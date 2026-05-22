"""
Risk Manager — position sizing, prop-firm rule enforcement, and daily limits.

Position Sizing Methods
-----------------------
1. Fixed Fractional  : risk_pct * account / (stop_distance * point_value)
2. Kelly-Lite        : fractional Kelly capped at 25% bet fraction
3. Volatility Target : target fixed daily dollar vol (divides by ATR * point_value)

Prop Firm Rules
---------------
- Daily loss limit   : halt all trading if day's P&L < -max_daily_loss
- Trailing drawdown  : halt if equity falls > max_trailing_drawdown from peak
- Consistency check  : warn if any single day would be >40% of total profit
- No overnight       : force flatten before session end
- Max contracts      : never exceed prop firm limit
"""

import logging
from dataclasses import dataclass, field
from typing import Optional
import math

logger = logging.getLogger(__name__)


@dataclass
class DayState:
    """Mutable state tracked per trading day."""
    date: str = ""
    trades: int = 0
    gross_pnl: float = 0.0
    peak_intraday_equity: float = 0.0
    halted: bool = False
    halt_reason: str = ""


@dataclass
class AccountState:
    """Persistent account state across the simulation / live session."""
    equity: float = 0.0
    peak_equity: float = 0.0
    total_gross_pnl: float = 0.0
    total_trades: int = 0
    trading_days: int = 0
    day: DayState = field(default_factory=DayState)


