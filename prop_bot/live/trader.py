"""
Live trading execution loop.

Architecture:
  - Polls market data every N seconds (configurable)
  - Recomputes indicators on latest bars
  - Checks signal against last bar
  - Routes orders through TradovateClient
  - Risk manager gates every order
  - Alerts via Telegram on all events
  - Flattens all positions before session end (prop firm no-overnight rule)

IMPORTANT — SAFETY CHECKLIST before going live:
  [ ] Run full backtest >= 5 years on target instrument
  [ ] Verify WFO efficiency >= 50%
  [ ] Monte Carlo ruin probability < 10%
  [ ] Test paper/demo for >= 2 weeks
  [ ] Confirm prop firm allows automated trading
  [ ] Confirm instrument and contract month are correct
  [ ] Set tradovate_demo=False ONLY when all above are complete
"""

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
import pandas as pd

from ..config import BotConfig, INSTRUMENTS
from ..data.loader import load_data
from ..risk.manager import RiskManager
from ..utils.alerts import AlertManager
from .tradovate import TradovateClient

logger = logging.getLogger(__name__)


def _build_strategy(config: BotConfig, inst_cfg):
    if config.strategy == "ibs":
        from ..strategies.ibs_mean_reversion import IBSMeanReversion
        return IBSMeanReversion(config, inst_cfg)
    elif config.strategy == "dual_thrust":
        from ..strategies.dual_thrust import DualThrustBreakout
        return DualThrustBreakout(config, inst_cfg)
    raise ValueError(f"Unknown strategy: {config.strategy}")


