"""
Walk-Forward Optimisation (WFO).

Splits data into rolling in-sample (IS) / out-of-sample (OOS) windows.
Optimises strategy parameters on IS, tests on OOS, avoids look-ahead bias.

WFO Efficiency = avg OOS Sharpe / avg IS Sharpe
  > 0.5  : reasonable robustness
  < 0.3  : likely overfit — do NOT use these parameters live
"""

import logging
from dataclasses import dataclass
from itertools import product
from typing import Callable, Dict, List, Tuple
import pandas as pd
import numpy as np

from .metrics import sharpe_ratio, compute_returns, profit_factor

logger = logging.getLogger(__name__)


@dataclass
class WFOWindow:
    is_start: pd.Timestamp
    is_end: pd.Timestamp
    oos_start: pd.Timestamp
    oos_end: pd.Timestamp
    best_params: dict
    is_sharpe: float
    oos_sharpe: float
    oos_profit_factor: float
    oos_trades: int


def generate_wfo_windows(
    df: pd.DataFrame,
    is_bars: int = 500,
    oos_bars: int = 125,
    step_bars: int = 125,
    min_is_bars: int = 300,
) -> List[Tuple[pd.DataFrame, pd.DataFrame]]:
    """
    Anchored walk-forward: each window anchors at the same start,
    expanding IS window. Simplest and most robust approach.

    For rolling (non-anchored) window, set anchored=False.
    """
    n = len(df)
    windows = []
    start = 0

    while start + is_bars + oos_bars <= n:
        is_data = df.iloc[start : start + is_bars]
        oos_data = df.iloc[start + is_bars : start + is_bars + oos_bars]
        if len(is_data) >= min_is_bars:
            windows.append((is_data, oos_data))
        start += step_bars

    logger.info("Generated %d WFO windows", len(windows))
    return windows


def optimise_on_window(
    is_data: pd.DataFrame,
    param_grid: Dict[str, List],
    run_func: Callable,  # fn(data, params) -> equity_curve_df
    metric: str = "sharpe",
) -> Tuple[dict, float]:
    """
    Grid search over param_grid on is_data.
    Returns (best_params, best_metric_value).
    """
    keys = list(param_grid.keys())
    values = list(param_grid.values())
    best_score = -float("inf")
    best_params = {}

    for combo in product(*values):
        params = dict(zip(keys, combo))
        try:
            equity_curve = run_func(is_data, params)
            returns = compute_returns(equity_curve)
            if metric == "sharpe":
                score = sharpe_ratio(returns)
            elif metric == "profit_factor":
                score = profit_factor(equity_curve)  # pass trades_df here
            else:
                score = float(equity_curve["equity"].iloc[-1])

            if score > best_score:
                best_score = score
                best_params = params

        except Exception as e:
            logger.debug("WFO param combo failed %s: %s", params, e)

    return best_params, best_score


def run_walk_forward(
    df: pd.DataFrame,
    param_grid: Dict[str, List],
    run_func: Callable,
    is_bars: int = 500,
    oos_bars: int = 125,
    step_bars: int = 125,
) -> List[WFOWindow]:
    """
    Full WFO pipeline. Returns list of WFOWindow results.

    Interpret results:
      WFO_efficiency = mean(oos_sharpe) / mean(is_sharpe)
      > 0.50: good robustness
      0.30–0.50: moderate
      < 0.30: OVERFIT — do not trade live
    """
    windows_data = generate_wfo_windows(df, is_bars, oos_bars, step_bars)
    results = []

    for i, (is_data, oos_data) in enumerate(windows_data):
        logger.info(
            "WFO window %d/%d | IS: %s→%s | OOS: %s→%s",
            i + 1, len(windows_data),
            is_data.index[0].date(), is_data.index[-1].date(),
            oos_data.index[0].date(), oos_data.index[-1].date(),
        )
        best_params, is_score = optimise_on_window(is_data, param_grid, run_func)

        try:
            oos_equity = run_func(oos_data, best_params)
            oos_returns = compute_returns(oos_equity)
            oos_score = sharpe_ratio(oos_returns)
            pf = profit_factor(oos_equity) if hasattr(oos_equity, "columns") else 0.0
            n_trades = int(oos_equity.get("n_trades", 0)) if isinstance(oos_equity, dict) else 0
        except Exception as e:
            logger.warning("OOS evaluation failed: %s", e)
            oos_score, pf, n_trades = 0.0, 0.0, 0

        results.append(WFOWindow(
            is_start=is_data.index[0],
            is_end=is_data.index[-1],
            oos_start=oos_data.index[0],
            oos_end=oos_data.index[-1],
            best_params=best_params,
            is_sharpe=round(is_score, 3),
            oos_sharpe=round(oos_score, 3),
            oos_profit_factor=round(pf, 3),
            oos_trades=n_trades,
        ))

    _print_wfo_summary(results)
    return results


def _print_wfo_summary(results: List[WFOWindow]):
    if not results:
        return
    is_sharpes = [r.is_sharpe for r in results]
    oos_sharpes = [r.oos_sharpe for r in results]
    efficiency = np.mean(oos_sharpes) / np.mean(is_sharpes) if np.mean(is_sharpes) != 0 else 0
    oos_positive = sum(1 for s in oos_sharpes if s > 0)

    print("\n" + "=" * 60)
    print("  WALK-FORWARD OPTIMISATION SUMMARY")
    print("=" * 60)
    print(f"  Windows:         {len(results)}")
    print(f"  Avg IS Sharpe:   {np.mean(is_sharpes):.3f}")
    print(f"  Avg OOS Sharpe:  {np.mean(oos_sharpes):.3f}")
    print(f"  WFO Efficiency:  {efficiency:.2%}")
    print(f"  OOS+ windows:    {oos_positive}/{len(results)}")

    robust = efficiency >= 0.5
    print(f"\n  Robustness: {'✓ ROBUST' if robust else '✗ POSSIBLY OVERFIT'}")
    if not robust:
        print("  WARNING: WFO efficiency < 50%. Consider simpler parameters.")
    print("=" * 60 + "\n")

    print(f"  {'Window':<6} {'IS Sharpe':>10} {'OOS Sharpe':>10} {'OOS PF':>8} {'Best Params'}")
    print("  " + "-" * 70)
    for i, r in enumerate(results):
        params_str = ", ".join(f"{k}={v}" for k, v in r.best_params.items())
        print(f"  {i+1:<6} {r.is_sharpe:>10.3f} {r.oos_sharpe:>10.3f} "
              f"{r.oos_profit_factor:>8.3f}  {params_str}")
