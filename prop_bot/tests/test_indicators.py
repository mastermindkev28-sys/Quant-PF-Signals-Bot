import pandas as pd
import numpy as np
import pytest
from prop_bot.indicators.ibs import compute_ibs, compute_ibs_bands
from prop_bot.indicators.common import atr, sma, rolling_high


def test_ibs_range(daily_ohlcv):
    ibs = compute_ibs(daily_ohlcv)
    valid = ibs.dropna()
    assert (valid >= 0.0).all() and (valid <= 1.0).all()


def test_ibs_doji_is_nan(daily_ohlcv):
    df = daily_ohlcv.copy()
    df.loc[df.index[5], "high"] = df.loc[df.index[5], "low"]  # force zero range
    ibs = compute_ibs(df)
    assert pd.isna(ibs.iloc[5])


def test_ibs_bands_columns(daily_ohlcv):
    result = compute_ibs_bands(daily_ohlcv)
    for col in ["ibs", "lower_band", "trend_sma", "avg_range", "long_signal"]:
        assert col in result.columns


def test_ibs_lower_band_below_highest_high(daily_ohlcv):
    result = compute_ibs_bands(daily_ohlcv)
    valid = result.dropna(subset=["lower_band", "highest_high"])
    assert (valid["lower_band"] <= valid["highest_high"]).all()


def test_atr_positive(daily_ohlcv):
    a = atr(daily_ohlcv, period=14)
    assert (a.dropna() > 0).all()


def test_rolling_high_non_decreasing_over_period(daily_ohlcv):
    rh = rolling_high(daily_ohlcv["high"], 10)
    valid = rh.dropna()
    highs_aligned = daily_ohlcv["high"].loc[valid.index]
    # Rolling max over N bars must be >= the current bar's high
    assert (valid >= highs_aligned).all()


def test_sma_warmup(daily_ohlcv):
    s = sma(daily_ohlcv["close"], 20)
    assert s.iloc[:19].isna().all()
    assert s.iloc[20:].notna().all()
