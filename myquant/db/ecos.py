"""ECOS-specific series fetch logic.

Internal helper extracted from the unified ``fetch_series`` function
in :mod:`myquant.db.core`.  Not part of the public API.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pandas as pd

from myquant.db.core import (
    _date_to_ecos,
    _ecos_time_to_date,
    _log_series_fetch,
)
from myquant.ecos import Ecos


def _fetch_ecos_series(
    conn: sqlite3.Connection,
    series_id: str,
    start_date: str,
    end_date: str,
    today: str,
    series: dict,
) -> None:
    """Fetch observations for an ECOS series and store them in the database.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    series_id : str
        ECOS series identifier (e.g. ``"901Y009_0"``).
    start_date : str
        ISO start date (already resolved by :func:`~myquant.db.core._resolve_fetch_window`).
    end_date : str
        ISO end date.
    today : str
        Current date as ISO string (used for fetch logging and as realtime_start/end).
    series : dict
        Registry entry from :data:`~myquant.db.core.CORE_SERIES` carrying
        ``stat_code``, ``item_code``, and ``cycle``.
    """
    cycle = series["cycle"]

    ecos_start = _date_to_ecos(
        date.fromisoformat(start_date), cycle
    )
    ecos_end = _date_to_ecos(
        date.fromisoformat(end_date), cycle
    )

    if ecos_start > ecos_end:
        _log_series_fetch(
            conn, series_id, today,
            start_date, end_date, 0, "ok",
            "Already up to date",
        )
        return

    try:
        ecos = Ecos()
        data = ecos.get_statistic_search(
            통계표코드=series["stat_code"],
            주기=cycle,
            검색시작일자=ecos_start,
            검색종료일자=ecos_end,
            통계항목코드1=series["item_code"],
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

    rows = []
    for item in data.itertuples(index=False):
        obs_date = _ecos_time_to_date(
            getattr(item, "TIME"), cycle
        )
        raw_value = getattr(item, "DATA_VALUE")
        if raw_value in (None, "", "."):
            value = None
        else:
            value = float(str(raw_value).replace(",", ""))
        rows.append((series_id, obs_date, value, today, today))

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
