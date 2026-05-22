#!/usr/bin/env python3
"""
Main backtest entry point.

Usage examples:
  # IBS on MGC (micro gold) — Topstep 50K rules
  python prop_bot/main_backtest.py --instrument MGC --strategy ibs \
      --start 2015-01-01 --end 2025-01-01 --prop topstep_50k --plot

  # Dual Thrust on MNQ (micro NASDAQ)
  python prop_bot/main_backtest.py --instrument MNQ --strategy dual_thrust \
      --start 2018-01-01 --end 2025-01-01 --prop topstep_50k

  # Full pipeline: backtest + WFO + Monte Carlo
  python prop_bot/main_backtest.py --instrument MGC --strategy ibs \
      --start 2015-01-01 --end 2025-01-01 --prop topstep_50k \
      --wfo --monte-carlo --plot
"""

import argparse
import logging
import sys
from pathlib import Path

# Ensure package root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from prop_bot.config import BotConfig, INSTRUMENTS, PROP_PRESETS, load_config
from prop_bot.data.loader import load_data
from prop_bot.backtest.engine import BacktestEngine
from prop_bot.backtest.metrics import full_report, print_report
from prop_bot.utils.monte_carlo import run_monte_carlo, print_mc_report
from prop_bot.utils.plotting import plot_equity_curve, plot_monthly_heatmap, plot_ibs_signals


def build_strategy(cfg: BotConfig, inst_cfg):
    if cfg.strategy == "ibs":
        from prop_bot.strategies.ibs_mean_reversion import IBSMeanReversion
        return IBSMeanReversion(cfg, inst_cfg)
    elif cfg.strategy == "dual_thrust":
        from prop_bot.strategies.dual_thrust import DualThrustBreakout
        return DualThrustBreakout(cfg, inst_cfg)
    raise ValueError(f"Unknown strategy: {cfg.strategy}")


