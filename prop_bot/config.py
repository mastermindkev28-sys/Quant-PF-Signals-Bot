"""
Central configuration for all prop_bot modules.
Override any value via environment variables or a local config.yaml.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import os
import yaml
from pathlib import Path


# ---------------------------------------------------------------------------
# Instrument definitions
# ---------------------------------------------------------------------------

@dataclass
class InstrumentConfig:
    symbol: str           # yfinance / data-provider ticker
    tradovate_symbol: str # broker symbol
    exchange: str
    point_value: float    # dollar value of 1 full point move
    tick_size: float      # minimum price increment
    tick_value: float     # dollar value of 1 tick
    margin: float         # approx intraday margin (USD)
    asset_class: str = "futures"

INSTRUMENTS: Dict[str, InstrumentConfig] = {
    "GC": InstrumentConfig(
        symbol="GC=F", tradovate_symbol="GCM5",
        exchange="COMEX", point_value=100.0,
        tick_size=0.10, tick_value=10.0, margin=8_000,
    ),
    "MGC": InstrumentConfig(
        symbol="MGC=F", tradovate_symbol="MGCM5",
        exchange="COMEX", point_value=10.0,
        tick_size=0.10, tick_value=1.0, margin=800,
    ),
    "NQ": InstrumentConfig(
        symbol="NQ=F", tradovate_symbol="NQM5",
        exchange="CME", point_value=20.0,
        tick_size=0.25, tick_value=5.0, margin=16_000,
    ),
    "MNQ": InstrumentConfig(
        symbol="MNQ=F", tradovate_symbol="MNQM5",
        exchange="CME", point_value=2.0,
        tick_size=0.25, tick_value=0.50, margin=1_600,
    ),
    "ES": InstrumentConfig(
        symbol="ES=F", tradovate_symbol="ESM5",
        exchange="CME", point_value=50.0,
        tick_size=0.25, tick_value=12.50, margin=12_500,
    ),
    "MES": InstrumentConfig(
        symbol="MES=F", tradovate_symbol="MESM5",
        exchange="CME", point_value=5.0,
        tick_size=0.25, tick_value=1.25, margin=1_250,
    ),
}


# ---------------------------------------------------------------------------
# IBS Mean Reversion strategy parameters
# ---------------------------------------------------------------------------

@dataclass
class IBSConfig:
    # --- Signal ---
    range_sma_period: int = 25       # SMA window for avg daily range (high-low)
    ibs_entry_threshold: float = 0.3 # IBS < this triggers long consideration
    highest_high_lookback: int = 10  # window for highest(high, N)
    band_multiplier: float = 2.5     # lower_band = highest_high - mult * avg_range
    trend_sma_period: int = 300      # trend filter: no longs below 300-day SMA

    # --- Exit ---
    exit_above_prev_high: bool = True  # exit if close > prev day high
    exit_below_trend: bool = True      # exit if close < 300 SMA
    max_holding_days: int = 10         # hard exit after N days

    # --- Timeframe ---
    timeframe: str = "1d"
    session: str = "daily"


# ---------------------------------------------------------------------------
# Dual Thrust breakout strategy parameters
# ---------------------------------------------------------------------------

@dataclass
class DualThrustConfig:
    # --- Signal ---
    lookback: int = 4          # bars for range calculation
    k_upper: float = 0.5       # upper multiplier
    k_lower: float = 0.5       # lower multiplier
    allow_short: bool = True   # enable short side

    # --- Session ---
    timeframe: str = "5min"
    session_start: str = "09:30"  # market open (ET)
    session_end: str = "15:45"    # hard close before 16:00

    # --- Exit ---
    exit_eod: bool = True          # always flatten by session_end
    reverse_on_opposite: bool = True  # flip when opposite signal triggers


# ---------------------------------------------------------------------------
# Prop firm rule sets
# ---------------------------------------------------------------------------

@dataclass
class PropFirmRules:
    name: str = "Topstep"
    account_size: float = 50_000.0

    # Drawdown
    max_daily_loss: float = 1_000.0       # hard stop — bot halts for the day
    max_trailing_drawdown: float = 2_000.0 # trailing from peak equity
    max_total_loss: float = 2_500.0        # absolute floor from starting equity

    # Consistency
    max_single_day_profit_pct: float = 0.40  # no day > 40% of total profit
    min_trading_days: int = 10               # evaluation period minimum

    # Position / leverage
    max_contracts: int = 3       # max simultaneous contracts
    no_overnight: bool = True    # must be flat at session end
    no_news_trading: bool = False # optional: avoid ±5min around major events

    # Evaluation vs funded
    phase: str = "evaluation"   # "evaluation" | "funded"

PROP_PRESETS: Dict[str, PropFirmRules] = {
    "topstep_50k": PropFirmRules(
        name="Topstep", account_size=50_000,
        max_daily_loss=1_000, max_trailing_drawdown=2_000,
        max_total_loss=2_500, max_contracts=3,
        min_trading_days=10,
    ),
    "topstep_100k": PropFirmRules(
        name="Topstep", account_size=100_000,
        max_daily_loss=3_000, max_trailing_drawdown=4_500,
        max_total_loss=5_000, max_contracts=6,
        min_trading_days=10,
    ),
    "lucid_25k": PropFirmRules(
        name="Lucid", account_size=25_000,
        max_daily_loss=500, max_trailing_drawdown=1_000,
        max_total_loss=1_500, max_contracts=2,
    ),
    "topstepx_50k": PropFirmRules(
        name="TopstepX", account_size=50_000,
        max_daily_loss=1_000, max_trailing_drawdown=2_500,
        max_total_loss=2_500, max_contracts=5,
    ),
    # No-minimum-days firms (best for fast pass)
    "apex_50k": PropFirmRules(
        name="Apex", account_size=50_000,
        max_daily_loss=1_000, max_trailing_drawdown=2_500,
        max_total_loss=2_500, max_contracts=5,
        min_trading_days=0,
    ),
    "apex_100k": PropFirmRules(
        name="Apex", account_size=100_000,
        max_daily_loss=2_000, max_trailing_drawdown=3_000,
        max_total_loss=3_000, max_contracts=10,
        min_trading_days=0,
    ),
    "mff_50k": PropFirmRules(            # MyFundedFutures
        name="MyFundedFutures", account_size=50_000,
        max_daily_loss=1_000, max_trailing_drawdown=2_000,
        max_total_loss=2_000, max_contracts=5,
        min_trading_days=0,
    ),
    "tradeday_50k": PropFirmRules(
        name="TradeDay", account_size=50_000,
        max_daily_loss=1_000, max_trailing_drawdown=2_000,
        max_total_loss=2_000, max_contracts=5,
        min_trading_days=0,
    ),
}


# ---------------------------------------------------------------------------
# Risk / position sizing
# ---------------------------------------------------------------------------

@dataclass
class RiskConfig:
    risk_per_trade_pct: float = 0.01     # 1% of account per trade
    atr_period: int = 14
    atr_stop_multiplier: float = 1.5     # stop = entry ± mult * ATR
    profit_target_r: float = 0.0         # 0 = no fixed target; 2.0 = 2R target
    max_correlated_positions: int = 2
    use_kelly: bool = False              # Kelly-lite sizing (capped at 25%)
    kelly_fraction: float = 0.25        # fraction of full Kelly to use
    commission_per_contract: float = 2.25  # round-turn RT commission
    slippage_ticks: int = 1             # 1-tick slippage each side
    # Aggressive / fast-pass mode
    daily_profit_target: float = 0.0    # halt trading once day P&L >= this ($)
    use_max_contracts: bool = False     # always size at prop firm max contracts


# ---------------------------------------------------------------------------
# Data configuration
# ---------------------------------------------------------------------------

@dataclass
class DataConfig:
    provider: str = "yfinance"           # yfinance | csv | tradovate_hist
    cache_dir: str = "prop_bot/data/cache"
    default_start: str = "2015-01-01"
    default_end: str = "2025-01-01"
    warmup_bars: int = 350               # extra bars for indicator warmup


# ---------------------------------------------------------------------------
# Live trading
# ---------------------------------------------------------------------------

@dataclass
class LiveConfig:
    broker: str = "tradovate"
    tradovate_demo: bool = True          # always start on demo!
    tradovate_cid: str = os.getenv("TRADOVATE_CID", "")
    tradovate_secret: str = os.getenv("TRADOVATE_SECRET", "")
    tradovate_username: str = os.getenv("TRADOVATE_USERNAME", "")
    tradovate_password: str = os.getenv("TRADOVATE_PASSWORD", "")
    poll_interval_seconds: int = 30
    heartbeat_interval: int = 300


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

@dataclass
class AlertConfig:
    telegram_token: str = os.getenv("TELEGRAM_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    alert_on_entry: bool = True
    alert_on_exit: bool = True
    alert_on_daily_loss_limit: bool = True
    alert_on_error: bool = True


# ---------------------------------------------------------------------------
# Master config
# ---------------------------------------------------------------------------

@dataclass
class BotConfig:
    instrument: str = "MGC"
    strategy: str = "ibs"              # "ibs" | "dual_thrust"
    ibs: IBSConfig = field(default_factory=IBSConfig)
    dual_thrust: DualThrustConfig = field(default_factory=DualThrustConfig)
    prop: PropFirmRules = field(default_factory=lambda: PropFirmRules())
    risk: RiskConfig = field(default_factory=RiskConfig)
    data: DataConfig = field(default_factory=DataConfig)
    live: LiveConfig = field(default_factory=LiveConfig)
    alerts: AlertConfig = field(default_factory=AlertConfig)
    log_level: str = "INFO"
    results_dir: str = "prop_bot/results"


def load_config(path: str = "prop_bot/bot_config.yaml") -> BotConfig:
    """Load config from YAML, falling back to defaults for missing keys."""
    cfg = BotConfig()
    p = Path(path)
    if not p.exists():
        return cfg

    with open(p) as f:
        raw = yaml.safe_load(f) or {}

    if "instrument" in raw:
        cfg.instrument = raw["instrument"]
    if "strategy" in raw:
        cfg.strategy = raw["strategy"]
    if "prop_preset" in raw:
        preset = PROP_PRESETS.get(raw["prop_preset"])
        if preset:
            cfg.prop = preset
    # Allow flat override of any sub-config field
    for section, cls_field in [("ibs", cfg.ibs), ("risk", cfg.risk),
                                ("data", cfg.data), ("live", cfg.live)]:
        if section in raw:
            for k, v in raw[section].items():
                if hasattr(cls_field, k):
                    setattr(cls_field, k, v)
    return cfg
