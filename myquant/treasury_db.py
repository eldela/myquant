"""SQLite data layer for U.S. Treasury Fiscal Data.

This module wraps the :class:`myquant.treasury.Treasury` client and
persists Debt to the Penny records and Treasury securities auction
results in a local SQLite database, along with a fetch history log.
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from myquant.treasury import Treasury

DEFAULT_DB_PATH: Path = Path.home() / "projects/myquant/data/treasury.db"

DEBT_START_DATE = "1993-04-01"
AUCTIONS_START_DATE = "2020-01-01"
PAGE_SIZE = 10000

SCHEMA: str = """
CREATE TABLE IF NOT EXISTS debt (
    record_date          TEXT PRIMARY KEY,
    debt_held_public_amt REAL,
    intragov_hold_amt    REAL,
    tot_pub_debt_out_amt REAL
);

CREATE TABLE IF NOT EXISTS auctions (
    record_date         TEXT,
    cusip               TEXT,
    security_type       TEXT,
    security_term       TEXT,
    auction_date        TEXT,
    issue_date          TEXT,
    maturity_date       TEXT,
    interest_rate       REAL,
    average_price       REAL,
    bid_to_cover_ratio  REAL,
    total_accepted      REAL,
    competitive_accepted REAL,
    PRIMARY KEY (auction_date, cusip)
);

CREATE TABLE IF NOT EXISTS fetch_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset       TEXT NOT NULL,
    fetch_date    TEXT NOT NULL,
    records_added INTEGER,
    status        TEXT DEFAULT 'ok',
    message       TEXT,
    updated_at    TEXT DEFAULT (datetime('now'))
);
"""

__all__ = [
    "DEFAULT_DB_PATH",
    "init_db",
    "fetch_debt",
    "fetch_auctions",
    "fetch_all",
    "get_debt_history",
    "get_auction_history",
    "get_latest_debt",
    "get_latest_auction",
]


def _today_str() -> str:
    """Return today's date as an ISO string."""
    return datetime.now().date().isoformat()


def _ensure_db_dir(db_path: Path) -> None:
    """Create the parent directory for ``db_path`` if it does not exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)


def _connection(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with row factories enabled."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _next_date(d: date) -> date:
    """Return the day after ``d``."""
    return d + timedelta(days=1)


def _max_date(conn: sqlite3.Connection, table: str, column: str) -> Optional[date]:
    """Return the maximum date stored in ``table.column`` or ``None``."""
    row = conn.execute(
        f"SELECT MAX({column}) AS max_date FROM {table}"
    ).fetchone()
    if row is None or row["max_date"] is None:
        return None
    return date.fromisoformat(row["max_date"])


def _log_fetch(
    conn: sqlite3.Connection,
    dataset: str,
    records_added: int,
    status: str,
    message: Optional[str] = None,
) -> None:
    """Insert a row into the fetch history log."""
    conn.execute(
        "INSERT INTO fetch_log (dataset, fetch_date, records_added, status, message) "
        "VALUES (?, ?, ?, ?, ?)",
        (dataset, _today_str(), records_added, status, message),
    )
    conn.commit()


def _to_float(value: Any) -> Optional[float]:
    """Cast a string API value to float, mapping blanks/errors to ``None``."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fetch_all_pages(
    method: Callable[..., List[Dict[str, Any]]],
    filters: str,
    sort: str,
) -> List[Dict[str, Any]]:
    """Retrieve all pages for a query, stopping on a short page."""
    rows: List[Dict[str, Any]] = []
    page = 1
    while True:
        data = method(page=page, page_size=PAGE_SIZE, filters=filters, sort=sort)
        rows.extend(data)
        if len(data) < PAGE_SIZE:
            break
        page += 1
    return rows


