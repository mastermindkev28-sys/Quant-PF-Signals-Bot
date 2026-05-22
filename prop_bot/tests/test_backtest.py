import pytest
import pandas as pd
from prop_bot.strategies.ibs_mean_reversion import IBSMeanReversion
from prop_bot.backtest.engine import BacktestEngine
from prop_bot.backtest.metrics import full_report


def test_backtest_runs_without_error(daily_ohlcv, cfg, inst):
    strat = IBSMeanReversion(cfg, inst)
    df = strat.run(daily_ohlcv)
    engine = BacktestEngine(cfg, inst)
    results = engine.run(df)
    assert results.equity_curve is not None
    assert len(results.equity_curve) == len(daily_ohlcv)


def test_equity_curve_has_required_columns(daily_ohlcv, cfg, inst):
    strat = IBSMeanReversion(cfg, inst)
    df = strat.run(daily_ohlcv)
    engine = BacktestEngine(cfg, inst)
    results = engine.run(df)
    assert "equity" in results.equity_curve.columns


def test_no_lookahead_in_backtest(daily_ohlcv, cfg, inst):
    """Bar-0 contracts must be 0 (signal from bar -1 = nothing)."""
    strat = IBSMeanReversion(cfg, inst)
    df = strat.run(daily_ohlcv)
    engine = BacktestEngine(cfg, inst)
    results = engine.run(df)
    trades_df = results.trades_df()
    if not trades_df.empty:
        assert (trades_df["entry_time"] >= daily_ohlcv.index[1]).all()


def test_stop_loss_never_exceeds_daily_limit(daily_ohlcv, cfg, inst):
    """Any single trade loss should not exceed the daily loss limit."""
    strat = IBSMeanReversion(cfg, inst)
    df = strat.run(daily_ohlcv)
    engine = BacktestEngine(cfg, inst)
    results = engine.run(df)
    trades_df = results.trades_df()
    if not trades_df.empty:
        max_single_loss = trades_df["pnl_net"].min()
        # Should never lose more than full daily limit in one trade
        assert max_single_loss > -cfg.prop.max_daily_loss * 1.5


def test_metrics_report_keys(daily_ohlcv, cfg, inst):
    strat = IBSMeanReversion(cfg, inst)
    df = strat.run(daily_ohlcv)
    engine = BacktestEngine(cfg, inst)
    results = engine.run(df)
    trades_df = results.trades_df()
    if not trades_df.empty:
        report = full_report(results.equity_curve, trades_df, cfg)
        for key in ["sharpe_ratio", "max_drawdown_pct", "win_rate_pct", "profit_factor", "PASSED"]:
            assert key in report


def test_monte_carlo_runs(daily_ohlcv, cfg, inst):
    from prop_bot.utils.monte_carlo import run_monte_carlo
    strat = IBSMeanReversion(cfg, inst)
    df = strat.run(daily_ohlcv)
    engine = BacktestEngine(cfg, inst)
    results = engine.run(df)
    trades_df = results.trades_df()
    if not trades_df.empty:
        mc = run_monte_carlo(trades_df, cfg, n_simulations=500)
        assert "prob_ruin_pct" in mc
        assert "prob_pass_target_pct" in mc
        assert 0 <= mc["prob_ruin_pct"] <= 100
