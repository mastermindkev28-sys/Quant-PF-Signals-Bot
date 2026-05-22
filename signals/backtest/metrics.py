import math
import pandas as pd
import numpy as np


def compute_metrics(results: pd.DataFrame, risk_free_rate: float = 0.0) -> dict:
    pnl = results["pnl"].dropna()
    equity = results["equity"].dropna()

    total_return = float(equity.iloc[-1]) if len(equity) else 0.0
    n_bars = len(pnl)
    trading_days_per_year = 252

    ann_return = total_return * (trading_days_per_year / max(n_bars, 1))

    daily_rf = risk_free_rate / trading_days_per_year
    excess = pnl - daily_rf
    sharpe = float(excess.mean() / excess.std(ddof=1)) * math.sqrt(trading_days_per_year) if excess.std() > 0 else 0.0

    downside = excess[excess < 0]
    sortino = float(excess.mean() / downside.std(ddof=1)) * math.sqrt(trading_days_per_year) if len(downside) > 1 and downside.std() > 0 else 0.0

    roll_max = equity.cummax()
    drawdown = equity - roll_max
    max_dd = float(drawdown.min())

    dd_pct = (drawdown / roll_max.replace(0, float("nan"))).min()
    max_dd_pct = float(dd_pct) if not math.isnan(dd_pct) else 0.0

    trades = _extract_trades(results)
    n_trades = len(trades)
    win_rate = float((trades["pnl"] > 0).mean()) if n_trades else 0.0
    avg_win = float(trades.loc[trades["pnl"] > 0, "pnl"].mean()) if (trades["pnl"] > 0).any() else 0.0
    avg_loss = float(trades.loc[trades["pnl"] < 0, "pnl"].mean()) if (trades["pnl"] < 0).any() else 0.0

    return {
        "total_pnl": round(total_return, 2),
        "annualized_return": round(ann_return, 2),
        "sharpe_ratio": round(sharpe, 3),
        "sortino_ratio": round(sortino, 3),
        "max_drawdown": round(max_dd, 2),
        "max_drawdown_pct": round(max_dd_pct * 100, 2),
        "n_trades": n_trades,
        "win_rate": round(win_rate * 100, 1),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
    }


def _extract_trades(results: pd.DataFrame) -> pd.DataFrame:
    trades = []
    position = 0
    entry_idx = None
    trade_pnl = 0.0

    for i, row in results.iterrows():
        sig = int(row.get("contracts", 0))
        pnl = float(row.get("pnl", 0.0))

        if position == 0 and sig != 0:
            position = sig
            entry_idx = i
            trade_pnl = 0.0
        elif position != 0:
            trade_pnl += pnl
            if sig == 0 or (sig != 0 and sig != position):
                trades.append({"entry": entry_idx, "exit": i, "pnl": trade_pnl})
                position = sig
                entry_idx = i if sig != 0 else None
                trade_pnl = 0.0

    return pd.DataFrame(trades) if trades else pd.DataFrame(columns=["entry", "exit", "pnl"])


def plot_equity_curve(results: pd.DataFrame, title: str = "Equity Curve", save_path: str = None):
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed — skipping plot")
        return

    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True)

    axes[0].plot(results.index, results["equity"], label="Equity")
    axes[0].set_title(title)
    axes[0].set_ylabel("Cumulative PnL ($)")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    col = "zscore" if "zscore" in results.columns else "signal_strength"
    if col in results.columns:
        axes[1].plot(results.index, results[col], color="orange", label=col)
        axes[1].axhline(0, color="black", linewidth=0.5)
        axes[1].set_ylabel(col)
        axes[1].legend()
        axes[1].grid(True, alpha=0.3)

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150)
    else:
        plt.show()
    plt.close()
