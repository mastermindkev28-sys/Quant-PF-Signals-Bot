from pathlib import Path
import pandas as pd
from .loader import DataLoader


class CsvLoader(DataLoader):
    """Load OHLCV data from local CSV or Parquet files."""

    def __init__(self, data_dir: str = "data/raw"):
        self.data_dir = Path(data_dir)

    def fetch(self, symbol: str, start: str, end: str, timeframe: str = "1d") -> pd.DataFrame:
        candidates = list(self.data_dir.glob(f"{symbol}*.csv")) + list(
            self.data_dir.glob(f"{symbol}*.parquet")
        )
        if not candidates:
            raise FileNotFoundError(f"No data file found for {symbol} in {self.data_dir}")

        path = sorted(candidates)[-1]
        if path.suffix == ".parquet":
            df = pd.read_parquet(path)
        else:
            df = pd.read_csv(path, index_col=0, parse_dates=True)

        df = self._validate(df)
        return df.loc[start:end]