def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Create the database and tables."""
    _ensure_db_dir(db_path)
    with _connection(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def fetch_debt(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    """Fetch Debt to the Penny records and store them in the database.

    When ``start_date`` is omitted, fetching resumes from the day after
    the latest stored record, or from 1993-04-01 if the table is empty.
    ``end_date`` defaults to today.
    """
    _ensure_db_dir(db_path)
    with _connection(db_path) as conn:
        if end_date is None:
            end_date = _today_str()
        if start_date is None:
            latest = _max_date(conn, "debt", "record_date")
            start_date = (
                _next_date(latest).isoformat() if latest else DEBT_START_DATE
            )

        try:
            treasury = Treasury()
            data = _fetch_all_pages(
                treasury.get_debt,
                filters=f"record_date:gte:{start_date},record_date:lte:{end_date}",
                sort="record_date",
            )
        except Exception as exc:
            _log_fetch(conn, "debt", 0, "error", str(exc))
            return

        if not data:
            _log_fetch(conn, "debt", 0, "ok", "No records returned")
            return

        rows = [
            (
                r.get("record_date"),
                _to_float(r.get("debt_held_public_amt")),
                _to_float(r.get("intragov_hold_amt")),
                _to_float(r.get("tot_pub_debt_out_amt")),
            )
            for r in data
            if r.get("record_date")
        ]
        conn.executemany(
            "INSERT OR REPLACE INTO debt "
            "(record_date, debt_held_public_amt, intragov_hold_amt, tot_pub_debt_out_amt) "
            "VALUES (?, ?, ?, ?)",
            rows,
        )
        _log_fetch(conn, "debt", len(rows), "ok")


def fetch_auctions(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    """Fetch Treasury auction results and store them in the database.

    When ``start_date`` is omitted, fetching resumes from the day after
    the latest stored auction, or from 2020-01-01 if the table is empty.
    ``end_date`` defaults to today.
    """
    _ensure_db_dir(db_path)
    with _connection(db_path) as conn:
        if end_date is None:
            end_date = _today_str()
        if start_date is None:
            latest = _max_date(conn, "auctions", "auction_date")
            start_date = (
                _next_date(latest).isoformat() if latest else AUCTIONS_START_DATE
            )

        try:
            treasury = Treasury()
            data = _fetch_all_pages(
                treasury.get_auctions,
                filters=f"auction_date:gte:{start_date},auction_date:lte:{end_date}",
                sort="-auction_date",
            )
        except Exception as exc:
            _log_fetch(conn, "auctions", 0, "error", str(exc))
            return

        if not data:
            _log_fetch(conn, "auctions", 0, "ok", "No records returned")
            return

        rows = [
            (
                r.get("record_date"),
                r.get("cusip"),
                r.get("security_type"),
                r.get("security_term"),
                r.get("auction_date"),
                r.get("issue_date"),
                r.get("maturity_date"),
                _to_float(r.get("interest_rate")),
                _to_float(r.get("average_price")),
                _to_float(r.get("bid_to_cover_ratio")),
                _to_float(r.get("total_accepted")),
                _to_float(r.get("competitive_accepted")),
            )
            for r in data
            if r.get("auction_date") and r.get("cusip")
        ]
        conn.executemany(
            "INSERT OR REPLACE INTO auctions "
            "(record_date, cusip, security_type, security_term, auction_date, "
            "issue_date, maturity_date, interest_rate, average_price, "
            "bid_to_cover_ratio, total_accepted, competitive_accepted) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        _log_fetch(conn, "auctions", len(rows), "ok")


def fetch_all(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Fetch both Treasury datasets."""
    for name, fetch in (("debt", fetch_debt), ("auctions", fetch_auctions)):
        try:
            fetch(db_path=db_path)
        except Exception as exc:
            print(f"Error fetching {name}: {exc}")


def get_debt_history(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> pd.DataFrame:
    """Return debt records as a DataFrame ordered by record date."""
    query = "SELECT * FROM debt"
    params: List[Any] = []
    clauses = []
    if start_date is not None:
        clauses.append("record_date >= ?")
        params.append(start_date)
    if end_date is not None:
        clauses.append("record_date <= ?")
        params.append(end_date)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY record_date"
    with _connection(db_path) as conn:
        return pd.read_sql_query(query, conn, params=params)


def get_auction_history(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    security_type: Optional[str] = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> pd.DataFrame:
    """Return auction records as a DataFrame ordered by auction date."""
    query = "SELECT * FROM auctions"
    params: List[Any] = []
    clauses = []
    if start_date is not None:
        clauses.append("auction_date >= ?")
        params.append(start_date)
    if end_date is not None:
        clauses.append("auction_date <= ?")
        params.append(end_date)
    if security_type is not None:
        clauses.append("security_type = ?")
        params.append(security_type)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY auction_date"
    with _connection(db_path) as conn:
        return pd.read_sql_query(query, conn, params=params)


def get_latest_debt(db_path: Path = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    """Return the most recent debt record."""
    with _connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM debt ORDER BY record_date DESC LIMIT 1"
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def get_latest_auction(
    security_type: Optional[str] = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> Optional[Dict[str, Any]]:
    """Return the most recent auction record, optionally by security type."""
    query = "SELECT * FROM auctions"
    params: List[Any] = []
    if security_type is not None:
        query += " WHERE security_type = ?"
        params.append(security_type)
    query += " ORDER BY auction_date DESC LIMIT 1"
    with _connection(db_path) as conn:
        row = conn.execute(query, params).fetchone()
    if row is None:
        return None
    return dict(row)


def _status(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Print row counts and last fetch information per dataset."""
    with _connection(db_path) as conn:
        debt_count = conn.execute("SELECT COUNT(*) AS c FROM debt").fetchone()["c"]
        auctions_count = conn.execute(
            "SELECT COUNT(*) AS c FROM auctions"
        ).fetchone()["c"]
        df = pd.read_sql_query(
            """
            SELECT dataset,
                   MAX(fetch_date)    AS last_fetch,
                   SUM(records_added) AS total_added,
                   SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS errors
            FROM fetch_log
            GROUP BY dataset
            ORDER BY dataset
            """,
            conn,
        )
    print(f"Database: {db_path}")
    print(f"debt rows:     {debt_count}")
    print(f"auctions rows: {auctions_count}")
    if not df.empty:
        print()
        print(df.to_string(index=False))


def _main() -> None:
    """Command-line interface for the Treasury SQLite data layer."""
    parser = argparse.ArgumentParser(description="Treasury SQLite data layer")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Path to the SQLite database",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Create DB and tables")
    subparsers.add_parser("fetch-debt", help="Fetch Debt to the Penny records")
    subparsers.add_parser("fetch-auctions", help="Fetch auction results")
    subparsers.add_parser("fetch-all", help="Fetch both datasets")
    subparsers.add_parser("status", help="Show row counts and last fetch dates")

    args = parser.parse_args()

    if args.command == "init":
        init_db(args.db_path)
        print(f"Initialized database at {args.db_path}")
    elif args.command == "fetch-debt":
        fetch_debt(db_path=args.db_path)
    elif args.command == "fetch-auctions":
        fetch_auctions(db_path=args.db_path)
    elif args.command == "fetch-all":
        fetch_all(db_path=args.db_path)
    elif args.command == "status":
        _status(args.db_path)


if __name__ == "__main__":
    _main()
