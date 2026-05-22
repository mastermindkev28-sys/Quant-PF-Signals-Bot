import pandas as pd


def compute_zscore(series: pd.Series, window: int) -> pd.Series:
    """Rolling z-score: (x - rolling_mean) / rolling_std. Returns NaN during warmup."""
    roll = series.rolling(window)
    mean = roll.mean()
    std = roll.std(ddof=1)
    return (series - mean) / std.replace(0, float("nan"))
