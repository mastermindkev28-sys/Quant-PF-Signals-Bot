import math
import pandas as pd
from ..indicators.atr import compute_atr


class PositionSizer:
    """Determines contract size per trade based on configured sizing method."""

    def __init__(self, config: dict):
        risk = config.get("risk", config)
        self.method = risk.get("sizing_method", "fractional")
        self.max_contracts = int(risk.get("limits", {}).get("max_position_contracts", 5))
        self._fixed_cfg = risk.get("fixed", {})
        self._frac_cfg = risk.get("fractional", {})
        self._vt_cfg = risk.get("volatility_target", {})

    def size(
        self,
        ohlcv: pd.DataFrame,
        point_value: float,
        bar_index: int = -1,
    ) -> int:
        if self.method == "fixed":
            return min(int(self._fixed_cfg.get("contracts", 1)), self.max_contracts)

        if self.method == "fractional":
            return self._fractional(ohlcv, point_value, bar_index)

        if self.method == "volatility_target":
            return self._volatility_target(ohlcv, point_value, bar_index)

        raise ValueError(f"Unknown sizing_method: {self.method}")

    def _fractional(self, ohlcv: pd.DataFrame, point_value: float, bar_index: int) -> int:
        cfg = self._frac_cfg
        account = float(cfg.get("account_size", 100_000))
        risk_pct = float(cfg.get("risk_per_trade_pct", 0.01))
        atr_period = int(cfg.get("atr_period", 14))
        atr_mult = float(cfg.get("atr_multiplier", 2.0))

        atr = compute_atr(ohlcv, atr_period)
        atr_val = float(atr.iloc[bar_index])
        if atr_val <= 0 or math.isnan(atr_val):
            return 1

        dollar_risk = account * risk_pct
        stop_dollars = atr_val * atr_mult * point_value
        contracts = int(dollar_risk / stop_dollars)
        return max(1, min(contracts, self.max_contracts))

    def _volatility_target(self, ohlcv: pd.DataFrame, point_value: float, bar_index: int) -> int:
        cfg = self._vt_cfg
        account = float(cfg.get("account_size", 100_000))
        daily_vol_target = float(cfg.get("daily_vol_target_pct", 0.005))
        lookback = int(cfg.get("vol_lookback", 20))

        returns = ohlcv["close"].pct_change().iloc[max(0, bar_index - lookback):bar_index]
        realized_vol = float(returns.std())
        if realized_vol <= 0 or math.isnan(realized_vol):
            return 1

        close = float(ohlcv["close"].iloc[bar_index])
        target_dollar_vol = account * daily_vol_target
        instrument_dollar_vol = realized_vol * close * point_value
        contracts = int(target_dollar_vol / instrument_dollar_vol)
        return max(1, min(contracts, self.max_contracts))
