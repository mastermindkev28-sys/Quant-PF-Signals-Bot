import pandas as pd
from .loader import DataLoader

_TIMEFRAME_MAP = {
    "1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h",
    "4h": "4h", "1d": "1d", "1wk": "1wk",
}


class LiveFeed(DataLoader):
    """Fetch recent OHLCV bars from yfinance (default) or a pluggable provider."""

    def __init__(self, provider: str = "yfinance"):
        self.provider = provider

    def fetch(self, symbol: str, start: str, end: str, timeframe: str = "1d") -> pd.DataFrame:
        if self.provider == "yfinance":
            return self._fetch_yfinance(symbol, start, end, timeframe)
        raise NotImplementedError(f"Provider '{self.provider}' not implemented. Available: yfinance")

    def _fetch_yfinance(self, symbol: str, start: str, end: str, timeframe: str) -> pd.DataFrame:
        try:
            import yfinance as yf
        except ImportError:
            raise ImportError("yfinance not installed. Run: pip install yfinance")

        interval = _TIMEFRAME_MAP.get(timeframe, "1d")
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start, end=end, interval=interval, auto_adjust=True)
        if df.empty:
            raise ValueError(f"No data returned for symbol '{symbol}' from yfinance")
        df = df.rename(columns=str.lower)
        df.index = pd.to_datetime(df.index)
        return self._validate(df)
