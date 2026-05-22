"""Abstract Strategy base class."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd


@dataclass
class TradeSignal:
    """Immutable signal emitted by a strategy."""
    timestamp: pd.Timestamp
    direction: int          # 1 = long, -1 = short, 0 = flat/exit
    instrument: str
    strategy: str
    entry_price: float
    stop_price: float       # hard stop loss price
    target_price: float     # first profit target (0 = none)
    signal_strength: float  # normalised [0,1] — used for sizing
    notes: str = ""

    @property
    def risk_per_unit(self) -> float:
        return abs(self.entry_price - self.stop_price)


class Strategy(ABC):
    def __init__(self, config, instrument_cfg):
        self.config = config
        self.instrument = instrument_cfg

    @abstractmethod
    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute all indicators, return augmented DataFrame."""

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Returns DataFrame with 'signal' column:
          1 = enter long
         -1 = enter short
          0 = no position / exit
        Also adds 'stop_price', 'target_price', 'signal_strength' columns.
        """

    def run(self, df: pd.DataFrame) -> pd.DataFrame:
        prepared = self.prepare(df)
        return self.generate_signals(prepared)
