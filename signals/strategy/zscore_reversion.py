import pandas as pd
from .base import Strategy
from ..indicators.zscore import compute_zscore


class ZScoreReversion(Strategy):
    """
    Mean reversion via rolling z-score.
    Long when z < -entry_threshold, short when z > +entry_threshold.
    Exit when |z| < exit_threshold.
    """

    def __init__(self, config: dict, instrument: str = ""):
        super().__init__(config, instrument)
        strat = config.get("zscore", {})
        inst_overrides = (
            config.get("instruments", {})
            .get(instrument, {})
            .get("strategy_overrides", {})
        )
        self.lookback = inst_overrides.get("zscore_lookback", strat.get("lookback_period", 20))
        self.entry_threshold = inst_overrides.get("entry_threshold", strat.get("entry_threshold", 2.0))
        self.exit_threshold = strat.get("exit_threshold", 0.5)
        self.price_field = strat.get("price_field", "close")

    def generate_signals(self, ohlcv: pd.DataFrame) -> pd.DataFrame:
        df = ohlcv.copy()
        df["zscore"] = compute_zscore(df[self.price_field], self.lookback)

        signal = pd.Series(0, index=df.index, dtype=int)
        position = 0

        for i in range(len(df)):
            z = df["zscore"].iloc[i]
            if pd.isna(z):
                signal.iloc[i] = 0
                continue

            if position == 0:
                if z <= -self.entry_threshold:
                    position = 1
                elif z >= self.entry_threshold:
                    position = -1
            elif position == 1 and z >= -self.exit_threshold:
                position = 0
            elif position == -1 and z <= self.exit_threshold:
                position = 0

            signal.iloc[i] = position

        df["signal"] = signal
        df["signal_strength"] = df["zscore"]
        return df
