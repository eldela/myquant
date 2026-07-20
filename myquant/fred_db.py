"""SQLite data layer for core FRED economic series.

This module wraps the :class:`myquant.fred.Fred` client and persists
observations, series metadata, and fetch history in a local SQLite database.
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from myquant.fred import Fred, FredAPIError

DEFAULT_DB_PATH: Path = Path.home() / "projects/myquant/data/fred.db"

CORE_SERIES: List[Dict[str, str]] = [
    {
        "id": "FEDFUNDS",
        "title": "Federal Funds Effective Rate",
        "frequency": "M",
        "units": "Percent",
        "start_date": "1990-01-01",
    },
    {
        "id": "DGS10",
        "title": "10-Year Treasury Constant Maturity Rate",
        "frequency": "D",
        "units": "Percent",
        "start_date": "1990-01-01",
    },
    {
        "id": "DGS2",
        "title": "2-Year Treasury Constant Maturity Rate",
        "frequency": "D",
        "units": "Percent",
        "start_date": "1990-01-01",
    },
    {
        "id": "T10Y2Y",
        "title": "Treasury Spread 10Y minus 2Y",
        "frequency": "D",
        "units": "Percent",
        "start_date": "1990-01-01",
    },
    {
        "id": "BAMLH0A0HYM2",
        "title": "ICE BofA US High Yield OAS",
        "frequency": "D",
        "units": "Percent",
        "start_date": "1990-01-01",
    },
    {
        "id": "CPIAUCSL",
        "title": "CPI All Urban Consumers (SA)",
        "frequency": "M",
        "units": "Index 1982-84=100",
        "start_date": "1990-01-01",
    },
    {
        "id": "CPILFESL",
        "title": "CPI Less Food and Energy (SA)",
        "frequency": "M",
        "units": "Index 1982-84=100",
        "start_date": "1990-01-01",
    },
    {
        "id": "T10YIE",
        "title": "10-Year Breakeven Inflation Rate",
        "frequency": "D",
        "units": "Percent",
        "start_date": "1990-01-01",
    },
    {
        "id": "DTWEXBGS",
        "title": "Trade Weighted U.S. Dollar Index: Broad",
        "frequency": "D",
        "units": "Index",
        "start_date": "1990-01-01",
    },
    {
        "id": "DEXKOUS",
        "title": "US Dollar to South Korean Won",
        "frequency": "D",
        "units": "KRW/USD",
        "start_date": "1990-01-01",
    },
    {
        "id": "GOLDAMGBD228NLBM",
        "title": "Gold Fixing Price (London AM)",
        "frequency": "D",
        "units": "USD/Troy oz",
        "start_date": "1990-01-01",
    },
    {
        "id": "DCOILWTICO",
        "title": "WTI Crude Oil Spot Price",
        "frequency": "D",
        "units": "USD/barrel",
        "start_date": "1990-01-01",
    },
    {
        "id": "GDPC1",
        "title": "Real Gross Domestic Product",
        "frequency": "Q",
        "units": "Billions of 2017 USD",
        "start_date": "1990-01-01",
    },
    {
        "id": "UMCSENT",
        "title": "University of Michigan Consumer Sentiment",
        "frequency": "M",
        "units": "Index 1966Q1=100",
        "start_date": "1990-01-01",
    },
    {
        "id": "UNRATE",
        "title": "Unemployment Rate",
        "frequency": "M",
        "units": "Percent",
        "start_date": "1990-01-01",
    },
    {
        "id": "PAYEMS",
        "title": "All Employees, Total Nonfarm",
        "frequency": "M",
        "units": "Thousands",
        "start_date": "1990-01-01",
    },
    {
        "id": "SP500",
        "title": "S&P 500 Index",
        "frequency": "D",
        "units": "Index",
        "start_date": "1990-01-01",
    },
    {
        "id": "VIXCLS",
        "title": "CBOE Volatility Index",
        "frequency": "D",
        "units": "Index",
        "start_date": "1990-01-01",
    },
    {
        "id": "M2SL",
        "title": "M2 Money Supply",
        "frequency": "M",
        "units": "Billions of USD",
        "start_date": "1990-01-01",
    },
]

SCHEMA: str = """
CREATE TABLE IF NOT EXISTS series (
    id              TEXT PRIMARY KEY,
    title           TEXT,
    frequency       TEXT NOT NULL,
    units           TEXT,
    observation_start DATE,
    observation_end   DATE,
    last_updated    TEXT
);

