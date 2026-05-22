import pandas as pd
import pytest
from signals.strategy.zscore_reversion import ZScoreReversion
from signals.risk.position_sizer import PositionSizer
from signals.backtest.engine import Backtester
from signals.backtest.metrics import compute_metrics


def test_backtest_runs(sample_ohlcv, sample_config):
    strat = ZScoreReversion(sample_config, "ES")
    sizer = PositionSizer(sample_config["risk"])
    bt = Backtester(strat, sizer, point_value=50.0)
    results = bt.run(sample_ohlcv)
    assert "pnl" in results.columns
    assert "equity" in results.columns
    assert len(results) == len(sample_ohlcv)


def test_backtest_no_lookahead(sample_ohlcv, sample_config):
    strat = ZScoreReversion(sample_config, "ES")
    sizer = PositionSizer(sample_config["risk"])
    bt = Backtester(strat, sizer, point_value=50.0)
    results = bt.run(sample_ohlcv)
    # Contracts at bar T should reflect signal from bar T-1
    assert results["contracts"].iloc[0] == 0


def test_metrics_keys(sample_ohlcv, sample_config):
    strat = ZScoreReversion(sample_config, "ES")
    sizer = PositionSizer(sample_config["risk"])
    bt = Backtester(strat, sizer, point_value=50.0)
    results = bt.run(sample_ohlcv)
    metrics = compute_metrics(results)
    required_keys = {"total_pnl", "sharpe_ratio", "max_drawdown", "win_rate", "n_trades"}
    assert required_keys.issubset(set(metrics.keys()))


def test_position_sizer_fixed(sample_ohlcv, sample_config):
    sizer = PositionSizer(sample_config["risk"])
    size = sizer.size(sample_ohlcv, point_value=50.0)
    assert size == 1
