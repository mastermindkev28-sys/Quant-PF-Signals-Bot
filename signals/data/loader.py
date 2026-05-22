from abc import ABC, abstractmethod
import pandas as pd


REQUIRED_COLUMNS = {"open", "high", "low", "close", "volume"}


class DataLoader(ABC):
    """Abstract base for all data sources. Subclasses must return a UTC-indexed OHLCV DataFrame."""

    @abstractmethod
    def fetch(
        self,
        symbol: str,
        start: str,
        end: str,
        timeframe: str = "1d",
    ) -> pd.DataFrame:
        """Return a DataFrame with columns: open, high, low, close, volume; DatetimeIndex in UTC."""

    def _validate(self, df: pd.DataFrame) -> pd.DataFrame:
        df.columns = [c.lower() for c in df.columns]
        missing = REQUIRED_COLUMNS - set(df.columns)
        if missing:
            raise ValueError(f"Data missing required columns: {missing}")
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("DataFrame index must be DatetimeIndex")
        df.index = df.index.tz_localize("UTC") if df.index.tz is None else df.index.tz_convert("UTC")
        return df[["open", "high", "low", "close", "volume"]].sort_index()
