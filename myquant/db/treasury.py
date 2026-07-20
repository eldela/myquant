"""Treasury-specific fetch and query functions.

All Treasury data (Debt to the Penny, securities auctions) is stored
in the same ``macro.db`` database but in separate tables (``debt``,
``auctions``, ``fetch_log``) with no FK links to the ``series`` table.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from myquant.db.core import (
    AUCTIONS_START_DATE,
    DEBT_START_DATE,
    DEFAULT_DB_PATH,
    PAGE_SIZE,
    _connection,
    _ensure_db_dir,
    _today_str,
)
from myquant.treasury import Treasury


# =============================================================================
# Treasury helpers
# =============================================================================


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


def _to_float(value: Any) -> Optional[float]:
    """Cast a string API value to float, mapping blanks/errors to ``None``."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


# =============================================================================
# Treasury — fetch
# =============================================================================


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


def fetch_all_treasury(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Fetch both Treasury datasets."""
    for name, fetch in (("debt", fetch_debt), ("auctions", fetch_auctions)):
        try:
            fetch(db_path=db_path)
        except Exception as exc:
            print(f"Error fetching {name}: {exc}")


# =============================================================================
# Treasury — query
# =============================================================================


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
