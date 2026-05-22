import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def sample_ohlcv():
    """Synthetic AR(1) mean-reverting price series — 200 daily bars."""
    rng = np.random.default_rng(42)
    n = 200
    prices = [100.0]
    for _ in range(n - 1):
        prices.append(prices[-1] * 0.99 + 100.0 * 0.01 + rng.normal(0, 0.5))

    prices = np.array(prices)
    noise = rng.uniform(0, 0.5, n)

    idx = pd.date_range("2022-01-03", periods=n, freq="B", tz="UTC")
    return pd.DataFrame({
        "open": prices + rng.uniform(-0.3, 0.3, n),
        "high": prices + noise,
        "low": prices - noise,
        "close": prices,
        "volume": rng.integers(1000, 10000, n).astype(float),
    }, index=idx)


@pytest.fixture
def sample_config():
    return {
        "instruments": {
            "ES": {
                "symbol": "ES=F",
                "point_value": 50.0,
                "strategy_overrides": {},
            }
        },
        "zscore": {
            "lookback_period": 20,
            "entry_threshold": 2.0,
            "exit_threshold": 0.5,
            "price_field": "close",
        },
        "bollinger": {
            "period": 20,
            "std_dev": 2.0,
            "exit_band": 0.5,
            "squeeze_filter": False,
        },
        "risk": {
            "sizing_method": "fixed",
            "fixed": {"contracts": 1},
            "limits": {"max_position_contracts": 5},
        },
    }
