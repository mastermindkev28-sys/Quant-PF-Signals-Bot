import json
import time
import logging
from datetime import datetime, timezone, timedelta
from ..data.live_feed import LiveFeed
from ..strategy.base import Strategy
from ..risk.position_sizer import PositionSizer

logger = logging.getLogger(__name__)


class LiveRunner:
    """
    Polling-based live signal runner.
    Emits JSON-lines signals to stdout on each new bar or signal change.
    """

    def __init__(
        self,
        strategy: Strategy,
        sizer: PositionSizer,
        instrument_cfg: dict,
        poll_interval_seconds: int = 60,
        lookback_bars: int = 60,
        timeframe: str = "1d",
    ):
        self.strategy = strategy
        self.sizer = sizer
        self.instrument_cfg = instrument_cfg
        self.poll_interval = poll_interval_seconds
        self.lookback_bars = lookback_bars
        self.timeframe = timeframe
        self.feed = LiveFeed()
        self._last_signal = None

    def run_once(self) -> dict:
        """Fetch latest bars, compute signal, return signal dict."""
        symbol = self.instrument_cfg["symbol"]
        point_value = self.instrument_cfg.get("point_value", 1.0)

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=self.lookback_bars * 2)

        ohlcv = self.feed.fetch(symbol, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), self.timeframe)
        result = self.strategy.generate_signals(ohlcv)

        last = result.iloc[-1]
        signal_val = int(last.get("signal", 0))
        strength = float(last.get("signal_strength", 0.0))
        contracts = self.sizer.size(ohlcv, point_value, -1) if signal_val != 0 else 0

        atr_stop = None
        try:
            from ..indicators.atr import compute_atr
            atr = compute_atr(ohlcv)
            atr_val = float(atr.iloc[-1])
            close = float(ohlcv["close"].iloc[-1])
            atr_stop = round(close - signal_val * atr_val * 2.0, 4)
        except Exception:
            pass

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "instrument": self.strategy.instrument,
            "symbol": symbol,
            "strategy": type(self.strategy).__name__,
            "signal": signal_val,
            "signal_strength": round(strength, 4),
            "suggested_contracts": contracts * signal_val if signal_val != 0 else 0,
            "entry_price_ref": round(float(ohlcv["close"].iloc[-1]), 4),
            "stop_price": atr_stop,
        }

    def run_loop(self, once: bool = False):
        """Polling loop. Set once=True for cron-compatible single-shot mode."""
        while True:
            try:
                sig = self.run_once()
                if once or sig != self._last_signal:
                    print(json.dumps(sig), flush=True)
                    self._last_signal = sig
            except Exception as e:
                logger.error("LiveRunner error: %s", e)

            if once:
                break
            time.sleep(self.poll_interval)
