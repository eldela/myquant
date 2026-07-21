"""Normalize heterogeneous-frequency data into a unified daily table.

Macro series (FRED/ECOS) and market prices (pykrx/yfinance) are resampled to a
single ``normalized_daily`` table so downstream analysis can join by date.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from myquant.db.core import DEFAULT_DB_PATH, _connection, _ensure_db_dir

# =============================================================================
# Schema
# =============================================================================

NORMALIZATION_SCHEMA: str = """
-- TABLE: normalized_daily — unified daily-frequency data
CREATE TABLE IF NOT EXISTS normalized_daily (
    series_id    TEXT NOT NULL,
    date         TEXT NOT NULL,
    value        REAL,
    source       TEXT NOT NULL CHECK(source IN ('FRED', 'ECOS', 'pykrx', 'yfinance')),
    asset_type   TEXT CHECK(asset_type IN ('macro', 'index', 'etf')),
    PRIMARY KEY (series_id, date)
);

CREATE INDEX IF NOT EXISTS idx_normalized_daily_series_date
    ON normalized_daily(series_id, date);

CREATE INDEX IF NOT EXISTS idx_normalized_daily_date
    ON normalized_daily(date);
"""


# =============================================================================
# Resampling helpers
# =============================================================================


def _resample_to_daily(
    df: pd.DataFrame,
    freq: str,
) -> pd.DataFrame:
    """Resample series observations to a daily frequency.

    Parameters
    ----------
    df
        DataFrame with ``date`` and ``value`` columns. ``value`` may contain
        numeric values or string representations.
    freq
        Original frequency: ``'D'``, ``'M'``, or ``'Q'``.

    Returns
    -------
    pd.DataFrame
        DataFrame with daily-frequency ``date`` and ``value`` columns. Values
        are forward-filled from the first day of each period.

    Raises
    ------
    ValueError
        If ``freq`` is not one of the supported frequencies.
    """
    if freq == "D":
        result = df.copy()
        result["value"] = pd.to_numeric(result["value"], errors="coerce")
        return result

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.set_index("date").sort_index()

    if freq == "M":
        # Value is assigned to the first day of the month, then forward-filled.
        resampled = df.resample("MS").first()
    elif freq == "Q":
        # Value is assigned to the first day of the quarter, then forward-filled.
        resampled = df.resample("QS").first()
    else:
        raise ValueError(f"Unknown frequency: {freq}")

    daily = resampled.resample("D").ffill()

    daily = daily.reset_index()
    daily["date"] = daily["date"].dt.strftime("%Y-%m-%d")
    return daily


def _filter_date_range(
    df: pd.DataFrame,
    start_date: Optional[str],
    end_date: Optional[str],
) -> pd.DataFrame:
    """Filter a DataFrame with an ISO ``date`` column by inclusive date range."""
    if start_date is not None:
        df = df[df["date"] >= start_date]
    if end_date is not None:
        df = df[df["date"] <= end_date]
    return df


# =============================================================================
# Initialization
# =============================================================================


def init_normalization_tables(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Create the ``normalized_daily`` table and its indexes.

    Safe to call multiple times (``IF NOT EXISTS``).
    """
    _ensure_db_dir(db_path)
    with _connection(db_path) as conn:
        conn.executescript(NORMALIZATION_SCHEMA)
        conn.commit()


# =============================================================================
# Macro series normalization
# =============================================================================


