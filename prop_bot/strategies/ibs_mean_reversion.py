"""
IBS (Internal Bar Strength) Mean Reversion Strategy
for daily futures (GC/MGC, NQ/MNQ, ES/MES).

Entry  : close < lower_band  AND  IBS < 0.3  AND  close > 300 SMA
Stop   : entry - ATR_stop_mult * ATR  (hard, never widened)
Target : none by default — held until exit trigger fires
Exit   : close > previous high  OR  close < 300 SMA  OR  max_holding_days
"""

import pandas as pd
import numpy as np

from .base import Strategy, TradeSignal
from ..indicators.ibs import compute_ibs_bands, ibs_signal_quality
from ..indicators.common import atr


class IBSMeanReversion(Strategy):

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        cfg = self.config.ibs
        df = compute_ibs_bands(
            df,
            range_sma_period=cfg.range_sma_period,
            highest_high_lookback=cfg.highest_high_lookback,
            band_multiplier=cfg.band_multiplier,
            trend_sma_period=cfg.trend_sma_period,
        )
        df["atr"] = atr(df, self.config.risk.atr_period)
        df["signal_quality"] = ibs_signal_quality(df)
        return df

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Vectorised signal generation. No position state is tracked here —
        the backtest engine handles state. This returns raw entry/exit signals.

        Returns df with added columns:
          signal          : 1 (long entry), -1 (exit), 0 (no action)
          stop_price      : hard stop for entries
          target_price    : 0.0 (no fixed target; held to exit trigger)
          signal_strength : quality score [0,1]
        """
        cfg = self.config
        risk = cfg.risk

        df = df.copy()

        # --- Entry ---
        entry_mask = df["long_signal"]  # cond_below_band & cond_ibs_low & cond_trend_ok

        # Hard stop = entry close - ATR_mult * ATR
        stop_distance = risk.atr_stop_multiplier * df["atr"]
        df["stop_price"] = df["close"] - stop_distance
        df["target_price"] = 0.0
        df["signal_strength"] = df["signal_quality"].fillna(0.0)

        # Raw signal: 1 on new long entry, -1 on exit trigger, 0 otherwise
        df["raw_long"] = entry_mask.astype(int)
        df["raw_exit"] = df["exit_signal"].astype(int)

        # Stateful signal: carry position forward, exit on trigger
        signal = pd.Series(0, index=df.index, dtype=int)
        in_trade = False
        entry_idx = None
        max_hold = cfg.ibs.max_holding_days

        for i in range(len(df)):
            row = df.iloc[i]

            if in_trade:
                holding_days = i - entry_idx
                if bool(row["raw_exit"]) or holding_days >= max_hold:
                    signal.iloc[i] = -1   # exit
                    in_trade = False
                    entry_idx = None
                else:
                    signal.iloc[i] = 1    # stay long (carry)
            else:
                if bool(row["raw_long"]) and not pd.isna(row["atr"]):
                    signal.iloc[i] = 1    # new entry
                    in_trade = True
                    entry_idx = i

        df["signal"] = signal
        return df

    def describe(self) -> str:
        c = self.config.ibs
        return (
            f"IBSMeanReversion | IBS<{c.ibs_entry_threshold} "
            f"| band_mult={c.band_multiplier} | trend={c.trend_sma_period}SMA "
            f"| stop={self.config.risk.atr_stop_multiplier}×ATR"
        )