CREATE TABLE IF NOT EXISTS observations (
    series_id   TEXT NOT NULL,
    date        TEXT NOT NULL,
    value       REAL,
    realtime_start TEXT,
    realtime_end   TEXT,
    PRIMARY KEY (series_id, date),
    FOREIGN KEY (series_id) REFERENCES series(id)
);

CREATE TABLE IF NOT EXISTS update_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id       TEXT NOT NULL,
    fetch_date      TEXT NOT NULL,
    observation_start TEXT,
    observation_end   TEXT,
    rows_added      INTEGER,
    status          TEXT DEFAULT 'ok',
    message         TEXT,
    updated_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (series_id) REFERENCES series(id)
);
"""

__all__ = [
    "DEFAULT_DB_PATH",
    "CORE_SERIES",
    "init_db",
    "fetch_series",
    "fetch_all",
    "fetch_due",
    "get_latest",
    "get_history",
    "get_series_info",
]


def _today() -> date:
    """Return today's date."""
    return datetime.now().date()


def _today_str() -> str:
    """Return today's date as an ISO string."""
    return _today().isoformat()


def _ensure_db_dir(db_path: Path) -> None:
    """Create the parent directory for ``db_path`` if it does not exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)


def _connection(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with row factories enabled."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _series_from_registry(series_id: str) -> Optional[Dict[str, str]]:
    """Return the registry entry for ``series_id`` if it exists."""
    for s in CORE_SERIES:
        if s["id"] == series_id:
            return s
    return None


def _latest_observation_date(
    conn: sqlite3.Connection, series_id: str
) -> Optional[date]:
    """Return the latest observation date for ``series_id`` or ``None``."""
    row = conn.execute(
        "SELECT MAX(date) as max_date FROM observations WHERE series_id = ?",
        (series_id,),
    ).fetchone()
    if row is None or row["max_date"] is None:
        return None
    return date.fromisoformat(row["max_date"])


def _next_date(d: date) -> date:
    """Return the day after ``d``."""
    return d + timedelta(days=1)


def _get_last_fetch_date(
    conn: sqlite3.Connection, series_id: str
) -> Optional[date]:
    """Return the date of the last successful fetch for ``series_id`` or ``None``."""
    row = conn.execute(
        "SELECT MAX(fetch_date) as last_fetch FROM update_log "
        "WHERE series_id = ? AND status = 'ok'",
        (series_id,),
    ).fetchone()
    if row is None or row["last_fetch"] is None:
        return None
    return date.fromisoformat(row["last_fetch"])


def _log_fetch(
    conn: sqlite3.Connection,
    series_id: str,
    fetch_date: str,
    observation_start: str,
    observation_end: str,
    rows_added: int,
    status: str,
    message: Optional[str] = None,
) -> None:
    """Insert a row into the fetch history log."""
    conn.execute(
        "INSERT INTO update_log "
        "(series_id, fetch_date, observation_start, observation_end, rows_added, status, message) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            series_id,
            fetch_date,
            observation_start,
            observation_end,
            rows_added,
            status,
            message,
        ),
    )
    if status == "ok":
        conn.execute(
            "UPDATE series SET last_updated = ? WHERE id = ?",
            (datetime.now().isoformat(), series_id),
        )
    conn.commit()


def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Create the database, tables, and seed the core series registry."""
    _ensure_db_dir(db_path)
    with _connection(db_path) as conn:
        conn.executescript(SCHEMA)
        for s in CORE_SERIES:
            conn.execute(
                "INSERT INTO series (id, title, frequency, units, observation_start) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "title=excluded.title, frequency=excluded.frequency, "
                "units=excluded.units, observation_start=excluded.observation_start",
                (s["id"], s["title"], s["frequency"], s["units"], s["start_date"]),
            )
        conn.commit()


