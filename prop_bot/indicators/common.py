"""
Core technical indicators: SMA, EMA, ATR, rolling-highest/lowest.
All functions operate on pandas Series/DataFrame and return Series.
No look-ahead bias — all rolling operations are strictly backward-looking.
"""

import pandas as pd
import numpy as np


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rolling_high(series: pd.Series, period: int) -> pd.Series:
    """Highest value over the last `period` bars (inclusive of current bar)."""
    return series.rolling(period, min_periods=period).max()


def rolling_low(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).min()


def true_range(df: pd.DataFrame) -> pd.Series:
    """True Range: max of (H-L), |H-prevC|, |L-prevC|."""
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder Average True Range."""
    tr = true_range(df)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def stddev(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).std(ddof=1)


def zscore(series: pd.Series, period: int) -> pd.Series:
    mu = sma(series, period)
    sigma = stddev(series, period)
    return (series - mu) / sigma.replace(0, np.nan)


def donchian_channel(df: pd.DataFrame, period: int):
    """Returns (upper, lower) as tuple of Series."""
    upper = rolling_high(df["high"], period)
    lower = rolling_low(df["low"], period)
    return upper, lower


def prev_day_high(df: pd.DataFrame) -> pd.Series:
    """Previous bar's high — used for IBS exit signal."""
    return df["high"].shift(1)


def prev_day_low(df: pd.DataFrame) -> pd.Series:
    return df["low"].shift(1)
