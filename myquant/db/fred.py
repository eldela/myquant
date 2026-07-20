"""FRED-specific series fetch logic.

Internal helper extracted from the unified ``fetch_series`` function
in :mod:`myquant.db.core`.  Not part of the public API.
"""

from __future__ import annotations

import sqlite3

import pandas as pd

from myquant.db.core import _log_series_fetch
from myquant.fred import Fred


def _fetch_fred_series(
    conn: sqlite3.Connection,
    series_id: str,
    start_date: str,
    end_date: str,
    today: str,
) -> None:
    """Fetch observations for a FRED series and store them in the database.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    series_id : str
        FRED series identifier (e.g. ``"DGS10"``).
    start_date : str
        ISO start date (already resolved by :func:`~myquant.db.core._resolve_fetch_window`).
    end_date : str
        ISO end date.
    today : str
        Current date as ISO string (used for fetch logging).
    """
    try:
        fred = Fred()
        data = fred.get_data(
            "series_observations",
            series_id=series_id,
            observation_start=start_date,
            observation_end=end_date,
        )
    except Exception as exc:
        _log_series_fetch(
            conn, series_id, today,
            start_date, end_date, 0, "error", str(exc),
        )
        return

    if not isinstance(data, pd.DataFrame) or data.empty:
        _log_series_fetch(
            conn, series_id, today,
            start_date, end_date, 0, "ok",
            "No observations returned",
        )
        return

    df = data[["date", "value", "realtime_start", "realtime_end"]].copy()
    df["series_id"] = series_id
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.where(pd.notnull(df), None)
    rows = [
        (
            row.series_id, row.date, row.value,
            row.realtime_start, row.realtime_end,
        )
        for row in df.itertuples(index=False)
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO observations "
        "(series_id, date, value, realtime_start, realtime_end) "
        "VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    _log_series_fetch(
        conn, series_id, today,
        start_date, end_date, len(rows), "ok",
    )