def main():
    parser = argparse.ArgumentParser(
        description="Futures prop trading bot backtester",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--instrument", default="MGC",
                        choices=list(INSTRUMENTS.keys()),
                        help="Futures instrument (default: MGC)")
    parser.add_argument("--strategy", default="ibs",
                        choices=["ibs", "dual_thrust"],
                        help="Strategy to run (default: ibs)")
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default="2025-01-01")
    parser.add_argument("--prop", default="topstep_50k",
                        choices=list(PROP_PRESETS.keys()),
                        help="Prop firm preset")
    parser.add_argument("--config", default=None,
                        help="Path to bot_config.yaml")
    parser.add_argument("--wfo", action="store_true",
                        help="Run Walk-Forward Optimisation")
    parser.add_argument("--monte-carlo", action="store_true",
                        help="Run Monte Carlo analysis")
    parser.add_argument("--plot", action="store_true",
                        help="Generate and save charts")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Build config
    cfg = load_config(args.config) if args.config else BotConfig()
    cfg.instrument = args.instrument
    cfg.strategy = args.strategy
    cfg.prop = PROP_PRESETS[args.prop]
    cfg.data.default_start = args.start
    cfg.data.default_end = args.end

    inst = INSTRUMENTS[args.instrument]
    Path(cfg.results_dir).mkdir(parents=True, exist_ok=True)
    cache_dir = cfg.data.cache_dir

    print(f"\n{'='*60}")
    print(f"  PropBot Backtest")
    print(f"  Instrument : {args.instrument}  ({inst.symbol})")
    print(f"  Strategy   : {args.strategy.upper()}")
    print(f"  Period     : {args.start} → {args.end}")
    print(f"  Prop Firm  : {cfg.prop.name} ${cfg.prop.account_size:,.0f}")
    print(f"{'='*60}\n")

    # ---- Load data ----
    timeframe = cfg.ibs.timeframe if args.strategy == "ibs" else cfg.dual_thrust.timeframe
    print(f"Loading {inst.symbol} {timeframe} data...")
    df = load_data(
        inst.symbol, args.start, args.end,
        timeframe=timeframe,
        provider=cfg.data.provider,
        cache_dir=cache_dir,
        warmup_bars=cfg.data.warmup_bars,
    )
    print(f"  {len(df)} bars loaded ({df.index[0].date()} → {df.index[-1].date()})")

    # ---- Build strategy and run signals ----
    strategy = build_strategy(cfg, inst)
    print(f"  Strategy: {strategy.describe()}")
    print("\nPreparing signals...")
    df_signals = strategy.run(df)

    n_entries = int((df_signals["signal"] == 1).sum())
    print(f"  Entry signals: {n_entries}")

    if n_entries == 0:
        print("\n⚠  No entry signals generated. Check parameters vs data range.")
        return

    # ---- Backtest ----
    print("\nRunning backtest...")
    engine = BacktestEngine(cfg, inst)
    results = engine.run(df_signals)
    trades_df = results.trades_df()
    print(f"  Trades executed: {len(trades_df)}")

    # ---- Metrics ----
    report = full_report(results.equity_curve, trades_df, cfg)
    print_report(report)

    # Save trade log
    trades_path = Path(cfg.results_dir) / f"{args.instrument}_{args.strategy}_trades.csv"
    trades_df.to_csv(trades_path, index=False)
    print(f"Trade log: {trades_path}")

    # ---- Plots ----
    if args.plot:
        print("\nGenerating charts...")
        plot_equity_curve(
            results.equity_curve, trades_df,
            title=f"{args.instrument} {args.strategy.upper()} | {args.start}→{args.end}",
            save_path=f"{cfg.results_dir}/{args.instrument}_{args.strategy}_equity.png",
        )
        plot_monthly_heatmap(
            trades_df,
            save_path=f"{cfg.results_dir}/{args.instrument}_{args.strategy}_heatmap.png",
        )
        if args.strategy == "ibs":
            # Plot last 2 years of signals
            cutoff = df_signals.index[-1] - pd.DateOffset(years=2)
            plot_ibs_signals(
                df_signals[df_signals.index >= cutoff],
                save_path=f"{cfg.results_dir}/{args.instrument}_ibs_signals.png",
            )
        print(f"Charts saved to {cfg.results_dir}/")

    # ---- Walk-Forward Optimisation ----
    if args.wfo:
        print("\nRunning Walk-Forward Optimisation...")
        from prop_bot.backtest.walk_forward import run_walk_forward

        # IBS parameter grid — keep small to avoid overfit
        param_grid = {
            "band_multiplier": [2.0, 2.5, 3.0],
            "range_sma_period": [20, 25, 30],
        }

        def _wfo_run(data, params):
            """Closure for WFO optimisation loop."""
            _cfg = BotConfig()
            _cfg.instrument = args.instrument
            _cfg.strategy = args.strategy
            _cfg.prop = cfg.prop
            _cfg.ibs.band_multiplier = params.get("band_multiplier", 2.5)
            _cfg.ibs.range_sma_period = params.get("range_sma_period", 25)
            _cfg.risk = cfg.risk

            _inst = INSTRUMENTS[args.instrument]
            _strat = build_strategy(_cfg, _inst)
            _df = _strat.run(data)
            _engine = BacktestEngine(_cfg, _inst)
            _res = _engine.run(_df)
            return _res.equity_curve

        run_walk_forward(df_signals, param_grid, _wfo_run,
                         is_bars=500, oos_bars=125, step_bars=125)

    # ---- Monte Carlo ----
    if args.monte_carlo:
        print("\nRunning Monte Carlo analysis...")
        from prop_bot.utils.monte_carlo import resample_trades
        mc = run_monte_carlo(trades_df, cfg, n_simulations=5000)
        print_mc_report(mc)

        if args.plot:
            from prop_bot.utils.plotting import plot_monte_carlo
            mc_paths = resample_trades(trades_df["pnl_net"], n_simulations=1000)
            plot_monte_carlo(
                mc_paths,
                start_equity=cfg.prop.account_size,
                prop_target=cfg.prop.account_size * 0.08,
                ruin_floor=-cfg.prop.max_total_loss,
                save_path=f"{cfg.results_dir}/{args.instrument}_monte_carlo.png",
            )

    # ---- Overfitting warnings ----
    _print_overfitting_warnings(report, args)

    print(f"\nDone. Results saved to {cfg.results_dir}/")


def _print_overfitting_warnings(report: dict, args):
    warnings = []

    n = report.get("total_trades", 0)
    if n < 30:
        warnings.append(f"Only {n} trades — insufficient sample size for statistical significance")

    pf = report.get("profit_factor", 0)
    if pf > 5.0:
        warnings.append(f"Profit factor {pf:.2f} is very high — likely overfit or insufficient trades")

    sharpe = report.get("sharpe_ratio", 0)
    if sharpe > 4.0:
        warnings.append(f"Sharpe {sharpe:.2f} > 4.0 — unusually high, verify no look-ahead bias")

    wr = report.get("win_rate_pct", 0)
    if wr > 85:
        warnings.append(f"Win rate {wr:.1f}% > 85% is suspicious — check exit logic")

    if not report.get("PASSED", False) and not warnings:
        warnings.append("Strategy did NOT pass prop firm rules — do NOT use for evaluation")

    if warnings:
        print("\n⚠  WARNINGS:")
        for w in warnings:
            print(f"   • {w}")


import pandas as pd  # needed for pd.DateOffset in plot section

if __name__ == "__main__":
    main()
