"""Shared test fixtures for prop_bot."""

import numpy as np
import pandas as pd
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from prop_bot.config import BotConfig, INSTRUMENTS, PROP_PRESETS


@pytest.fixture
def daily_ohlcv():
    """600 daily bars with mean-reverting AR(1) price process."""
    rng = np.random.default_rng(42)
    n = 600
    prices = [1900.0]
    for _ in range(n - 1):
        # AR(1): slow mean reversion to 1900
        prices.append(prices[-1] * 0.995 + 1900 * 0.005 + rng.normal(0, 5))
    prices = np.array(prices)
    noise = rng.uniform(3, 12, n)  # daily range

    idx = pd.date_range("2020-01-02", periods=n, freq="B", tz="UTC")
    return pd.DataFrame({
        "open":   prices + rng.uniform(-2, 2, n),
        "high":   prices + noise,
        "low":    prices - noise,
        "close":  prices,
        "volume": rng.integers(10_000, 100_000, n).astype(float),
    }, index=idx)


@pytest.fixture
def cfg():
    c = BotConfig()
    c.instrument = "MGC"
    c.strategy = "ibs"
    c.prop = PROP_PRESETS["topstep_50k"]
    return c


@pytest.fixture
def inst():
    return INSTRUMENTS["MGC"]
