"""
Dual Thrust Breakout Strategy — intraday (5-min or 15-min bars).

Entry : price breaks above upper_band → long
        price breaks below lower_band → short (if allow_short)
Stop  : opposite band OR ATR-based stop
Exit  : EOD flat, or reverse on opposite signal
"""

import pandas as pd
import numpy as np

from .base import Strategy
from ..indicators.dual_thrust import compute_dual_thrust_bands
from ..indicators.common import atr
from ..data.loader import add_session_flags


class DualThrustBreakout(Strategy):

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        cfg = self.config.dual_thrust
        df = add_session_flags(df, timeframe=cfg.timeframe)
        df = compute_dual_thrust_bands(
            df,
            lookback=cfg.lookback,
            k_upper=cfg.k_upper,
            k_lower=cfg.k_lower,
        )
        df["atr"] = atr(df, self.config.risk.atr_period)
        return df

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        cfg = self.config.dual_thrust
        risk = self.config.risk
        df = df.copy()

        df["stop_price"] = np.nan
        df["target_price"] = 0.0
        df["signal_strength"] = 0.5  # breakout: no quality gradation, binary

        signal = pd.Series(0, index=df.index, dtype=int)
        stop_price = pd.Series(np.nan, index=df.index)
        position = 0
        last_signal_bar = -1

        for i in range(len(df)):
            row = df.iloc[i]

            # Hard EOD flatten
            if cfg.exit_eod and bool(row.get("is_last_bar", False)):
                if position != 0:
                    signal.iloc[i] = -position  # counter-signal = exit
                    position = 0
                continue

            # Reset at session start (bands recalculate)
            if bool(row.get("is_first_bar", False)):
                position = 0

            if position == 0:
                if bool(row.get("long_signal", False)):
                    position = 1
                    signal.iloc[i] = 1
                    last_signal_bar = i
                    atr_val = row["atr"] if not pd.isna(row["atr"]) else 0
                    stop_price.iloc[i] = row["lower_band"] - risk.atr_stop_multiplier * atr_val

                elif cfg.allow_short and bool(row.get("short_signal", False)):
                    position = -1
                    signal.iloc[i] = -1
                    last_signal_bar = i
                    atr_val = row["atr"] if not pd.isna(row["atr"]) else 0
                    stop_price.iloc[i] = row["upper_band"] + risk.atr_stop_multiplier * atr_val

            elif position == 1:
                if cfg.reverse_on_opposite and bool(row.get("short_signal", False)):
                    signal.iloc[i] = -1  # reverse: exit long, enter short
                    position = -1
                    atr_val = row["atr"] if not pd.isna(row["atr"]) else 0
                    stop_price.iloc[i] = row["upper_band"] + risk.atr_stop_multiplier * atr_val

            elif position == -1:
                if cfg.reverse_on_opposite and bool(row.get("long_signal", False)):
                    signal.iloc[i] = 1   # reverse: exit short, enter long
                    position = 1
                    atr_val = row["atr"] if not pd.isna(row["atr"]) else 0
                    stop_price.iloc[i] = row["lower_band"] - risk.atr_stop_multiplier * atr_val

        df["signal"] = signal
        df["stop_price"] = stop_price
        return df

    def describe(self) -> str:
        c = self.config.dual_thrust
        return (
            f"DualThrust | N={c.lookback} k_up={c.k_upper} k_dn={c.k_lower} "
            f"| tf={c.timeframe} | short={'yes' if c.allow_short else 'no'}"
        )
