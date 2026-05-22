"""
Plotting utilities: equity curve, drawdown, monthly heatmap,
IBS signal visualisation, Monte Carlo fan chart.
"""

import logging
from pathlib import Path
from typing import Optional, List
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def _get_mpl():
    try:
        import matplotlib
        matplotlib.use("Agg")  # headless / VPS-friendly
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec
        return plt, gridspec
    except ImportError:
        raise ImportError("pip install matplotlib")


def plot_equity_curve(
    equity_curve: pd.DataFrame,
    trades_df: Optional[pd.DataFrame] = None,
    title: str = "Equity Curve",
    save_path: Optional[str] = None,
    show: bool = False,
):
    plt, gridspec = _get_mpl()
    fig, axes = plt.subplots(3, 1, figsize=(14, 10),
                              gridspec_kw={"height_ratios": [3, 1, 1]}, sharex=True)
    fig.suptitle(title, fontsize=14, fontweight="bold")

    # --- Equity ---
    eq = equity_curve["equity"]
    axes[0].plot(eq.index, eq.values, color="#2196F3", linewidth=1.5, label="Net Equity")
    axes[0].fill_between(eq.index, eq.values, eq.values[0],
                          where=eq.values >= eq.values[0], alpha=0.15, color="#2196F3")
    axes[0].fill_between(eq.index, eq.values, eq.values[0],
                          where=eq.values < eq.values[0], alpha=0.2, color="#F44336")
    if trades_df is not None and not trades_df.empty:
        wins = trades_df[trades_df["pnl_net"] > 0]
        losses = trades_df[trades_df["pnl_net"] <= 0]
        for t in wins.itertuples():
            if pd.notna(t.exit_time):
                axes[0].axvline(t.exit_time, color="#4CAF50", alpha=0.3, linewidth=0.5)
        for t in losses.itertuples():
            if pd.notna(t.exit_time):
                axes[0].axvline(t.exit_time, color="#F44336", alpha=0.3, linewidth=0.5)
    axes[0].set_ylabel("Equity ($)")
    axes[0].legend(loc="upper left")
    axes[0].grid(True, alpha=0.3)

    # --- Drawdown ---
    roll_max = eq.cummax()
    dd = eq - roll_max
    axes[1].fill_between(dd.index, dd.values, 0, alpha=0.6, color="#F44336", label="Drawdown")
    axes[1].set_ylabel("Drawdown ($)")
    axes[1].legend(loc="lower left")
    axes[1].grid(True, alpha=0.3)

    # --- Daily P&L bar chart ---
    if trades_df is not None and not trades_df.empty and "exit_time" in trades_df.columns:
        daily = trades_df.groupby(
            pd.to_datetime(trades_df["exit_time"]).dt.date
        )["pnl_net"].sum()
        colors = ["#4CAF50" if v > 0 else "#F44336" for v in daily.values]
        axes[2].bar(pd.to_datetime(daily.index), daily.values, color=colors, alpha=0.7)
        axes[2].axhline(0, color="black", linewidth=0.5)
        axes[2].set_ylabel("Daily P&L ($)")
        axes[2].grid(True, alpha=0.3)

    plt.tight_layout()
    _save_or_show(plt, fig, save_path, show)


def plot_monthly_heatmap(
    trades_df: pd.DataFrame,
    save_path: Optional[str] = None,
    show: bool = False,
):
    plt, _ = _get_mpl()
    if trades_df.empty:
        return

    df = trades_df.copy()
    df["exit_time"] = pd.to_datetime(df["exit_time"])
    df["year"] = df["exit_time"].dt.year
    df["month"] = df["exit_time"].dt.month

    pivot = df.groupby(["year", "month"])["pnl_net"].sum().unstack(fill_value=0)

    import matplotlib.colors as mcolors
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "rg", ["#F44336", "#FFFFFF", "#4CAF50"]
    )
    vmax = max(abs(pivot.values.min()), abs(pivot.values.max()), 1)

    fig, ax = plt.subplots(figsize=(12, max(3, len(pivot) * 0.8)))
    im = ax.imshow(pivot.values, cmap=cmap, aspect="auto", vmin=-vmax, vmax=vmax)
    plt.colorbar(im, ax=ax, label="Monthly P&L ($)")

    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels([months[m - 1] for m in pivot.columns])
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index)

    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            val = pivot.values[i, j]
            ax.text(j, i, f"${val:.0f}", ha="center", va="center",
                    fontsize=7, color="black" if abs(val) < vmax * 0.5 else "white")

    ax.set_title("Monthly P&L Heatmap")
    plt.tight_layout()
    _save_or_show(plt, fig, save_path, show)


