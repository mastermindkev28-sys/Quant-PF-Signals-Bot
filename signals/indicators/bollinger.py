import pandas as pd


def compute_bollinger(series: pd.Series, period: int = 20, n_std: float = 2.0) -> pd.DataFrame:
    """
    Returns DataFrame with columns: middle, upper, lower, pct_b, bandwidth.
    pct_b: 0 = at lower band, 1 = at upper band. Values outside [0,1] indicate beyond-band price.
    bandwidth: (upper - lower) / middle — useful for squeeze filter.
    """
    middle = series.rolling(period).mean()
    std = series.rolling(period).std(ddof=1)
    upper = middle + n_std * std
    lower = middle - n_std * std
    band_width = upper - lower
    pct_b = (series - lower) / band_width.replace(0, float("nan"))
    bandwidth = band_width / middle.replace(0, float("nan"))

    return pd.DataFrame({
        "middle": middle,
        "upper": upper,
        "lower": lower,
        "pct_b": pct_b,
        "bandwidth": bandwidth,
    }, index=series.index)
