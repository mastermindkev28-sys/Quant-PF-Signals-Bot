"""
Backtesting engine with realistic futures simulation:
  - Per-contract P&L in dollars (point_value applied)
  - Round-turn commission and bi-directional slippage
  - Overnight gap fills (position open at prior close, fills at next open)
  - Prop firm daily limit enforcement during simulation
  - Full trade log with entry/exit details
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional
import pandas as pd
import numpy as np

from ..risk.manager import RiskManager

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    entry_time: pd.Timestamp
    entry_price: float
    direction: int          # 1=long, -1=short
    contracts: int
    stop_price: float
    strategy: str
    exit_time: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    exit_reason: str = ""
    pnl_gross: float = 0.0
    pnl_net: float = 0.0

    @property
    def is_open(self) -> bool:
        return self.exit_time is None

    def close(self, exit_time, exit_price, exit_reason, point_value,
              commission_rt, slippage_ticks, tick_value):
        self.exit_time = exit_time
        self.exit_price = exit_price
        self.exit_reason = exit_reason
        raw_pts = (exit_price - self.entry_price) * self.direction
        self.pnl_gross = raw_pts * point_value * self.contracts
        slip_cost = slippage_ticks * tick_value * 2 * self.contracts
        comm_cost = commission_rt * self.contracts
        self.pnl_net = self.pnl_gross - slip_cost - comm_cost
        return self.pnl_net


class BacktestEngine:
    """
    Bar-by-bar backtester. Processes a DataFrame with pre-computed signals and
    returns trade-level results plus an equity curve.
    """

    def __init__(self, config, instrument_cfg):
        self.cfg = config
        self.inst = instrument_cfg
        self.risk_mgr = RiskManager(config, instrument_cfg)
        self.trades: List[Trade] = []
        self._equity_curve: List[dict] = []
        self._open_trade: Optional[Trade] = None

    # ------------------------------------------------------------------
    # Main run loop
    # ------------------------------------------------------------------

    def run(self, df: pd.DataFrame) -> "BacktestResults":
        """
        df must have columns: signal, stop_price, signal_strength, close, open,
        high, low, atr.  signal: 1=enter long, -1=exit or enter short, 0=hold.
        """
        risk = self.cfg.risk
        inst = self.inst
        current_date = None

        for i, (ts, row) in enumerate(df.iterrows()):
            date_str = str(ts.date()) if hasattr(ts, "date") else str(ts)[:10]

            # ---------- Day boundary ----------
            if date_str != current_date:
                if current_date is not None:
                    # Close any overnight positions if prop rules require it
                    if self.cfg.prop.no_overnight and self._open_trade:
                        self._close_trade(ts, row["close"], "EOD_FLAT")
                    self.risk_mgr.end_day()
                current_date = date_str
                self.risk_mgr.start_day(date_str)

            # ---------- Simulate stop-loss on open gap ----------
            if self._open_trade:
                self._check_stop_gap(ts, row)

            # ---------- Process signal ----------
            sig = int(row.get("signal", 0))

            if sig == 0:
                pass  # hold or flat

            elif sig == 1:  # long entry signal
                if self._open_trade is None:
                    ok, reason = self.risk_mgr.can_trade()
                    if ok:
                        self._open_long(ts, row)
                    else:
                        logger.debug("Entry blocked at %s: %s", ts, reason)

                elif self._open_trade.direction == -1:
                    # Existing short — reverse
                    self._close_trade(ts, row["open"], "REVERSE_TO_LONG")
                    ok, _ = self.risk_mgr.can_trade()
                    if ok:
                        self._open_long(ts, row)

            elif sig == -1:  # exit signal or short entry
                if self._open_trade and self._open_trade.direction == 1:
                    self._close_trade(ts, row["close"], "EXIT_SIGNAL")

                elif self._open_trade is None and self.cfg.dual_thrust.allow_short \
                        if hasattr(self.cfg, "dual_thrust") else False:
                    ok, _ = self.risk_mgr.can_trade()
                    if ok:
                        self._open_short(ts, row)

            # ---------- Profit target and stop hit on bar close ----------
            if self._open_trade:
                self._check_profit_target_on_bar(ts, row)
            if self._open_trade:
                self._check_stop_on_bar(ts, row)

            # ---------- Record equity ----------
            unrealised = self._unrealised_pnl(row["close"])
            self._equity_curve.append({
                "timestamp": ts,
                "equity": self.risk_mgr.state.equity + unrealised,
                "realised_equity": self.risk_mgr.state.equity,
                "in_trade": self._open_trade is not None,
            })

        # Close any remaining open trade at end
        if self._open_trade:
            last_close = df["close"].iloc[-1]
            self._close_trade(df.index[-1], last_close, "END_OF_DATA")

        return BacktestResults(
            trades=self.trades,
            equity_curve=pd.DataFrame(self._equity_curve).set_index("timestamp"),
            config=self.cfg,
            instrument=self.inst,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _open_long(self, ts, row):
        fill = row["open"] + self.cfg.risk.slippage_ticks * self.inst.tick_size
        stop = float(row.get("stop_price", fill - 2 * row.get("atr", fill * 0.01)))
        strength = float(row.get("signal_strength", 0.5))
        contracts = self.risk_mgr.size_position(fill, stop, strength)
        t = Trade(
            entry_time=ts, entry_price=fill, direction=1,
            contracts=contracts, stop_price=stop,
            strategy=self.cfg.strategy,
        )
        self._open_trade = t
        logger.debug("LONG %d @ %.4f | stop %.4f | %s", contracts, fill, stop, ts)

    def _open_short(self, ts, row):
        fill = row["open"] - self.cfg.risk.slippage_ticks * self.inst.tick_size
        stop = float(row.get("stop_price", fill + 2 * row.get("atr", fill * 0.01)))
        strength = float(row.get("signal_strength", 0.5))
        contracts = self.risk_mgr.size_position(fill, stop, strength)
        t = Trade(
            entry_time=ts, entry_price=fill, direction=-1,
            contracts=contracts, stop_price=stop,
            strategy=self.cfg.strategy,
        )
        self._open_trade = t
        logger.debug("SHORT %d @ %.4f | stop %.4f | %s", contracts, fill, stop, ts)

    def _close_trade(self, ts, price: float, reason: str):
        t = self._open_trade
        if t is None:
            return
        # Slippage on exit
        slip = self.cfg.risk.slippage_ticks * self.inst.tick_size * t.direction
        exit_price = price - slip

        pnl_net = t.close(
            exit_time=ts,
            exit_price=exit_price,
            exit_reason=reason,
            point_value=self.inst.point_value,
            commission_rt=self.cfg.risk.commission_per_contract,
            slippage_ticks=self.cfg.risk.slippage_ticks,
            tick_value=self.inst.tick_value,
        )
        self.risk_mgr.record_trade(t.pnl_gross, t.contracts)
        self.trades.append(t)
        self._open_trade = None
        logger.debug(
            "CLOSE [%s] @ %.4f | PnL net: $%.2f | reason: %s",
            ts, exit_price, pnl_net, reason,
        )

    def _check_stop_gap(self, ts, row):
        """If today's open gaps through the stop, fill at open."""
        t = self._open_trade
        if t is None:
            return
        if t.direction == 1 and row["open"] <= t.stop_price:
            self._close_trade(ts, row["open"], "STOP_GAP")
        elif t.direction == -1 and row["open"] >= t.stop_price:
            self._close_trade(ts, row["open"], "STOP_GAP")

    def _check_stop_on_bar(self, ts, row):
        """Check if bar's low/high touches the stop price."""
        t = self._open_trade
        if t is None:
            return
        if t.direction == 1 and row["low"] <= t.stop_price:
            self._close_trade(ts, t.stop_price, "STOP_HIT")
        elif t.direction == -1 and row["high"] >= t.stop_price:
            self._close_trade(ts, t.stop_price, "STOP_HIT")

    def _check_profit_target_on_bar(self, ts, row):
        """Hit fixed R-multiple profit target if configured."""
        t = self._open_trade
        if t is None:
            return
        r = self.cfg.risk.profit_target_r
        if r <= 0:
            return
        risk_pts = abs(t.entry_price - t.stop_price)
        target_price = t.entry_price + t.direction * risk_pts * r
        if t.direction == 1 and row["high"] >= target_price:
            self._close_trade(ts, target_price, "TARGET_HIT")
        elif t.direction == -1 and row["low"] <= target_price:
            self._close_trade(ts, target_price, "TARGET_HIT")

    def _unrealised_pnl(self, current_price: float) -> float:
        t = self._open_trade
        if t is None:
            return 0.0
        return (current_price - t.entry_price) * t.direction * self.inst.point_value * t.contracts


# ---------------------------------------------------------------------------
# Results container
# ---------------------------------------------------------------------------

@dataclass
class BacktestResults:
    trades: List[Trade]
    equity_curve: pd.DataFrame
    config: object
    instrument: object

    def trades_df(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()
        rows = []
        for t in self.trades:
            rows.append({
                "entry_time": t.entry_time,
                "exit_time": t.exit_time,
                "direction": "LONG" if t.direction == 1 else "SHORT",
                "contracts": t.contracts,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "stop_price": t.stop_price,
                "exit_reason": t.exit_reason,
                "pnl_gross": round(t.pnl_gross, 2),
                "pnl_net": round(t.pnl_net, 2),
                "hold_bars": (
                    (t.exit_time - t.entry_time).days
                    if t.exit_time and t.entry_time else None
                ),
            })
        return pd.DataFrame(rows)
