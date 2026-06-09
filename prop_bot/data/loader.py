"""
Historical data loading with caching, gap filling, and split-adjustment handling.
Supports daily and intraday bars.
"""

import logging
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

REQUIRED_COLS = {"open", "high", "low", "close", "volume"}


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.lower().strip() for c in df.columns]
    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {missing}")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("DataFrame must have DatetimeIndex")
    df.index = (
        df.index.tz_localize("UTC")
        if df.index.tz is None
        else df.index.tz_convert("UTC")
    )
    df = df[list(REQUIRED_COLS)].sort_index()
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=["close"])
    return df


def _cache_path(cache_dir: str, symbol: str, timeframe: str, start: str, end: str) -> Path:
    tag = f"{symbol}_{timeframe}_{start}_{end}".replace("/", "-").replace(":", "")
    return Path(cache_dir) / f"{tag}.parquet"


# ---------------------------------------------------------------------------
# yfinance loader
# ---------------------------------------------------------------------------

def _yf_interval(timeframe: str) -> str:
    mapping = {
        "1d": "1d", "1D": "1d",
        "1h": "1h", "60min": "1h",
        "30min": "30m", "15min": "15m",
        "5min": "5m", "1min": "1m",
    }
    return mapping.get(timeframe, "1d")


def load_yfinance(
    symbol: str,
    start: str,
    end: str,
    timeframe: str = "1d",
    cache_dir: Optional[str] = None,
) -> pd.DataFrame:
    cache_path = _cache_path(cache_dir, symbol, timeframe, start, end) if cache_dir else None
    if cache_path and cache_path.exists():
        logger.debug("Cache hit: %s", cache_path)
        return pd.read_parquet(cache_path)

    try:
        import yfinance as yf
    except ImportError:
        raise ImportError("pip install yfinance")

    interval = _yf_interval(timeframe)

    # yfinance hard limits for intraday data:
    #   1m  → last  7 days only
    #   5m  → last 60 days only
    #   15m → last 60 days only
    #   1h  → last 730 days only
    # For backtesting beyond these windows, automatically fall back to daily bars.
    INTRADAY_INTERVALS = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"}
    if interval in INTRADAY_INTERVALS:
        from datetime import datetime, timezone
        req_start = pd.Timestamp(start)
        cutoffs = {"1m": 7, "5m": 60, "15m": 60, "30m": 60, "1h": 730, "60m": 730, "90m": 60}
        max_days = cutoffs.get(interval, 60)
        earliest_allowed = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=max_days)
        if req_start.tz is None:
            req_start = req_start.tz_localize("UTC")
        if req_start < earliest_allowed:
            logger.warning(
                "yfinance only provides %s data for the last %d days. "
                "Requested start %s is too old — falling back to daily (1d) bars for backtesting. "
                "For live signals the bot will use %s bars normally.",
                interval, max_days, start, interval,
            )
            interval = "1d"

    logger.info("Downloading %s %s %s→%s via yfinance", symbol, interval, start, end)
    ticker = yf.Ticker(symbol)
    df = ticker.history(start=start, end=end, interval=interval, auto_adjust=True)
    if df.empty:
        raise ValueError(
            f"No data returned for {symbol} ({interval}). "
            "Check the symbol is correct and the date range is valid."
        )

    df = df.rename(columns=str.lower)
    df.index = pd.to_datetime(df.index)
    df = _normalise(df)

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache_path)

    return df


# ---------------------------------------------------------------------------
# CSV / Parquet loader (local data, e.g. from Rithmic, NinjaTrader export)
# ---------------------------------------------------------------------------

def load_csv(
    path: str,
    symbol: str = "",
    timeframe: str = "1d",
    date_col: Optional[str] = None,
) -> pd.DataFrame:
    p = Path(path)
    if p.suffix == ".parquet":
        df = pd.read_parquet(p)
    else:
        df = pd.read_csv(p, parse_dates=True, index_col=date_col or 0)
    df.index = pd.to_datetime(df.index)
    return _normalise(df)


# ---------------------------------------------------------------------------
# Master loader
# ---------------------------------------------------------------------------

def load_data(
    symbol: str,
    start: str,
    end: str,
    timeframe: str = "1d",
    provider: str = "yfinance",
    cache_dir: Optional[str] = None,
    warmup_bars: int = 350,
) -> pd.DataFrame:
    """
    Load OHLCV data with enough warmup bars prepended for indicator initialisation.
    Returns DataFrame trimmed back to [start, end] after warmup bars are included.
    """
    # Estimate how much extra history to pull for warmup
    freq_days = {
        "1d": 1, "1h": 1/8, "30min": 1/16, "15min": 1/32, "5min": 1/96, "1min": 1/480
    }
    extra_days = int(warmup_bars * freq_days.get(timeframe, 1) * 1.5) + 30
    actual_start = (pd.Timestamp(start) - timedelta(days=extra_days)).strftime("%Y-%m-%d")

    if provider == "yfinance":
        df = load_yfinance(symbol, actual_start, end, timeframe, cache_dir)
    elif provider == "csv":
        raise ValueError("For CSV, call load_csv() directly")
    else:
        raise ValueError(f"Unknown provider: {provider}")

    logger.info("Loaded %d bars of %s %s", len(df), symbol, timeframe)
    return df


# ---------------------------------------------------------------------------
# Utility: add overnight gap and session flags
# ---------------------------------------------------------------------------

def add_session_flags(df: pd.DataFrame, timeframe: str = "1d") -> pd.DataFrame:
    """Add boolean columns: is_first_bar, is_last_bar (per session/day)."""
    if timeframe == "1d":
        df["is_first_bar"] = True
        df["is_last_bar"] = True
        return df

    df = df.copy()
    dates = df.index.normalize()
    df["date"] = dates
    df["is_first_bar"] = ~dates.duplicated(keep="first")
    df["is_last_bar"] = ~dates.duplicated(keep="last")
    df.drop(columns=["date"], inplace=True)
    return df


def add_overnight_gap(df: pd.DataFrame) -> pd.DataFrame:
    """Add overnight_gap column = today's open - yesterday's close."""
    df = df.copy()
    df["overnight_gap"] = df["open"] - df["close"].shift(1)
    return df