class LiveTrader:
    def __init__(self, config: BotConfig):
        self.cfg = config
        self.inst = INSTRUMENTS[config.instrument]
        self.strategy = _build_strategy(config, self.inst)
        self.risk = RiskManager(config, self.inst)
        self.alerts = AlertManager(config)
        self.broker = TradovateClient(config)
        self._position: int = 0         # +1 long, -1 short, 0 flat
        self._entry_price: float = 0.0
        self._entry_contracts: int = 0
        self._stop_price: float = 0.0
        self._last_signal: int = 0

    def start(self):
        """Main polling loop. Runs until KeyboardInterrupt or halt."""
        logger.info("Authenticating with broker...")
        self.broker.authenticate()
        acct = self.broker.get_account()
        logger.info("Account: %s | Mode: %s",
                    acct.get("name"), "DEMO" if self.cfg.live.tradovate_demo else "LIVE")

        self.alerts.send(
            f"PropBot started | {self.cfg.instrument} | {self.cfg.strategy.upper()} "
            f"| {'DEMO' if self.cfg.live.tradovate_demo else '⚠ LIVE'}",
            "INFO",
        )

        today = None
        while True:
            try:
                now = datetime.now(timezone.utc)
                today_str = now.strftime("%Y-%m-%d")

                if today_str != today:
                    if today is not None:
                        self._end_of_day()
                    today = today_str
                    self.risk.start_day(today_str)

                self._check_eod_flatten(now)
                self._poll_and_act()

                time.sleep(self.cfg.live.poll_interval_seconds)

            except KeyboardInterrupt:
                logger.info("Shutdown requested — flattening positions")
                self._flatten_all("MANUAL_SHUTDOWN")
                self.alerts.send("Bot stopped (manual shutdown)", "INFO")
                break
            except Exception as e:
                logger.exception("Live loop error: %s", e)
                self.alerts.error(str(e))
                time.sleep(30)  # back-off on error

    def _poll_and_act(self):
        """Fetch latest bars, compute signal, execute if changed."""
        now = datetime.now(timezone.utc)
        lookback_days = max(400, self.cfg.data.warmup_bars)
        start = (now - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        end = now.strftime("%Y-%m-%d")

        try:
            df = load_data(
                self.inst.symbol,
                start, end,
                timeframe=self.cfg.ibs.timeframe if self.cfg.strategy == "ibs" else self.cfg.dual_thrust.timeframe,
                provider="yfinance",
            )
        except Exception as e:
            logger.error("Data fetch failed: %s", e)
            return

        result = self.strategy.run(df)
        if result.empty:
            return

        last = result.iloc[-1]
        signal = int(last.get("signal", 0))
        stop = float(last.get("stop_price", 0))
        strength = float(last.get("signal_strength", 0.5))

        # Only act on signal changes
        if signal == self._last_signal:
            return
        self._last_signal = signal

        ok, reason = self.risk.can_trade()
        if not ok:
            self.alerts.daily_halt(reason, self.risk.state.day.gross_pnl, self.risk.state.equity)
            return

        close = float(last["close"])

        if signal == 1 and self._position == 0:
            contracts = self.risk.size_position(close, stop, strength)
            self._enter_long(contracts, close, stop)

        elif signal == -1 and self._position == 1:
            self._exit_position(close, "EXIT_SIGNAL")

        elif signal == -1 and self._position == 0 and self.cfg.strategy == "dual_thrust":
            contracts = self.risk.size_position(close, stop, strength)
            self._enter_short(contracts, close, stop)

        elif signal == 1 and self._position == -1:
            self._exit_position(close, "EXIT_SIGNAL")

    def _enter_long(self, contracts: int, price: float, stop: float):
        symbol = self.inst.tradovate_symbol
        logger.info("ENTER LONG %d %s @ %.4f | stop %.4f", contracts, symbol, price, stop)
        try:
            self.broker.place_bracket_order(symbol, "Buy", contracts, stop)
            self._position = 1
            self._entry_price = price
            self._entry_contracts = contracts
            self._stop_price = stop
            self.alerts.trade_entry(self.cfg.instrument, "LONG", price, contracts, stop)
        except Exception as e:
            logger.error("Order failed: %s", e)
            self.alerts.error(f"Entry order failed: {e}")

    def _enter_short(self, contracts: int, price: float, stop: float):
        symbol = self.inst.tradovate_symbol
        logger.info("ENTER SHORT %d %s @ %.4f | stop %.4f", contracts, symbol, price, stop)
        try:
            self.broker.place_bracket_order(symbol, "Sell", contracts, stop)
            self._position = -1
            self._entry_price = price
            self._entry_contracts = contracts
            self._stop_price = stop
            self.alerts.trade_entry(self.cfg.instrument, "SHORT", price, contracts, stop)
        except Exception as e:
            logger.error("Order failed: %s", e)
            self.alerts.error(f"Short entry failed: {e}")

    def _exit_position(self, price: float, reason: str):
        if self._position == 0:
            return
        direction = "LONG" if self._position == 1 else "SHORT"
        action = "Sell" if self._position == 1 else "Buy"
        symbol = self.inst.tradovate_symbol
        contracts = self._entry_contracts

        logger.info("EXIT %s %d %s @ %.4f | reason: %s",
                    direction, contracts, symbol, price, reason)
        try:
            self.broker.cancel_all_orders()
            self.broker.place_market_order(symbol, action, contracts)

            pnl_gross = (price - self._entry_price) * self._position * self.inst.point_value * contracts
            pnl_net = self.risk.record_trade(pnl_gross, contracts)
            self.alerts.trade_exit(
                self.cfg.instrument, direction,
                self._entry_price, price, pnl_net, reason,
            )
            self._position = 0
            self._entry_price = 0.0
            self._entry_contracts = 0
        except Exception as e:
            logger.error("Exit order failed: %s", e)
            self.alerts.error(f"Exit failed: {e}")

    def _flatten_all(self, reason: str = "FLATTEN"):
        if self._position != 0:
            price = self._entry_price  # best estimate for alert
            self._exit_position(price, reason)

    def _check_eod_flatten(self, now: datetime):
        """Flatten positions before end-of-session if prop rules require it."""
        if not self.cfg.prop.no_overnight:
            return
        # Simple approach: flatten after 3:45 PM ET (15:45 UTC-5 = 20:45 UTC)
        eod_hour_utc = 21  # adjust for DST as needed
        if now.hour >= eod_hour_utc and self._position != 0:
            logger.info("EOD flatten triggered (%s UTC)", now)
            self._flatten_all("EOD_NO_OVERNIGHT")

    def _end_of_day(self):
        state = self.risk.state
        dd_remaining = (
            self.cfg.prop.max_trailing_drawdown
            - (state.peak_equity - state.equity)
        )
        self.alerts.daily_summary(
            state.day.date,
            state.day.gross_pnl,
            state.day.trades,
            state.equity,
            max(0, dd_remaining),
        )
        self.risk.end_day()
