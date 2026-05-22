"""
Performance metrics: Sharpe, Sortino, Calmar, profit factor, win rate,
max drawdown, CAGR, trade-level statistics, and prop firm pass/fail summary.
"""

import math
import pandas as pd
import numpy as np
from typing import Dict, Any


TRADING_DAYS_PER_YEAR = 252


def compute_returns(equity_curve: pd.DataFrame) -> pd.Series:
    """Daily returns from equity curve."""
    eq = equity_curve["equity"].resample("1D").last().dropna()
    return eq.pct_change().dropna()


def cagr(equity_curve: pd.DataFrame, start_equity: float) -> float:
    eq = equity_curve["equity"].dropna()
    if len(eq) < 2:
        return 0.0
    n_years = (eq.index[-1] - eq.index[0]).days / 365.25
    if n_years <= 0:
        return 0.0
    return (eq.iloc[-1] / start_equity) ** (1 / n_years) - 1


def sharpe_ratio(returns: pd.Series, risk_free: float = 0.05) -> float:
    if returns.std() == 0:
        return 0.0
    daily_rf = risk_free / TRADING_DAYS_PER_YEAR
    excess = returns - daily_rf
    return float(excess.mean() / excess.std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR))


def sortino_ratio(returns: pd.Series, risk_free: float = 0.05) -> float:
    daily_rf = risk_free / TRADING_DAYS_PER_YEAR
    excess = returns - daily_rf
    downside = excess[excess < 0]
    if len(downside) < 2 or downside.std() == 0:
        return 0.0
    return float(excess.mean() / downside.std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR))


def max_drawdown(equity_curve: pd.DataFrame) -> tuple[float, float]:
    """Returns (max_drawdown_dollars, max_drawdown_pct)."""
    eq = equity_curve["equity"].dropna()
    roll_max = eq.cummax()
    dd = eq - roll_max
    mdd_dollars = float(dd.min())
    mdd_pct = float((dd / roll_max).min()) * 100
    return mdd_dollars, mdd_pct


def max_drawdown_duration(equity_curve: pd.DataFrame) -> int:
    """Days from peak to recovery (longest drawdown period)."""
    eq = equity_curve["equity"].dropna()
    roll_max = eq.cummax()
    in_dd = (eq < roll_max)
    durations = []
    current = 0
    for v in in_dd:
        if v:
            current += 1
        else:
            if current:
                durations.append(current)
            current = 0
    return max(durations) if durations else 0


def calmar_ratio(equity_curve: pd.DataFrame, start_equity: float) -> float:
    ann = cagr(equity_curve, start_equity)
    _, mdd_pct = max_drawdown(equity_curve)
    mdd_abs = abs(mdd_pct) / 100
    return ann / mdd_abs if mdd_abs > 0 else 0.0


def profit_factor(trades_df: pd.DataFrame) -> float:
    wins = trades_df[trades_df["pnl_net"] > 0]["pnl_net"].sum()
    losses = trades_df[trades_df["pnl_net"] < 0]["pnl_net"].sum()
    return wins / abs(losses) if losses != 0 else float("inf")


def win_rate(trades_df: pd.DataFrame) -> float:
    if len(trades_df) == 0:
        return 0.0
    return float((trades_df["pnl_net"] > 0).mean())


def avg_win_loss(trades_df: pd.DataFrame) -> tuple[float, float]:
    wins = trades_df[trades_df["pnl_net"] > 0]["pnl_net"]
    losses = trades_df[trades_df["pnl_net"] < 0]["pnl_net"]
    return float(wins.mean()) if len(wins) else 0.0, float(losses.mean()) if len(losses) else 0.0


def expectancy(trades_df: pd.DataFrame) -> float:
    """Average net P&L per trade in dollars."""
    if len(trades_df) == 0:
        return 0.0
    return float(trades_df["pnl_net"].mean())


def consecutive_stats(trades_df: pd.DataFrame) -> dict:
    if len(trades_df) == 0:
        return {"max_consec_wins": 0, "max_consec_losses": 0}
    wins = (trades_df["pnl_net"] > 0).astype(int)
    max_w = max_l = cur_w = cur_l = 0
    for w in wins:
        if w:
            cur_w += 1; cur_l = 0
        else:
            cur_l += 1; cur_w = 0
        max_w = max(max_w, cur_w)
        max_l = max(max_l, cur_l)
    return {"max_consec_wins": max_w, "max_consec_losses": max_l}


def exit_breakdown(trades_df: pd.DataFrame) -> dict:
    if "exit_reason" not in trades_df.columns:
        return {}
    return trades_df.groupby("exit_reason")["pnl_net"].agg(["count", "sum", "mean"]).to_dict()