def normalize_series(
    series_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> int:
    """Normalize a single macro series into ``normalized_daily``.

    Parameters
    ----------
    series_id
        Series identifier (e.g. ``"DGS10"`` or ``"901Y009_0"``).
    start_date
        Optional ISO start date to limit the output range (inclusive).
    end_date
        Optional ISO end date to limit the output range (inclusive).
    db_path
        Path to the SQLite database.

    Returns
    -------
    int
        Number of rows inserted or replaced in ``normalized_daily``.
    """
    _ensure_db_dir(db_path)
    with _connection(db_path) as conn:
        series_row = conn.execute(
            "SELECT source, frequency FROM series WHERE id = ?", (series_id,)
        ).fetchone()
        if series_row is None:
            raise ValueError(f"Unknown series: {series_id}")

        source: str = series_row["source"]
        freq: str = series_row["frequency"]

        df = pd.read_sql_query(
            "SELECT date, value FROM observations WHERE series_id = ? ORDER BY date",
            conn,
            params=(series_id,),
        )

    if df.empty:
        return 0

    daily = _resample_to_daily(df, freq)
    daily = _filter_date_range(daily, start_date, end_date)

    if daily.empty:
        return 0

    rows = [
        (series_id, row.date, row.value, source, "macro")
        for row in daily.itertuples(index=False)
    ]

    _ensure_db_dir(db_path)
    with _connection(db_path) as conn:
        conn.executescript(NORMALIZATION_SCHEMA)
        conn.executemany(
            "INSERT OR REPLACE INTO normalized_daily "
            "(series_id, date, value, source, asset_type) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()

    return len(rows)


def normalize_all(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> Dict[str, int]:
    """Normalize all macro series into ``normalized_daily``.

    Parameters
    ----------
    start_date
        Optional ISO start date to limit the output range.
    end_date
        Optional ISO end date to limit the output range.
    db_path
        Path to the SQLite database.

    Returns
    -------
    Dict[str, int]
        Mapping ``series_id -> rows_inserted``.
    """
    _ensure_db_dir(db_path)
    results: Dict[str, int] = {}
    with _connection(db_path) as conn:
        rows = conn.execute(
            "SELECT id FROM series ORDER BY id"
        ).fetchall()

    for row in rows:
        series_id = row["id"]
        try:
            results[series_id] = normalize_series(
                series_id, start_date, end_date, db_path
            )
        except Exception as exc:
            print(f"Error normalizing {series_id}: {exc}")
            results[series_id] = 0

    return results


# =============================================================================
# Market data normalization
# =============================================================================


def normalize_market_data(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> Dict[str, int]:
    """Normalize market prices into ``normalized_daily``.

    Uses the adjusted close price when available, falling back to close price.

    Parameters
    ----------
    start_date
        Optional ISO start date to limit the output range.
    end_date
        Optional ISO end date to limit the output range.
    db_path
        Path to the SQLite database.

    Returns
    -------
    Dict[str, int]
        Mapping ``symbol -> rows_inserted``.
    """
    _ensure_db_dir(db_path)
    results: Dict[str, int] = {}

    with _connection(db_path) as conn:
        symbols = conn.execute(
            "SELECT DISTINCT symbol FROM market_prices ORDER BY symbol"
        ).fetchall()

    for symbol_row in symbols:
        symbol = symbol_row["symbol"]
        try:
            results[symbol] = _normalize_one_symbol(
                symbol, start_date, end_date, db_path
            )
        except Exception as exc:
            print(f"Error normalizing market data for {symbol}: {exc}")
            results[symbol] = 0

    return results


def _normalize_one_symbol(
    symbol: str,
    start_date: Optional[str],
    end_date: Optional[str],
    db_path: Path,
) -> int:
    """Normalize a single market symbol into ``normalized_daily``."""
    query = (
        "SELECT symbol, date, close, adj_close, source, asset_type "
        "FROM market_prices WHERE symbol = ? ORDER BY date"
    )
    with _connection(db_path) as conn:
        df = pd.read_sql_query(query, conn, params=(symbol,))

    if df.empty:
        return 0

    # Prefer adjusted close; fall back to close for older/spot data.
    df["value"] = df["adj_close"].where(df["adj_close"].notna(), df["close"])
    df = df[df["value"].notna()]

    if df.empty:
        return 0

    # Market data is already daily; no frequency conversion needed.
    daily = df[["date", "value"]].copy()
    daily = _filter_date_range(daily, start_date, end_date)

    if daily.empty:
        return 0

    source = str(df["source"].iloc[0])
    asset_type = str(df["asset_type"].iloc[0])

    rows = [
        (symbol, row.date, row.value, source, asset_type)
        for row in daily.itertuples(index=False)
    ]

    with _connection(db_path) as conn:
        conn.executescript(NORMALIZATION_SCHEMA)
        conn.executemany(
            "INSERT OR REPLACE INTO normalized_daily "
            "(series_id, date, value, source, asset_type) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()

    return len(rows)


# =============================================================================
# Query API
# =============================================================================


def get_normalized_history(
    series_id: str,
    days: int = 365,
    db_path: Path = DEFAULT_DB_PATH,
) -> pd.DataFrame:
    """Return normalized daily history for ``series_id``.

    Parameters
    ----------
    series_id
        Series or symbol identifier.
    days
        Number of calendar days to look back.
    db_path
        Path to the SQLite database.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns ``series_id``, ``date``, ``value``, ``source``,
        ``asset_type`` ordered by date.
    """
    from datetime import date, timedelta

    start = (date.today() - timedelta(days=days)).isoformat()
    query = (
        "SELECT * FROM normalized_daily "
        "WHERE series_id = ? AND date >= ? "
        "ORDER BY date"
    )
    with _connection(db_path) as conn:
        return pd.read_sql_query(query, conn, params=(series_id, start))


def get_normalized_status(db_path: Path = DEFAULT_DB_PATH) -> pd.DataFrame:
    """Return a summary of ``normalized_daily`` contents.

    Returns
    -------
    pd.DataFrame
        One row per ``series_id`` with source, asset_type, row count, and the
        earliest/latest dates. Returns an empty DataFrame if the table does not
        exist yet.
    """
    _ensure_db_dir(db_path)
    with _connection(db_path) as conn:
        try:
            return pd.read_sql_query(
                """
                SELECT
                    series_id,
                    source,
                    asset_type,
                    COUNT(*) AS row_count,
                    MIN(date) AS earliest_date,
                    MAX(date) AS latest_date
                FROM normalized_daily
                GROUP BY series_id, source, asset_type
                ORDER BY series_id
                """,
                conn,
            )
        except pd.errors.DatabaseError:
            # Table does not exist yet; return an empty summary.
            return pd.DataFrame(
                columns=[
                    "series_id",
                    "source",
                    "asset_type",
                    "row_count",
                    "earliest_date",
                    "latest_date",
                ]
            )
