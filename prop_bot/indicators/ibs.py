"""
Internal Bar Strength (IBS) mean reversion indicator set.

Strategy logic (exact rules):
  rolling_mean  = SMA(high - low, 25)
  IBS           = (close - low) / (high - low)
  lower_band    = highest(high, 10) - 2.5 * rolling_mean
  LONG entry    : close < lower_band  AND  IBS < 0.3
  EXIT          : close > prev_high   OR   close < SMA(close, 300)
"""

import pandas as pd
import numpy as np
from .common import sma, rolling_high, prev_day_high


def compute_ibs(df: pd.DataFrame) -> pd.Series:
    """
    IBS = (close - low) / (high - low).
    Returns NaN when high == low (doji / zero-range bar).
    Values in [0, 1]: 0 = close at low, 1 = close at high.
    """
    rng = df["high"] - df["low"]
    return ((df["close"] - df["low"]) / rng.replace(0, np.nan)).clip(0.0, 1.0)


def compute_ibs_bands(
    df: pd.DataFrame,
    range_sma_period: int = 25,
    highest_high_lookback: int = 10,
    band_multiplier: float = 2.5,
    trend_sma_period: int = 300,
) -> pd.DataFrame:
    """
    Compute all IBS strategy inputs and return as an augmented DataFrame.

    Columns added:
      daily_range   : high - low
      avg_range     : SMA(daily_range, 25)
      ibs           : internal bar strength
      highest_high  : rolling highest high over 10 bars
      lower_band    : highest_high - 2.5 * avg_range
      trend_sma     : SMA(close, 300)
      prev_high     : previous bar's high (for exit trigger)
    """
    out = df.copy()

    out["daily_range"] = out["high"] - out["low"]
    out["avg_range"] = sma(out["daily_range"], range_sma_period)
    out["ibs"] = compute_ibs(out)
    out["highest_high"] = rolling_high(out["high"], highest_high_lookback)
    out["lower_band"] = out["highest_high"] - band_multiplier * out["avg_range"]
    out["trend_sma"] = sma(out["close"], trend_sma_period)
    out["prev_high"] = prev_day_high(out)

    # Entry condition as boolean columns (for readability / debugging)
    out["cond_below_band"] = out["close"] < out["lower_band"]
    out["cond_ibs_low"] = out["ibs"] < 0.3
    out["cond_trend_ok"] = out["close"] > out["trend_sma"]

    # Composite long signal (requires both price AND IBS condition, filtered by trend)
    out["long_signal"] = (
        out["cond_below_band"] & out["cond_ibs_low"] & out["cond_trend_ok"]
    )

    # Exit conditions
    out["exit_above_prev_high"] = out["close"] > out["prev_high"]
    out["exit_below_trend"] = out["close"] < out["trend_sma"]
    out["exit_signal"] = out["exit_above_prev_high"] | out["exit_below_trend"]

    return out


def ibs_signal_quality(df: pd.DataFrame) -> pd.Series:
    """
    Signal quality score [0–1] combining IBS distance from 0.3 and
    band penetration depth. Higher = stronger mean-reversion setup.
    """
    ibs_score = (0.3 - df["ibs"]).clip(lower=0) / 0.3
    band_pct = (df["lower_band"] - df["close"]) / df["avg_range"].replace(0, np.nan)
    band_score = band_pct.clip(lower=0) / 2.0  # normalise — 2 avg_ranges = max
    return (0.6 * ibs_score + 0.4 * band_score.clip(upper=1.0)).rename("signal_quality")
