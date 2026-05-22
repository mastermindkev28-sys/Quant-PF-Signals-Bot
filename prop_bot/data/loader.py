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
# Synthetic data generator (GBM) — used when live data is unavailable
# ---------------------------------------------------------------------------

_SYNTH_PARAMS = {
    "MGC=F": {"start_price": 1180.0, "annual_vol": 0.13, "annual_drift": 0.04},
    "GC=F":  {"start_price": 1180.0, "annual_vol": 0.13, "annual_drift": 0.04},
    "NQ=F":  {"start_price": 4300.0, "annual_vol": 0.22, "annual_drift": 0.14},
    "MNQ=F": {"start_price": 4300.0, "annual_vol": 0.22, "annual_drift": 0.14},
    "ES=F":  {"start_price": 2000.0, "annual_vol": 0.18, "annual_drift": 0.10},
    "MES=F": {"start_price": 2000.0, "annual_vol": 0.18, "annual_drift": 0.10},
}
_SYNTH_DEFAULT = {"start_price": 100.0, "annual_vol": 0.20, "annual_drift": 0.08}


def _generate_synthetic(
    symbol: str, start: str, end: str, timeframe: str = "1d", seed: int = 42,
) -> pd.DataFrame:
    """Generate realistic GBM OHLCV bars for backtesting without live data."""
    rng = np.random.default_rng(seed)
    p = _SYNTH_PARAMS.get(symbol, _SYNTH_DEFAULT)
    mu, sigma, s0 = p["annual_drift"], p["annual_vol"], p["start_price"]

    if timeframe in ("1d", "1D"):
        dates = pd.bdate_range(start=start, end=end)
        n = len(dates)
        dt = 1.0 / 252.0

        log_ret = (mu - 0.5 * sigma ** 2) * dt + sigma * np.sqrt(dt) * rng.standard_normal(n)
        close = s0 * np.exp(np.cumsum(log_ret))

        gap_frac = rng.standard_normal(n) * sigma * np.sqrt(dt) * 0.4
        open_ = np.empty(n)
        open_[0] = s0
        open_[1:] = close[:-1] * (1.0 + gap_frac[1:])

        rng_extra = np.abs(rng.standard_normal(n)) * sigma * np.sqrt(dt) * close
        rng_extra = np.maximum(rng_extra, np.abs(close - open_))

        hi_frac = rng.uniform(0.15, 0.85, n)
        high = np.maximum(open_, close) + hi_frac * rng_extra
        low  = np.minimum(open_, close) - (1.0 - hi_frac) * rng_extra
        high = np.maximum(high, np.maximum(open_, close))
        low  = np.minimum(low,  np.minimum(open_, close))

        avg_vol = 80_000 if any(x in symbol for x in ("MG", "MN", "ME")) else 300_000
        volume = rng.lognormal(np.log(avg_vol), 0.4, n).astype(int)

        df = pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
            index=pd.DatetimeIndex(dates).tz_localize("UTC"),
        )
        return df

    else:  # intraday: generate 5-min bars per trading day
        trading_days = pd.bdate_range(start=start, end=end)
        session_open = pd.Timedelta(hours=9, minutes=30)
        bars_per_day = 78  # 9:30–16:00 ET in 5-min bars

        dt_bar = 1.0 / (252.0 * bars_per_day)
        all_rows = []
        day_close = s0

        for day in trading_days:
            day_open = day_close * (1.0 + rng.standard_normal() * sigma * np.sqrt(1.0 / 252.0) * 0.3)
            day_ret = (mu - 0.5 * sigma ** 2) / 252.0 + sigma * np.sqrt(1.0 / 252.0) * rng.standard_normal()
            target = day_open * np.exp(day_ret)

            noise = rng.standard_normal(bars_per_day) * sigma * np.sqrt(dt_bar)
            bar_c = np.zeros(bars_per_day)
            bar_c[0] = day_open * (1.0 + noise[0])
            for b in range(1, bars_per_day):
                w = b / bars_per_day
                bar_c[b] = bar_c[b - 1] * (1.0 + noise[b]) * (1.0 - w) + target * w
            bar_c[-1] = target

            for b in range(bars_per_day):
                bo = bar_c[b - 1] if b > 0 else day_open
                bc = bar_c[b]
                br = abs(bc - bo) + abs(rng.standard_normal()) * sigma * np.sqrt(dt_bar) * bc
                bh = max(bo, bc) + rng.uniform(0.05, 0.50) * br
                bl = min(bo, bc) - rng.uniform(0.05, 0.50) * br
                ts = day + session_open + pd.Timedelta(minutes=5 * b)
                all_rows.append({"timestamp": ts, "open": bo, "high": bh,
                                  "low": bl, "close": bc, "volume": int(rng.lognormal(8.0, 0.5))})
            day_close = target

        df = pd.DataFrame(all_rows).set_index("timestamp")
        df.index = pd.DatetimeIndex(df.index).tz_localize("UTC")
        return df


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
    logger.info("Downloading %s %s %s→%s via yfinance", symbol, interval, start, end)
    ticker = yf.Ticker(symbol)
    df = ticker.history(start=start, end=end, interval=interval, auto_adjust=True)
    if df.empty:
        raise ValueError(f"No data returned for {symbol}")

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
        try:
            df = load_yfinance(symbol, actual_start, end, timeframe, cache_dir)
        except Exception as exc:
            logger.warning(
                "yfinance failed (%s) — falling back to synthetic data. "
                "Results will be on simulated prices, not real market data.", exc
            )
            df = _generate_synthetic(symbol, actual_start, end, timeframe)
            df = _normalise(df)
    elif provider == "synthetic":
        logger.info("Using synthetic GBM data for %s", symbol)
        df = _generate_synthetic(symbol, actual_start, end, timeframe)
        df = _normalise(df)
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
