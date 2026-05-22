import numpy as np
import pandas as pd
import pytest
from signals.indicators.zscore import compute_zscore
from signals.indicators.bollinger import compute_bollinger
from signals.indicators.atr import compute_atr


def test_zscore_warmup(sample_ohlcv):
    z = compute_zscore(sample_ohlcv["close"], window=20)
    assert z.iloc[:19].isna().all()
    assert z.iloc[20:].notna().all()


def test_zscore_mean_is_zero(sample_ohlcv):
    z = compute_zscore(sample_ohlcv["close"], window=20).dropna()
    assert abs(z.mean()) < 1.0


def test_bollinger_bands(sample_ohlcv):
    bb = compute_bollinger(sample_ohlcv["close"], period=20, n_std=2.0)
    valid = bb.dropna()
    assert (valid["upper"] >= valid["middle"]).all()
    assert (valid["middle"] >= valid["lower"]).all()


def test_bollinger_pct_b_range(sample_ohlcv):
    bb = compute_bollinger(sample_ohlcv["close"], period=20)
    valid = bb["pct_b"].dropna()
    assert ((valid >= -0.5) & (valid <= 1.5)).mean() > 0.9


def test_atr_positive(sample_ohlcv):
    atr = compute_atr(sample_ohlcv, period=14)
    assert (atr.dropna() > 0).all()
