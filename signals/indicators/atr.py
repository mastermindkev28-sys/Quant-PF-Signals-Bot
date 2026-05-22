import pandas as pd
import numpy as np


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder ATR from an OHLCV DataFrame with open/high/low/close columns."""
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    # Wilder smoothing: EWM with alpha = 1/period
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
