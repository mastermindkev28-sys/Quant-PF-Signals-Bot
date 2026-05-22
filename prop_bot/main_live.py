#!/usr/bin/env python3
"""
Live trading entry point.

CRITICAL: You MUST complete ALL of these before running live:
  [ ] Run backtest >= 5 years, review all metrics
  [ ] WFO efficiency >= 50%
  [ ] Monte Carlo ruin probability < 10%
  [ ] Paper traded on DEMO for >= 2 weeks
  [ ] Verified Tradovate credentials and account connection
  [ ] Confirmed prop firm allows automated trading
  [ ] tradovate_demo=True in config (NEVER go live without this gate)

Usage:
  # Demo mode (default)
  python prop_bot/main_live.py --instrument MGC --strategy ibs --demo

  # Live mode (requires explicit --live flag AND confirmation prompt)
  python prop_bot/main_live.py --instrument MGC --strategy ibs --live
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from prop_bot.config import BotConfig, INSTRUMENTS, PROP_PRESETS, load_config
from prop_bot.live.trader import LiveTrader


def main():
    parser = argparse.ArgumentParser(description="PropBot live trader")
    parser.add_argument("--instrument", default="MGC", choices=list(INSTRUMENTS.keys()))
    parser.add_argument("--strategy", default="ibs", choices=["ibs", "dual_thrust"])
    parser.add_argument("--prop", default="topstep_50k", choices=list(PROP_PRESETS.keys()))
    parser.add_argument("--config", default=None)
    parser.add_argument("--demo", action="store_true", default=True,
                        help="Run on demo account (default: True)")
    parser.add_argument("--live", action="store_true", default=False,
                        help="Run on LIVE account (requires explicit confirmation)")
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--log-file", default=None)
    args = parser.parse_args()

    handlers = [logging.StreamHandler()]
    if args.log_file:
        handlers.append(logging.FileHandler(args.log_file))
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )

    cfg = load_config(args.config) if args.config else BotConfig()
    cfg.instrument = args.instrument
    cfg.strategy = args.strategy
    cfg.prop = PROP_PRESETS[args.prop]
    cfg.live.tradovate_demo = not args.live

    if args.live:
        print("\n" + "!" * 60)
        print("  ⚠  LIVE TRADING MODE")
        print("  Real money will be at risk.")
        print("!" * 60)
        confirm = input("\nType 'YES I UNDERSTAND' to proceed: ").strip()
        if confirm != "YES I UNDERSTAND":
            print("Aborted.")
            return

    mode = "DEMO" if cfg.live.tradovate_demo else "LIVE"
    print(f"\nStarting PropBot [{mode}]")
    print(f"  Instrument: {args.instrument}")
    print(f"  Strategy:   {args.strategy.upper()}")
    print(f"  Prop Firm:  {cfg.prop.name} ${cfg.prop.account_size:,.0f}")
    print(f"  Daily Loss Limit: ${cfg.prop.max_daily_loss:,.0f}")
    print(f"  Max Contracts:    {cfg.prop.max_contracts}")
    print()

    trader = LiveTrader(cfg)
    trader.start()


if __name__ == "__main__":
    main()
