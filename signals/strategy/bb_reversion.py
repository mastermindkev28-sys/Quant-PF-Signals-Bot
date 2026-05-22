import pandas as pd
from .base import Strategy
from ..indicators.bollinger import compute_bollinger


class BollingerReversion(Strategy):
    """
    Mean reversion via Bollinger Bands.
    Long when price crosses below lower band (pct_b < 0).
    Short when price crosses above upper band (pct_b > 1).
    Exit when pct_b crosses back through exit_band (default 0.5 = middle).
    Optional squeeze filter skips signals when bandwidth percentile is too low.
    """

    def __init__(self, config: dict, instrument: str = ""):
        super().__init__(config, instrument)
        strat = config.get("bollinger", {})
        self.period = strat.get("period", 20)
        self.std_dev = strat.get("std_dev", 2.0)
        self.exit_band = strat.get("exit_band", 0.5)
        self.squeeze_filter = strat.get("squeeze_filter", True)
        self._squeeze_pct = 20  # skip bottom 20th percentile bandwidth

    def generate_signals(self, ohlcv: pd.DataFrame) -> pd.DataFrame:
        df = ohlcv.copy()
        bb = compute_bollinger(df["close"], self.period, self.std_dev)
        df = pd.concat([df, bb], axis=1)

        squeeze_threshold = (
            df["bandwidth"].quantile(self._squeeze_pct / 100.0)
            if self.squeeze_filter
            else -float("inf")
        )

        signal = pd.Series(0, index=df.index, dtype=int)
        position = 0

        for i in range(len(df)):
            pb = df["pct_b"].iloc[i]
            bw = df["bandwidth"].iloc[i]

            if pd.isna(pb) or pd.isna(bw):
                signal.iloc[i] = 0
                continue

            in_squeeze = bw < squeeze_threshold

            if position == 0 and not in_squeeze:
                if pb < 0:
                    position = 1
                elif pb > 1:
                    position = -1
            elif position == 1 and pb >= self.exit_band:
                position = 0
            elif position == -1 and pb <= self.exit_band:
                position = 0

            signal.iloc[i] = position

        df["signal"] = signal
        df["signal_strength"] = df["pct_b"]
        return df
