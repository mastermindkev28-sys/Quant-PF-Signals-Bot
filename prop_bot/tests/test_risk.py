import pytest
from prop_bot.risk.manager import RiskManager


def test_can_trade_initially(cfg, inst):
    rm = RiskManager(cfg, inst)
    rm.start_day("2024-01-02")
    ok, reason = rm.can_trade()
    assert ok
    assert reason == "OK"


def test_halt_on_daily_loss(cfg, inst):
    rm = RiskManager(cfg, inst)
    rm.start_day("2024-01-02")
    # Simulate a big loss exceeding daily limit
    rm.state.day.gross_pnl = -cfg.prop.max_daily_loss - 1
    ok, reason = rm.can_trade()
    assert not ok
    assert "Daily loss" in reason


def test_halt_on_trailing_drawdown(cfg, inst):
    rm = RiskManager(cfg, inst)
    rm.start_day("2024-01-02")
    rm.state.peak_equity = cfg.prop.account_size
    rm.state.equity = cfg.prop.account_size - cfg.prop.max_trailing_drawdown - 100
    ok, reason = rm.can_trade()
    assert not ok


def test_position_size_respects_max_contracts(cfg, inst):
    rm = RiskManager(cfg, inst)
    rm.start_day("2024-01-02")
    size = rm.size_position(entry_price=1950.0, stop_price=1930.0, signal_strength=1.0)
    assert size <= cfg.prop.max_contracts
    assert size >= 1


def test_position_size_1pct_risk(cfg, inst):
    rm = RiskManager(cfg, inst)
    rm.start_day("2024-01-02")
    # $500 account risk at 1%, $20 stop on MGC ($10/pt) = ~25 contracts → capped at 3
    size = rm.size_position(entry_price=1950.0, stop_price=1948.0, signal_strength=1.0)
    assert 1 <= size <= cfg.prop.max_contracts


def test_record_trade_updates_equity(cfg, inst):
    rm = RiskManager(cfg, inst)
    rm.start_day("2024-01-02")
    initial = rm.state.equity
    rm.record_trade(pnl_gross=500.0, contracts=1)
    assert rm.state.equity > initial  # net > 0 after comm/slip


def test_record_loss_updates_daily_pnl(cfg, inst):
    rm = RiskManager(cfg, inst)
    rm.start_day("2024-01-02")
    rm.record_trade(pnl_gross=-300.0, contracts=1)
    assert rm.state.day.gross_pnl < 0
