#!/usr/bin/env python3
"""Start live signal runner for a futures instrument."""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from signals.config import load_config
from signals.strategy.zscore_reversion import ZScoreReversion
from signals.strategy.bb_reversion import BollingerReversion
from signals.risk.position_sizer import PositionSizer
from signals.runner.live_runner import LiveRunner


def main():
    parser = argparse.ArgumentParser(description="Live futures mean reversion signal runner")
    parser.add_argument("--instrument", default="ES")
    parser.add_argument("--strategy", default="zscore", choices=["zscore", "bollinger"])
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--interval", type=int, default=60, help="Poll interval in seconds")
    parser.add_argument("--once", action="store_true", help="Run once and exit (cron mode)")
    parser.add_argument("--log-file", default=None)
    parser.add_argument("--config-dir", default=None)
    args = parser.parse_args()

    log_level = logging.INFO
    handlers = [logging.StreamHandler(sys.stderr)]
    if args.log_file:
        handlers.append(logging.FileHandler(args.log_file))
    logging.basicConfig(level=log_level, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(message)s")

    config = load_config(args.config_dir)
    inst_cfg = config.get("instruments", {}).get(args.instrument)
    if not inst_cfg:
        print(f"ERROR: Instrument '{args.instrument}' not in config", file=sys.stderr)
        sys.exit(1)

    if args.strategy == "zscore":
        strategy = ZScoreReversion(config, args.instrument)
    else:
        strategy = BollingerReversion(config, args.instrument)

    sizer = PositionSizer(config["risk"])
    runner = LiveRunner(
        strategy=strategy,
        sizer=sizer,
        instrument_cfg=inst_cfg,
        poll_interval_seconds=args.interval,
        timeframe=args.timeframe,
    )
    runner.run_loop(once=args.once)


if __name__ == "__main__":
    main()
