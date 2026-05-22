"""
Dual Thrust breakout indicator.

Range = max(HH_N - LC_N,  HC_N - LL_N)
  HH_N = highest high of past N bars
  LC_N = lowest close of past N bars
  HC_N = highest close of past N bars
  LL_N = lowest low of past N bars

Upper = today_open + k_upper * Range
Lower = today_open - k_lower * Range

Long  if price crosses above Upper
Short if price crosses below Lower (if allow_short=True)
"""

import pandas as pd
import numpy as np
from .common import rolling_high, rolling_low


def compute_dual_thrust_range(df: pd.DataFrame, lookback: int = 4) -> pd.Series:
    """
    Calculate the Dual Thrust range value (scalar per bar).
    Uses shifted values so there is zero look-ahead on intraday bars.
    For intraday use, feed daily OHLCV and merge into the intraday frame.
    """
    hh = rolling_high(df["high"], lookback)
    lc = rolling_low(df["close"], lookback)
    hc = rolling_high(df["close"], lookback)
    ll = rolling_low(df["low"], lookback)

    r1 = hh - lc
    r2 = hc - ll
    return pd.concat([r1, r2], axis=1).max(axis=1).rename("dt_range")


def compute_dual_thrust_bands(
    df: pd.DataFrame,
    lookback: int = 4,
    k_upper: float = 0.5,
    k_lower: float = 0.5,
) -> pd.DataFrame:
    """
    Compute Dual Thrust bands for an intraday DataFrame.

    Expects the DataFrame to have columns: open, high, low, close
    with a first-bar-of-day flag column 'is_first_bar'.

    For correct no-look-ahead behaviour:
      - The range is computed from the PREVIOUS day's OHLCV
      - The bands are anchored to today's FIRST bar open
    """
    out = df.copy()

    # Compute range on daily aggregation, then forward-fill into intraday
    if "is_first_bar" not in out.columns:
        # Assume daily timeframe
        dt_range = compute_dual_thrust_range(out.shift(1), lookback)
        out["dt_range"] = dt_range
        out["upper_band"] = out["open"] + k_upper * out["dt_range"]
        out["lower_band"] = out["open"] - k_lower * out["dt_range"]
        return out

    # Intraday: get range from prior day's daily bars, then broadcast per day
    daily = out.resample("1D").agg({
        "open": "first", "high": "max", "low": "min", "close": "last"
    }).dropna()
    daily_range = compute_dual_thrust_range(daily, lookback).shift(1)  # prior day

    out["dt_range"] = out.index.normalize().map(
        lambda d: daily_range.get(pd.Timestamp(d, tz=daily_range.index.tz), np.nan)
    )

    # Session open = first bar's open each day
    session_open = (
        out[out["is_first_bar"]]["open"]
        .resample("1D").first()
    )
    out["session_open"] = out.index.normalize().map(
        lambda d: session_open.get(pd.Timestamp(d, tz=session_open.index.tz), np.nan)
    )

    out["upper_band"] = out["session_open"] + k_upper * out["dt_range"]
    out["lower_band"] = out["session_open"] - k_lower * out["dt_range"]

    # Signal flags
    out["long_signal"] = out["close"] > out["upper_band"]
    out["short_signal"] = out["close"] < out["lower_band"]

    return out
