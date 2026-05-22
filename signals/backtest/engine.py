import pandas as pd
from ..strategy.base import Strategy
from ..risk.position_sizer import PositionSizer


class Backtester:
    """
    Vectorized-first backtester for futures mean reversion strategies.
    Signals from bar T are filled at bar T+1 open (no lookahead).
    """

    def __init__(
        self,
        strategy: Strategy,
        sizer: PositionSizer,
        point_value: float = 1.0,
        fill_on_close: bool = False,
    ):
        self.strategy = strategy
        self.sizer = sizer
        self.point_value = point_value
        self.fill_on_close = fill_on_close

    def run(self, ohlcv: pd.DataFrame) -> pd.DataFrame:
        df = self.strategy.generate_signals(ohlcv)

        fill_price = df["close"] if self.fill_on_close else df["open"].shift(-1)
        position_signal = df["signal"].shift(1).fillna(0).astype(int)

        contracts = pd.Series(0, index=df.index, dtype=int)
        for i in range(1, len(df)):
            sig = int(df["signal"].iloc[i - 1])
            if sig != 0:
                contracts.iloc[i] = self.sizer.size(ohlcv, self.point_value, i - 1) * sig

        price_change = df["close"].diff()
        pnl = contracts.shift(1).fillna(0) * price_change * self.point_value
        equity = pnl.cumsum()

        result = df.copy()
        result["contracts"] = contracts
        result["fill_price"] = fill_price
        result["pnl"] = pnl
        result["equity"] = equity
        return result
