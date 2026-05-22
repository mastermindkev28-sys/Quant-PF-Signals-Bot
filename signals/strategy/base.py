from abc import ABC, abstractmethod
import pandas as pd


class Strategy(ABC):
    """Base class for all mean reversion strategies."""

    def __init__(self, config: dict, instrument: str = ""):
        self.config = config
        self.instrument = instrument

    @abstractmethod
    def generate_signals(self, ohlcv: pd.DataFrame) -> pd.DataFrame:
        """
        Augments ohlcv with at minimum:
          - signal: int column (1=long, -1=short, 0=flat)
          - signal_strength: float column (raw indicator value, e.g. z-score or pct_b)
        Returns the augmented DataFrame.
        """

    @staticmethod
    def combine_signals(
        df_a: pd.DataFrame,
        df_b: pd.DataFrame,
        mode: str = "AND",
    ) -> pd.Series:
        """Combine two signal columns using AND (both agree) or OR (either triggers)."""
        sig_a = df_a["signal"]
        sig_b = df_b["signal"]
        if mode == "AND":
            combined = sig_a.where(sig_a == sig_b, other=0)
        else:
            combined = sig_a.where(sig_a != 0, other=sig_b)
        return combined.rename("signal")
