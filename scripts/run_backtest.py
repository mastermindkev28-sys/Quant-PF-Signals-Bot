#!/usr/bin/env python3
"""Run backtest for one or more futures instruments."""

import argparse
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from signals.config import load_config
from signals.data.live_feed import LiveFeed
from signals.data.csv_loader import CsvLoader
from signals.strategy.zscore_reversion import ZScoreReversion
from signals.strategy.bb_reversion import BollingerReversion
from signals.strategy.base import Strategy
from signals.risk.position_sizer import PositionSizer
from signals.backtest.engine import Backtester
from signals.backtest.metrics import compute_metrics, plot_equity_curve


def build_strategy(name: str, config: dict, instrument: str) -> Strategy:
    if name == "zscore":
        return ZScoreReversion(config, instrument)
    if name == "bollinger":
        return BollingerReversion(config, instrument)
    raise ValueError(f"Unknown strategy: {name}")


def run_backtest(instrument: str, strategy_name: str, start: str, end: str,
                 config: dict, data_dir: str, output_dir: str, plot: bool):
    inst_cfg = config.get("instruments", {}).get(instrument)
    if not inst_cfg:
        print(f"[SKIP] Instrument '{instrument}' not found in instruments.yaml")
        return

    symbol = inst_cfg["symbol"]
    point_value = inst_cfg.get("point_value", 1.0)

    if data_dir and Path(data_dir).exists():
        loader = CsvLoader(data_dir)
    else:
        loader = LiveFeed()

    print(f"Fetching {symbol} ({start} -> {end})...")
    ohlcv = loader.fetch(symbol, start, end)

    strategy = build_strategy(strategy_name, config, instrument)
    sizer = PositionSizer(config["risk"])
    bt = Backtester(strategy, sizer, point_value)
    results = bt.run(ohlcv)

    metrics = compute_metrics(results)
    print(f"\n{'='*50}")
    print(f"  {instrument} | {strategy_name.upper()} | {start} -> {end}")
    print(f"{'='*50}")
    for k, v in metrics.items():
        print(f"  {k:<25} {v}")
    print()

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    csv_path = Path(output_dir) / f"{instrument}_{strategy_name}_{start}_{end}.csv"
    results.to_csv(csv_path)
    print(f"  Trade log saved: {csv_path}")

    if plot:
        img_path = str(csv_path).replace(".csv", ".png")
        plot_equity_curve(results, title=f"{instrument} {strategy_name}", save_path=img_path)
        print(f"  Equity curve: {img_path}")


def main():
    parser = argparse.ArgumentParser(description="Run futures mean reversion backtest")
    parser.add_argument("--instrument", default="ES", help="Instrument key (ES, NQ, CL, GC) or 'all'")
    parser.add_argument("--strategy", default="zscore", choices=["zscore", "bollinger"])
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2024-12-31")
    parser.add_argument("--data-dir", default=None, help="Local CSV/Parquet data directory (optional)")
    parser.add_argument("--output-dir", default="results")
    parser.add_argument("--config-dir", default=None)
    parser.add_argument("--plot", action="store_true", help="Save equity curve plot")
    args = parser.parse_args()

    config = load_config(args.config_dir)
    instruments = list(config.get("instruments", {}).keys()) if args.instrument == "all" else [args.instrument]

    for inst in instruments:
        run_backtest(inst, args.strategy, args.start, args.end,
                     config, args.data_dir, args.output_dir, args.plot)


if __name__ == "__main__":
    main()
