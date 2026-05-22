import pandas as pd
import pytest
from signals.strategy.zscore_reversion import ZScoreReversion
from signals.strategy.bb_reversion import BollingerReversion
from signals.strategy.base import Strategy


def test_zscore_signal_columns(sample_ohlcv, sample_config):
    strat = ZScoreReversion(sample_config, "ES")
    result = strat.generate_signals(sample_ohlcv)
    assert "signal" in result.columns
    assert "signal_strength" in result.columns


def test_zscore_signal_values(sample_ohlcv, sample_config):
    strat = ZScoreReversion(sample_config, "ES")
    result = strat.generate_signals(sample_ohlcv)
    assert set(result["signal"].unique()).issubset({-1, 0, 1})


def test_bollinger_signal_columns(sample_ohlcv, sample_config):
    strat = BollingerReversion(sample_config, "ES")
    result = strat.generate_signals(sample_ohlcv)
    assert "signal" in result.columns
    assert "signal_strength" in result.columns


def test_bollinger_signal_values(sample_ohlcv, sample_config):
    strat = BollingerReversion(sample_config, "ES")
    result = strat.generate_signals(sample_ohlcv)
    assert set(result["signal"].unique()).issubset({-1, 0, 1})


def test_combine_signals_and(sample_ohlcv, sample_config):
    s1 = ZScoreReversion(sample_config, "ES").generate_signals(sample_ohlcv)
    s2 = BollingerReversion(sample_config, "ES").generate_signals(sample_ohlcv)
    combined = Strategy.combine_signals(s1, s2, mode="AND")
    # AND mode: combined signal must match both or be 0
    mask = (s1["signal"] != s2["signal"])
    assert (combined[mask] == 0).all()