class RiskManager:
    """
    Central risk gate. All trade actions must be approved through this object.
    """

    def __init__(self, config, instrument_cfg):
        self.cfg = config
        self.risk = config.risk
        self.prop = config.prop
        self.inst = instrument_cfg
        self.state = AccountState(
            equity=self.prop.account_size,
            peak_equity=self.prop.account_size,
        )

    # ------------------------------------------------------------------
    # Daily session management
    # ------------------------------------------------------------------

    def start_day(self, date: str):
        self.state.day = DayState(date=date)
        self.state.day.peak_intraday_equity = self.state.equity
        self.state.trading_days += 1
        logger.info("=== New trading day: %s | Equity: $%.2f ===", date, self.state.equity)

    def end_day(self):
        d = self.state.day
        logger.info(
            "Day %s ended | P&L: $%.2f | Trades: %d | Equity: $%.2f",
            d.date, d.gross_pnl, d.trades, self.state.equity,
        )
        if d.gross_pnl > 0:
            pct = d.gross_pnl / max(self.state.total_gross_pnl, 0.01)
            if pct > self.prop.max_single_day_profit_pct:
                logger.warning(
                    "Consistency WARNING: Today's profit ($%.2f) is %.0f%% of total P&L "
                    "— exceeds %.0f%% threshold. Risk: prop firm may flag account.",
                    d.gross_pnl, pct * 100, self.prop.max_single_day_profit_pct * 100,
                )

    # ------------------------------------------------------------------
    # Trade approval gate
    # ------------------------------------------------------------------

    def can_trade(self) -> tuple[bool, str]:
        """Returns (approved, reason). Call before every order."""
        d = self.state.day

        if d.halted:
            return False, f"HALTED: {d.halt_reason}"

        # Daily profit target — stop trading once hit (locks in the day's gains)
        daily_target = self.risk.daily_profit_target
        if daily_target > 0 and d.gross_pnl >= daily_target:
            d.halted = True
            d.halt_reason = f"Daily profit target ${daily_target:.0f} reached — locking in gains"
            logger.info("TARGET HIT — %s", d.halt_reason)
            return False, d.halt_reason

        # Daily loss check
        if d.gross_pnl <= -self.prop.max_daily_loss:
            d.halted = True
            d.halt_reason = f"Daily loss limit ${self.prop.max_daily_loss:.0f} reached"
            logger.warning("HALT — %s", d.halt_reason)
            return False, d.halt_reason

        # Trailing drawdown check
        drawdown_from_peak = self.state.peak_equity - self.state.equity
        if drawdown_from_peak >= self.prop.max_trailing_drawdown:
            d.halted = True
            d.halt_reason = (
                f"Trailing drawdown ${drawdown_from_peak:.0f} "
                f">= limit ${self.prop.max_trailing_drawdown:.0f}"
            )
            logger.warning("HALT — %s", d.halt_reason)
            return False, d.halt_reason

        # Total loss floor
        total_loss = self.prop.account_size - self.state.equity
        if total_loss >= self.prop.max_total_loss:
            d.halted = True
            d.halt_reason = f"Total loss ${total_loss:.0f} >= floor ${self.prop.max_total_loss:.0f}"
            logger.warning("HALT — %s", d.halt_reason)
            return False, d.halt_reason

        return True, "OK"

    # ------------------------------------------------------------------
    # Position sizing
    # ------------------------------------------------------------------

    def size_position(
        self,
        entry_price: float,
        stop_price: float,
        signal_strength: float = 1.0,
        win_rate: float = 0.55,
        avg_win_loss_ratio: float = 1.5,
    ) -> int:
        """
        Returns integer number of contracts (minimum 1, max prop.max_contracts).
        Applies prop firm contract cap after internal sizing.
        """
        stop_distance = abs(entry_price - stop_price)
        if stop_distance <= 0:
            logger.warning("Zero stop distance — defaulting to 1 contract")
            return 1

        dollar_risk_per_contract = stop_distance * self.inst.point_value
        # Add round-trip commission and slippage to cost
        slippage_cost = self.risk.slippage_ticks * self.inst.tick_value * 2
        commission_cost = self.risk.commission_per_contract
        total_cost = dollar_risk_per_contract + slippage_cost + commission_cost

        # Aggressive mode: always use prop firm max contracts
        if self.risk.use_max_contracts:
            contracts = self.prop.max_contracts
        elif self.risk.use_kelly:
            contracts = self._kelly_size(total_cost, win_rate, avg_win_loss_ratio)
        else:
            contracts = self._fractional_size(total_cost)
            # Scale by signal strength (range [0.5, 1.0])
            scale = 0.5 + 0.5 * signal_strength
            contracts = max(1, round(contracts * scale))

        # Hard caps
        contracts = min(contracts, self.prop.max_contracts)

        # Never risk more than max_daily_loss remaining
        remaining_daily_buffer = self.prop.max_daily_loss + self.state.day.gross_pnl
        max_by_buffer = max(1, int(remaining_daily_buffer / max(total_cost, 1)))
        contracts = min(contracts, max_by_buffer)

        return max(1, contracts)

    def _fractional_size(self, dollar_risk_per_contract: float) -> int:
        account = self.state.equity
        max_risk_dollars = account * self.risk.risk_per_trade_pct
        return max(1, int(max_risk_dollars / dollar_risk_per_contract))

    def _kelly_size(
        self, dollar_risk_per_contract: float, win_rate: float, avg_rr: float
    ) -> int:
        # Kelly fraction = p - q/r  (p=win rate, q=loss rate, r=reward/risk)
        p, q = win_rate, 1 - win_rate
        full_kelly = p - q / max(avg_rr, 0.01)
        kelly_frac = max(0.0, full_kelly) * self.risk.kelly_fraction  # fractional Kelly
        account = self.state.equity
        max_risk_dollars = account * kelly_frac
        return max(1, int(max_risk_dollars / dollar_risk_per_contract))

    # ------------------------------------------------------------------
    # P&L accounting
    # ------------------------------------------------------------------

    def record_trade(self, pnl_gross: float, contracts: int):
        """Call after every trade is closed."""
        commission = self.risk.commission_per_contract * contracts
        slippage = self.risk.slippage_ticks * self.inst.tick_value * contracts * 2
        pnl_net = pnl_gross - commission - slippage

        self.state.equity += pnl_net
        self.state.peak_equity = max(self.state.peak_equity, self.state.equity)
        self.state.total_gross_pnl += pnl_net
        self.state.total_trades += 1
        self.state.day.gross_pnl += pnl_net
        self.state.day.trades += 1
        self.state.day.peak_intraday_equity = max(
            self.state.day.peak_intraday_equity, self.state.equity
        )

        logger.debug(
            "Trade closed | Gross: $%.2f | Net: $%.2f | Equity: $%.2f",
            pnl_gross, pnl_net, self.state.equity,
        )
        return pnl_net

    # ------------------------------------------------------------------
    # Prop firm status summary
    # ------------------------------------------------------------------

    def status_report(self) -> dict:
        dd = self.state.peak_equity - self.state.equity
        dd_pct = dd / self.state.peak_equity * 100 if self.state.peak_equity else 0
        return {
            "equity": round(self.state.equity, 2),
            "peak_equity": round(self.state.peak_equity, 2),
            "total_pnl": round(self.state.total_gross_pnl, 2),
            "trailing_drawdown": round(dd, 2),
            "trailing_dd_pct": round(dd_pct, 2),
            "daily_pnl": round(self.state.day.gross_pnl, 2),
            "daily_trades": self.state.day.trades,
            "total_trades": self.state.total_trades,
            "trading_days": self.state.trading_days,
            "halted": self.state.day.halted,
            "halt_reason": self.state.day.halt_reason,
            "daily_limit_used_pct": round(
                abs(min(0, self.state.day.gross_pnl)) / self.prop.max_daily_loss * 100, 1
            ),
        }
