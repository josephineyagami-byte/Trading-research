"""Input checks shared by historical OHLCV and flow loaders."""

import pandas as pd


def regular_session_mask(timestamps_ms: pd.Series) -> pd.Series:
    """9:35 <= ET < 16:00; preserve the existing auction exclusion, with DST.

    This filters supplied bars, not an exchange calendar or completeness check.
    """
    et = pd.to_datetime(timestamps_ms, unit="ms", utc=True).dt.tz_convert("America/New_York")
    minutes = et.dt.hour * 60 + et.dt.minute
    return (et.dt.dayofweek < 5) & (minutes >= 575) & (minutes < 960)


def unique_timestamp_bars(df: pd.DataFrame) -> pd.DataFrame:
    """Remove exact page-boundary repeats; never choose a conflicting revision."""
    if df.empty:
        return df
    unique = df.drop_duplicates()
    if unique["timestamp"].isna().any() or unique["timestamp"].duplicated().any():
        raise ValueError("Conflicting or missing bar timestamps; inspect source revisions")
    return unique.sort_values("timestamp").reset_index(drop=True)