def plot_monte_carlo(
    mc_paths: pd.DataFrame,
    start_equity: float,
    prop_target: float,
    ruin_floor: float,
    save_path: Optional[str] = None,
    show: bool = False,
    n_paths_to_plot: int = 200,
):
    plt, _ = _get_mpl()
    fig, ax = plt.subplots(figsize=(12, 6))

    equity_paths = start_equity + mc_paths
    sample = equity_paths.sample(min(n_paths_to_plot, len(equity_paths)))

    for _, row in sample.iterrows():
        ax.plot(row.values, color="#90CAF9", alpha=0.15, linewidth=0.5)

    # Percentile bands
    for pct, color, label in [(5, "#F44336", "5th pct"), (50, "#2196F3", "Median"), (95, "#4CAF50", "95th pct")]:
        band = equity_paths.quantile(pct / 100, axis=0)
        ax.plot(band.values, color=color, linewidth=2, label=label)

    ax.axhline(start_equity + prop_target, color="#FF9800", linestyle="--",
               linewidth=1.5, label=f"Pass target (+${prop_target:,.0f})")
    ax.axhline(start_equity + ruin_floor, color="#D32F2F", linestyle="--",
               linewidth=1.5, label=f"Ruin floor (-${abs(ruin_floor):,.0f})")

    ax.set_title(f"Monte Carlo Fan Chart ({len(mc_paths):,} simulations)")
    ax.set_xlabel("Trade #")
    ax.set_ylabel("Equity ($)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    _save_or_show(plt, fig, save_path, show)


def plot_ibs_signals(
    df: pd.DataFrame,
    save_path: Optional[str] = None,
    show: bool = False,
):
    plt, _ = _get_mpl()
    required = {"close", "lower_band", "ibs", "trend_sma"}
    if not required.issubset(df.columns):
        logger.warning("Missing columns for IBS plot: %s", required - set(df.columns))
        return

    fig, axes = plt.subplots(3, 1, figsize=(14, 9), sharex=True,
                              gridspec_kw={"height_ratios": [3, 1, 1]})

    ax = axes[0]
    ax.plot(df.index, df["close"], label="Close", color="#2196F3", linewidth=1)
    ax.plot(df.index, df["lower_band"], label="Lower Band", color="#F44336", linewidth=1, linestyle="--")
    ax.plot(df.index, df["trend_sma"], label="300 SMA", color="#FF9800", linewidth=1, linestyle=":")

    if "signal" in df.columns:
        entries = df[df["signal"] == 1]
        exits = df[df["signal"] == -1]
        ax.scatter(entries.index, entries["close"], marker="^", color="#4CAF50", s=80, zorder=5, label="Entry")
        ax.scatter(exits.index, exits["close"], marker="v", color="#F44336", s=80, zorder=5, label="Exit")

    ax.set_title("IBS Mean Reversion — Price & Bands")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(True, alpha=0.3)

    axes[1].plot(df.index, df["ibs"], color="#9C27B0", linewidth=1)
    axes[1].axhline(0.3, color="#F44336", linestyle="--", linewidth=1, label="IBS=0.3 threshold")
    axes[1].set_ylabel("IBS")
    axes[1].set_ylim(0, 1)
    axes[1].legend(fontsize=8)
    axes[1].grid(True, alpha=0.3)

    if "avg_range" in df.columns:
        axes[2].plot(df.index, df["avg_range"], color="#607D8B", linewidth=1, label="Avg Range (25)")
        axes[2].set_ylabel("Avg Daily Range")
        axes[2].legend(fontsize=8)
        axes[2].grid(True, alpha=0.3)

    plt.tight_layout()
    _save_or_show(plt, fig, save_path, show)


def _save_or_show(plt, fig, save_path: Optional[str], show: bool):
    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        logger.info("Saved plot: %s", save_path)
    if show:
        plt.show()
    plt.close(fig)
