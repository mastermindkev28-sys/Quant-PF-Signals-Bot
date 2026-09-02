# Quant PF Signals Bot

A Python futures mean reversion trading bot that generates quantitative signals for ES, NQ, CL, and GC futures.

## Features

- **Z-Score Mean Reversion** — rolling z-score with configurable entry/exit thresholds
- **Bollinger Band Reversion** — band-touch entries with optional squeeze filter
- **Multi-instrument** — ES, NQ, CL, GC with per-instrument parameter overrides
- **Backtesting engine** — vectorized, no-lookahead, with Sharpe / drawdown / win-rate metrics
- **Live signal runner** — polling loop emitting JSON-lines signals; cron-compatible single-shot mode
- **Instrument-aware position sizing** — fixed, fractional (ATR-based), or volatility-target

## Quickstart

```bash
pip install -r requirements.txt
cp .env.example .env  # fill in any API keys if needed

# Backtest ES on z-score strategy (pulls data via yfinance)
python scripts/run_backtest.py --instrument ES --strategy zscore --start 2020-01-01 --end 2024-12-31 --plot

# Run all instruments
python scripts/run_backtest.py --instrument all --strategy bollinger

# Live signal (single-shot, cron-friendly)
python scripts/run_live.py --instrument NQ --strategy zscore --once

# Live signal loop (60-second poll)
python scripts/run_live.py --instrument CL --strategy zscore --interval 60
```

## Live Signal Output Format

JSON-lines to stdout:

```json
{
  "timestamp": "2024-03-15T14:30:00+00:00",
  "instrument": "ES",
  "symbol": "ES=F",
  "strategy": "ZScoreReversion",
  "signal": 1,
  "signal_strength": -2.34,
  "suggested_contracts": 2,
  "entry_price_ref": 5123.25,
  "stop_price": 5089.50
}
```

`signal`: `1` = long, `-1` = short, `0` = flat.

## TradingView Indicator

`tradingview/h1_range_break_choch_ifvg.pine` — Pine Script v6 overlay that marks the high
and low of the H1 candle opening after 05:30 PST (06:00–07:00 America/Los_Angeles), then
labels the reversal sequence that follows: **range break → change of character → inverse
fair value gap**, with alerts on each step. See `tradingview/README.md` for install and
tuning.

## Project Structure

```
config/           # instruments.yaml, strategy.yaml, risk.yaml
signals/
  data/           # DataLoader base, CsvLoader, LiveFeed (yfinance)
  indicators/     # zscore, bollinger, atr
  strategy/       # ZScoreReversion, BollingerReversion
  risk/           # PositionSizer (fixed / fractional / vol-target)
  backtest/       # Backtester engine + metrics
  runner/         # LiveRunner polling loop
scripts/          # run_backtest.py, run_live.py
tradingview/      # Pine Script indicators
tests/            # pytest suite with synthetic AR(1) data
```

## Configuration

Edit `config/instruments.yaml` to add instruments or tweak `tick_size` / `point_value`. Strategy thresholds live in `config/strategy.yaml`. Risk limits and sizing method in `config/risk.yaml`.

Per-instrument strategy overrides in `instruments.yaml` take precedence over global `strategy.yaml` values.

## Running Tests

```bash
pytest tests/ -v
```

## Data Sources

Default: **yfinance** (no API key required, works for continuous futures like `ES=F`).

To use local CSV files, place them in `data/raw/` named `<SYMBOL>_*.csv` and pass `--data-dir data/raw` to `run_backtest.py`.