def prop_firm_check(
    equity_curve: pd.DataFrame,
    trades_df: pd.DataFrame,
    config,
) -> dict:
    """
    Evaluate whether the backtest would have passed a prop firm evaluation.
    Returns dict with pass/fail flags and detailed diagnostics.
    """
    prop = config.prop
    start_eq = prop.account_size

    eq = equity_curve["equity"]
    min_equity = float(eq.min())
    final_equity = float(eq.iloc[-1])

    # Max trailing drawdown from peak
    roll_max = eq.cummax()
    trailing_dd = float((eq - roll_max).min())

    # Daily P&L
    daily_pnl = trades_df.groupby(
        pd.to_datetime(trades_df["exit_time"]).dt.date
    )["pnl_net"].sum()

    max_daily_loss = float(daily_pnl.min()) if len(daily_pnl) else 0.0
    max_single_day_profit = float(daily_pnl.max()) if len(daily_pnl) else 0.0
    total_profit = float(daily_pnl[daily_pnl > 0].sum())
    consistency_pct = (
        max_single_day_profit / total_profit if total_profit > 0 else 0.0
    )

    passed_daily_loss = max_daily_loss >= -prop.max_daily_loss
    passed_trailing_dd = trailing_dd >= -prop.max_trailing_drawdown
    passed_total_loss = (start_eq - min_equity) <= prop.max_total_loss
    passed_consistency = consistency_pct <= prop.max_single_day_profit_pct
    passed_profit_target = (final_equity - start_eq) >= (start_eq * 0.08)  # typical 8%

    overall = all([
        passed_daily_loss, passed_trailing_dd,
        passed_total_loss, passed_consistency, passed_profit_target,
    ])

    return {
        "prop_firm": prop.name,
        "account_size": start_eq,
        "PASSED": overall,
        "profit_target_met": passed_profit_target,
        "daily_loss_ok": passed_daily_loss,
        "trailing_dd_ok": passed_trailing_dd,
        "total_loss_ok": passed_total_loss,
        "consistency_ok": passed_consistency,
        "worst_daily_loss": round(max_daily_loss, 2),
        "max_trailing_dd": round(trailing_dd, 2),
        "best_single_day": round(max_single_day_profit, 2),
        "consistency_pct": round(consistency_pct * 100, 1),
        "final_equity": round(final_equity, 2),
        "total_net_pnl": round(final_equity - start_eq, 2),
    }


def full_report(
    equity_curve: pd.DataFrame,
    trades_df: pd.DataFrame,
    config,
) -> Dict[str, Any]:
    """Master metrics report."""
    if trades_df.empty:
        return {"error": "No trades generated"}

    start_equity = config.prop.account_size
    returns = compute_returns(equity_curve)
    mdd_d, mdd_p = max_drawdown(equity_curve)
    avg_w, avg_l = avg_win_loss(trades_df)

    report = {
        # Returns
        "total_net_pnl": round(float(trades_df["pnl_net"].sum()), 2),
        "cagr_pct": round(cagr(equity_curve, start_equity) * 100, 2),
        # Risk-adjusted
        "sharpe_ratio": round(sharpe_ratio(returns), 3),
        "sortino_ratio": round(sortino_ratio(returns), 3),
        "calmar_ratio": round(calmar_ratio(equity_curve, start_equity), 3),
        # Drawdown
        "max_drawdown_dollars": round(mdd_d, 2),
        "max_drawdown_pct": round(mdd_p, 2),
        "max_dd_duration_days": max_drawdown_duration(equity_curve),
        # Trade stats
        "total_trades": len(trades_df),
        "win_rate_pct": round(win_rate(trades_df) * 100, 1),
        "profit_factor": round(profit_factor(trades_df), 3),
        "expectancy_per_trade": round(expectancy(trades_df), 2),
        "avg_win": round(avg_w, 2),
        "avg_loss": round(avg_l, 2),
        "avg_rr_ratio": round(abs(avg_w / avg_l) if avg_l else 0, 2),
        **consecutive_stats(trades_df),
        # Prop firm
        **prop_firm_check(equity_curve, trades_df, config),
        # Monthly
        "monthly_pnl": _monthly_pnl(trades_df),
    }
    return report


def _monthly_pnl(trades_df: pd.DataFrame) -> dict:
    if trades_df.empty or "exit_time" not in trades_df.columns:
        return {}
    df = trades_df.copy()
    df["month"] = pd.to_datetime(df["exit_time"]).dt.to_period("M").astype(str)
    monthly = df.groupby("month")["pnl_net"].sum().round(2)
    return monthly.to_dict()


def print_report(report: dict):
    """Pretty-print the full metrics report."""
    divider = "=" * 60
    print(f"\n{divider}")
    print(f"  PERFORMANCE REPORT")
    print(divider)

    sections = {
        "Returns": ["total_net_pnl", "cagr_pct"],
        "Risk-Adjusted": ["sharpe_ratio", "sortino_ratio", "calmar_ratio"],
        "Drawdown": ["max_drawdown_dollars", "max_drawdown_pct", "max_dd_duration_days"],
        "Trades": ["total_trades", "win_rate_pct", "profit_factor",
                   "expectancy_per_trade", "avg_win", "avg_loss",
                   "avg_rr_ratio", "max_consec_wins", "max_consec_losses"],
        "Prop Firm": ["prop_firm", "PASSED", "profit_target_met", "daily_loss_ok",
                      "trailing_dd_ok", "consistency_ok", "worst_daily_loss",
                      "max_trailing_dd", "final_equity", "total_net_pnl"],
    }

    for section, keys in sections.items():
        print(f"\n  {section}")
        print("  " + "-" * 40)
        for k in keys:
            if k in report:
                v = report[k]
                suffix = "%" if k.endswith("_pct") or k.endswith("_pct") else ""
                print(f"    {k:<30} {v}{suffix}")

    if "monthly_pnl" in report and report["monthly_pnl"]:
        print(f"\n  Monthly P&L")
        print("  " + "-" * 40)
        for month, pnl in sorted(report["monthly_pnl"].items()):
            bar = "█" * int(abs(pnl) / 200) if abs(pnl) > 0 else ""
            sign = "+" if pnl >= 0 else ""
            print(f"    {month}   {sign}${pnl:.0f}  {bar}")

    print(f"\n{divider}\n")
