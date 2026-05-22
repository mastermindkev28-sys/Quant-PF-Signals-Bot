import pandas as pd
import pytest
from prop_bot.strategies.ibs_mean_reversion import IBSMeanReversion


def test_ibs_signal_columns(daily_ohlcv, cfg, inst):
    strat = IBSMeanReversion(cfg, inst)
    result = strat.run(daily_ohlcv)
    for col in ["signal", "stop_price", "signal_strength"]:
        assert col in result.columns


def test_ibs_signal_valid_values(daily_ohlcv, cfg, inst):
    strat = IBSMeanReversion(cfg, inst)
    result = strat.run(daily_ohlcv)
    assert set(result["signal"].unique()).issubset({-1, 0, 1})


def test_ibs_stop_below_entry_for_long(daily_ohlcv, cfg, inst):
    strat = IBSMeanReversion(cfg, inst)
    result = strat.run(daily_ohlcv)
    entries = result[result["signal"] == 1]
    valid_stops = entries.dropna(subset=["stop_price"])
    assert (valid_stops["stop_price"] < valid_stops["close"]).all()


def test_no_lookahead_no_future_signals(daily_ohlcv, cfg, inst):
    # Trim to first 100 bars — signals should not differ from full run
    strat_full = IBSMeanReversion(cfg, inst)
    result_full = strat_full.run(daily_ohlcv)

    strat_trim = IBSMeanReversion(cfg, inst)
    result_trim = strat_trim.run(daily_ohlcv.iloc[:100])

    # Signals on bar 50 must be identical whether we see future or not
    pd.testing.assert_series_equal(
        result_full["signal"].iloc[:100],
        result_trim["signal"].iloc[:100],
        check_names=False,
    )