def _resolve_fetch_window(
    conn: sqlite3.Connection,
    series_id: str,
    start_date: Optional[str],
    end_date: Optional[str],
) -> Tuple[str, str]:
    """Resolve the observation window for a fetch."""
    if end_date is None:
        end_date = _today_str()
    if start_date is None:
        latest = _latest_observation_date(conn, series_id)
        if latest is not None:
            start_date = _next_date(latest).isoformat()
        else:
            series = _series_from_registry(series_id)
            if series is None:
                raise ValueError(f"Unknown series: {series_id}")
            start_date = series["start_date"]
    return start_date, end_date


def fetch_series(
    series_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    """Fetch observations for ``series_id`` and store them in the database.

    Parameters
    ----------
    series_id
        FRED series identifier.
    start_date
        Optional start of the observation window (YYYY-MM-DD). When omitted,
        fetching resumes from the day after the latest stored observation or
        the series' registry start date if no observations exist.
    end_date
        Optional end of the observation window (YYYY-MM-DD). Defaults to today.
    db_path
        Path to the SQLite database.
    """
    _ensure_db_dir(db_path)
    with _connection(db_path) as conn:
        start_date, end_date = _resolve_fetch_window(
            conn, series_id, start_date, end_date
        )
        today = _today_str()
        try:
            fred = Fred()
            data = fred.get_data(
                "series_observations",
                series_id=series_id,
                observation_start=start_date,
                observation_end=end_date,
            )
        except Exception as exc:
            _log_fetch(
                conn,
                series_id,
                today,
                start_date,
                end_date,
                0,
                "error",
                str(exc),
            )
            return

        if not isinstance(data, pd.DataFrame) or data.empty:
            _log_fetch(
                conn,
                series_id,
                today,
                start_date,
                end_date,
                0,
                "ok",
                "No observations returned",
            )
            return

        df = data[["date", "value", "realtime_start", "realtime_end"]].copy()
        df["series_id"] = series_id
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.where(pd.notnull(df), None)
        rows = [
            (row.series_id, row.date, row.value, row.realtime_start, row.realtime_end)
            for row in df.itertuples(index=False)
        ]
        conn.executemany(
            "INSERT OR REPLACE INTO observations "
            "(series_id, date, value, realtime_start, realtime_end) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        _log_fetch(
            conn,
            series_id,
            today,
            start_date,
            end_date,
            len(rows),
            "ok",
        )


def fetch_all(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    """Fetch observations for all core series."""
    for s in CORE_SERIES:
        try:
            fetch_series(s["id"], start_date, end_date, db_path)
        except Exception as exc:
            print(f"Error fetching {s['id']}: {exc}")


def _last_monday(d: date) -> date:
    """Return the Monday of the week containing ``d``."""
    return d - timedelta(days=d.weekday())


def _is_due_weekly(today: date, last_fetch: Optional[date]) -> bool:
    """Return whether a weekly series should be fetched today."""
    if last_fetch is None:
        return True
    last_monday = _last_monday(today)
    return today >= last_monday and last_fetch < last_monday


def _is_due_monthly(today: date, last_fetch: Optional[date]) -> bool:
    """Return whether a monthly series should be fetched today."""
    if today.day > 5:
        return False
    if last_fetch is None:
        return True
    first_of_month = today.replace(day=1)
    return last_fetch < first_of_month


def _quarter_end(d: date) -> date:
    """Return the last day of the quarter immediately before ``d``."""
    q = (d.month - 1) // 3
    if q == 0:
        return date(d.year - 1, 12, 31)
    if q == 1:
        return date(d.year, 3, 31)
    if q == 2:
        return date(d.year, 6, 30)
    return date(d.year, 9, 30)


def _is_due_quarterly(today: date, last_fetch: Optional[date]) -> bool:
    """Return whether a quarterly series should be fetched today."""
    q_end = _quarter_end(today)
    days_after = (today - q_end).days
    if days_after < 1 or days_after > 30:
        return False
    if last_fetch is None:
        return True
    return last_fetch <= q_end


def _is_due(frequency: str, today: date, last_fetch: Optional[date]) -> bool:
    """Return whether a series with ``frequency`` is due for a fetch."""
    if frequency == "D":
        return True
    if frequency == "W":
        return _is_due_weekly(today, last_fetch)
    if frequency == "M":
        return _is_due_monthly(today, last_fetch)
    if frequency == "Q":
        return _is_due_quarterly(today, last_fetch)
    raise ValueError(f"Unknown frequency: {frequency}")


def fetch_due(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Fetch series that are due for update based on their frequency."""
    today = _today()
    with _connection(db_path) as conn:
        for s in CORE_SERIES:
            last_fetch = _get_last_fetch_date(conn, s["id"])
            if _is_due(s["frequency"], today, last_fetch):
                try:
                    fetch_series(s["id"], db_path=db_path)
                except Exception as exc:
                    print(f"Error fetching {s['id']}: {exc}")


def get_latest(
    series_id: str, db_path: Path = DEFAULT_DB_PATH
) -> Optional[Dict[str, Any]]:
    """Return the latest observation row for ``series_id``."""
    with _connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM observations WHERE series_id = ? ORDER BY date DESC LIMIT 1",
            (series_id,),
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def get_history(
    series_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> pd.DataFrame:
    """Return all observations for ``series_id`` as a DataFrame."""
    query = "SELECT * FROM observations WHERE series_id = ?"
    params: List[Any] = [series_id]
    if start_date is not None:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date is not None:
        query += " AND date <= ?"
        params.append(end_date)
    query += " ORDER BY date"
    with _connection(db_path) as conn:
        return pd.read_sql_query(query, conn, params=params)


def get_series_info(db_path: Path = DEFAULT_DB_PATH) -> pd.DataFrame:
    """Return the ``series`` table as a DataFrame."""
    with _connection(db_path) as conn:
        return pd.read_sql_query(
            "SELECT * FROM series ORDER BY id", conn
        )


def _status(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Print series info, observation counts, and last fetch dates."""
    with _connection(db_path) as conn:
        df = pd.read_sql_query(
            """
            SELECT
                s.id,
                s.title,
                s.frequency,
                COUNT(DISTINCT o.date) AS observations,
                MAX(u.fetch_date) AS last_fetch,
                MAX(u.rows_added) AS last_rows_added
            FROM series s
            LEFT JOIN observations o ON s.id = o.series_id
            LEFT JOIN update_log u ON s.id = u.series_id AND u.status = 'ok'
            GROUP BY s.id
            ORDER BY s.id
            """,
            conn,
        )
    print(df.to_string(index=False))


def _main() -> None:
    """Command-line interface for the FRED SQLite data layer."""
    parser = argparse.ArgumentParser(description="FRED SQLite data layer")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Path to the SQLite database",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Create DB and populate series")
    subparsers.add_parser("fetch-all", help="Fetch all series")
    subparsers.add_parser("fetch-due", help="Fetch only due series")
    subparsers.add_parser("status", help="Show series info and last fetch dates")

    args = parser.parse_args()

    if args.command == "init":
        init_db(args.db_path)
        print(f"Initialized database at {args.db_path}")
    elif args.command == "fetch-all":
        fetch_all(db_path=args.db_path)
    elif args.command == "fetch-due":
        fetch_due(db_path=args.db_path)
    elif args.command == "status":
        _status(args.db_path)


if __name__ == "__main__":
    _main()
