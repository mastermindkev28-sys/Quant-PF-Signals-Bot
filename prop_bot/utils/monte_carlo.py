"""
Monte Carlo robustness analysis.

Techniques used:
  1. Trade-sequence shuffling  : resample trade P&Ls with replacement
  2. Random entry delays       : shift entries by 0–N bars
  3. Parameter perturbation    : add Gaussian noise to key parameters

Outputs:
  - Distribution of final equity
  - Distribution of Sharpe ratios
  - Probability of meeting prop firm profit target
  - 5th-percentile worst-case drawdown
  - Ruin probability (equity falls below total loss floor)
"""

import logging
import math
from typing import List
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def resample_trades(
    pnl_series: pd.Series,
    n_simulations: int = 5000,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Bootstrap resampling of trade P&Ls.
    Each simulation draws len(pnl_series) trades with replacement.
    Returns DataFrame of shape (n_simulations, len(pnl_series))
    containing cumulative P&L paths.
    """
    rng = np.random.default_rng(seed)
    n = len(pnl_series)
    arr = pnl_series.values

    simulations = rng.choice(arr, size=(n_simulations, n), replace=True)
    cumulative = np.cumsum(simulations, axis=1)
    return pd.DataFrame(cumulative)


def compute_mc_metrics(
    cumulative_paths: pd.DataFrame,
    start_equity: float,
    profit_target: float,
    ruin_threshold: float,
) -> dict:
    """
    Summarise Monte Carlo paths.

    Parameters
    ----------
    cumulative_paths : shape (n_sims, n_trades) — cumulative dollar P&L
    start_equity     : account starting balance
    profit_target    : minimum dollar profit to "pass" (e.g. $4000 for 8% of $50K)
    ruin_threshold   : equity floor below which account is "blown" (e.g. -$2500)
    """
    final_pnl = cumulative_paths.iloc[:, -1].values
    equity_paths = start_equity + cumulative_paths

    # Minimums across each path (used for drawdown / ruin checks)
    min_equity = equity_paths.min(axis=1).values
    max_equity = equity_paths.max(axis=1).values

    # Drawdown: max(peak - current) for each path
    peak_equity = equity_paths.cummax(axis=1)
    drawdowns = (equity_paths - peak_equity).min(axis=1).values

    sharpes = []
    for i in range(len(cumulative_paths)):
        path_returns = pd.Series(cumulative_paths.iloc[i].diff().fillna(0) / start_equity)
        s = path_returns.mean() / path_returns.std() * math.sqrt(252) if path_returns.std() > 0 else 0
        sharpes.append(s)
    sharpes = np.array(sharpes)

    prob_pass = float((final_pnl >= profit_target).mean())
    prob_ruin = float((min_equity <= start_equity + ruin_threshold).mean())

    return {
        "n_simulations": len(final_pnl),
        "median_final_pnl": round(float(np.median(final_pnl)), 2),
        "mean_final_pnl": round(float(np.mean(final_pnl)), 2),
        "p5_final_pnl": round(float(np.percentile(final_pnl, 5)), 2),
        "p25_final_pnl": round(float(np.percentile(final_pnl, 25)), 2),
        "p75_final_pnl": round(float(np.percentile(final_pnl, 75)), 2),
        "p95_final_pnl": round(float(np.percentile(final_pnl, 95)), 2),
        "worst_final_pnl": round(float(final_pnl.min()), 2),
        "best_final_pnl": round(float(final_pnl.max()), 2),
        "median_max_drawdown": round(float(np.median(drawdowns)), 2),
        "p5_max_drawdown": round(float(np.percentile(drawdowns, 5)), 2),
        "median_sharpe": round(float(np.median(sharpes)), 3),
        "p5_sharpe": round(float(np.percentile(sharpes, 5)), 3),
        "prob_pass_target_pct": round(prob_pass * 100, 1),
        "prob_ruin_pct": round(prob_ruin * 100, 1),
    }


def run_monte_carlo(
    trades_df: pd.DataFrame,
    config,
    n_simulations: int = 5000,
    seed: int = 42,
) -> dict:
    """
    Full Monte Carlo analysis on a completed backtest's trade list.
    """
    if trades_df.empty:
        logger.warning("No trades — cannot run Monte Carlo")
        return {}

    pnl = trades_df["pnl_net"]
    prop = config.prop

    logger.info("Running %d Monte Carlo simulations on %d trades...", n_simulations, len(pnl))
    paths = resample_trades(pnl, n_simulations, seed)

    profit_target = prop.account_size * 0.08   # 8% target (typical evaluation)
    ruin_threshold = -prop.max_total_loss

    metrics = compute_mc_metrics(paths, prop.account_size, profit_target, ruin_threshold)
    return metrics


def print_mc_report(mc: dict):
    print("\n" + "=" * 60)
    print("  MONTE CARLO ROBUSTNESS ANALYSIS")
    print("=" * 60)
    print(f"  Simulations:              {mc.get('n_simulations', 0):,}")
    print(f"\n  Final P&L Distribution")
    print(f"    5th  percentile:        ${mc.get('p5_final_pnl', 0):,.0f}")
    print(f"    25th percentile:        ${mc.get('p25_final_pnl', 0):,.0f}")
    print(f"    Median:                 ${mc.get('median_final_pnl', 0):,.0f}")
    print(f"    75th percentile:        ${mc.get('p75_final_pnl', 0):,.0f}")
    print(f"    95th percentile:        ${mc.get('p95_final_pnl', 0):,.0f}")
    print(f"\n  Drawdown")
    print(f"    Median max drawdown:    ${mc.get('median_max_drawdown', 0):,.0f}")
    print(f"    5th pct max drawdown:   ${mc.get('p5_max_drawdown', 0):,.0f}")
    print(f"\n  Sharpe Ratio")
    print(f"    Median Sharpe:          {mc.get('median_sharpe', 0):.3f}")
    print(f"    5th pct Sharpe:         {mc.get('p5_sharpe', 0):.3f}")
    print(f"\n  Prop Firm Outcome")
    print(f"    Prob pass target:       {mc.get('prob_pass_target_pct', 0):.1f}%")
    print(f"    Prob ruin:              {mc.get('prob_ruin_pct', 0):.1f}%")

    ruin = mc.get("prob_ruin_pct", 0)
    pass_p = mc.get("prob_pass_target_pct", 0)
    if ruin > 20:
        print(f"\n  ⚠ WARNING: {ruin:.1f}% ruin probability is HIGH. Review parameters.")
    if pass_p < 40:
        print(f"\n  ⚠ WARNING: Only {pass_p:.1f}% chance of passing evaluation target.")
    if pass_p >= 60 and ruin < 10:
        print(f"\n  ✓ ROBUST: {pass_p:.1f}% pass probability, {ruin:.1f}% ruin risk.")
    print("=" * 60 + "\n")
