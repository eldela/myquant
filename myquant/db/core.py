"""Core utilities, constants, and unified series API for the macro database.

This module provides the shared foundation used by all other ``myquant.db``
submodules: utility helpers, the series registry, the database schema,
initialization, due-date scheduling, and the unified fetch/query API for
FRED and ECOS time-series data.

.. allow: SIZE_OK — CORE_SERIES (~260 lines of registry dicts) and SCHEMA
   (~86 lines of DDL) are pure data declarations, not logic. The actual
   operational code (~371 LOC) is well under the guardrail.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# =============================================================================
# Constants
# =============================================================================

DEFAULT_DB_PATH: Path = Path.home() / "projects/myquant/data/macro.db"

DEBT_START_DATE = "1993-04-01"
AUCTIONS_START_DATE = "2020-01-01"
PAGE_SIZE = 10000

# =============================================================================
# Unified CORE_SERIES registry — 19 FRED + 9 ECOS = 28 series
# =============================================================================

CORE_SERIES: List[Dict[str, Optional[str]]] = [
    # =========================================================================
    # FRED — United States (19 series)
    # =========================================================================
    {
        "id": "FEDFUNDS",
        "title": "Federal Funds Effective Rate",
        "source": "FRED",
        "frequency": "M",
        "cycle": "M",
        "units": "Percent",
        "start_date": "1990-01-01",
    },
    {
        "id": "DGS10",
        "title": "10-Year Treasury Constant Maturity Rate",
        "source": "FRED",
        "frequency": "D",
        "cycle": "D",
        "units": "Percent",
        "start_date": "1990-01-01",
    },
    {
        "id": "DGS2",
        "title": "2-Year Treasury Constant Maturity Rate",
        "source": "FRED",
        "frequency": "D",
        "cycle": "D",
        "units": "Percent",
        "start_date": "1990-01-01",
    },
    {
        "id": "T10Y2Y",
        "title": "Treasury Spread 10Y minus 2Y",
        "source": "FRED",
        "frequency": "D",
        "cycle": "D",
        "units": "Percent",
        "start_date": "1990-01-01",
    },
    {
        "id": "BAMLH0A0HYM2",
        "title": "ICE BofA US High Yield OAS",
        "source": "FRED",
        "frequency": "D",
        "cycle": "D",
        "units": "Percent",
        "start_date": "1990-01-01",
    },
    {
        "id": "CPIAUCSL",
        "title": "CPI All Urban Consumers (SA)",
        "source": "FRED",
        "frequency": "M",
        "cycle": "M",
        "units": "Index 1982-84=100",
        "start_date": "1990-01-01",
    },
    {
        "id": "CPILFESL",
        "title": "CPI Less Food and Energy (SA)",
        "source": "FRED",
        "frequency": "M",
        "cycle": "M",
        "units": "Index 1982-84=100",
        "start_date": "1990-01-01",
    },
    {
        "id": "T10YIE",
        "title": "10-Year Breakeven Inflation Rate",
        "source": "FRED",
        "frequency": "D",
        "cycle": "D",
        "units": "Percent",
        "start_date": "1990-01-01",
    },
    {
        "id": "DTWEXBGS",
        "title": "Trade Weighted U.S. Dollar Index: Broad",
        "source": "FRED",
        "frequency": "D",
        "cycle": "D",
        "units": "Index",
        "start_date": "1990-01-01",
    },
    {
        "id": "DEXKOUS",
        "title": "US Dollar to South Korean Won",
        "source": "FRED",
        "frequency": "D",
        "cycle": "D",
        "units": "KRW/USD",
        "start_date": "1990-01-01",
    },
    {
        "id": "GOLDAMGBD228NLBM",
        "title": "Gold Fixing Price (London AM)",
        "source": "FRED",
        "frequency": "D",
        "cycle": "D",
        "units": "USD/Troy oz",
        "start_date": "1990-01-01",
    },
    {
        "id": "DCOILWTICO",
        "title": "WTI Crude Oil Spot Price",
        "source": "FRED",
        "frequency": "D",
        "cycle": "D",
        "units": "USD/barrel",
        "start_date": "1990-01-01",
    },
    {
        "id": "GDPC1",
        "title": "Real Gross Domestic Product",
        "source": "FRED",
        "frequency": "Q",
        "cycle": "Q",
        "units": "Billions of 2017 USD",
        "start_date": "1990-01-01",
    },
    {
        "id": "UMCSENT",
        "title": "University of Michigan Consumer Sentiment",
        "source": "FRED",
        "frequency": "M",
        "cycle": "M",
        "units": "Index 1966Q1=100",
        "start_date": "1990-01-01",
    },
    {
        "id": "UNRATE",
        "title": "Unemployment Rate",
        "source": "FRED",
        "frequency": "M",
        "cycle": "M",
        "units": "Percent",
        "start_date": "1990-01-01",
    },
    {
        "id": "PAYEMS",
        "title": "All Employees, Total Nonfarm",
        "source": "FRED",
        "frequency": "M",
        "cycle": "M",
        "units": "Thousands",
        "start_date": "1990-01-01",
    },
    {
        "id": "SP500",
        "title": "S&P 500 Index",
        "source": "FRED",
        "frequency": "D",
        "cycle": "D",
        "units": "Index",
        "start_date": "1990-01-01",
    },
    {
        "id": "VIXCLS",
        "title": "CBOE Volatility Index",
        "source": "FRED",
        "frequency": "D",
        "cycle": "D",
        "units": "Index",
        "start_date": "1990-01-01",
    },
    {
        "id": "M2SL",
        "title": "M2 Money Supply",
        "source": "FRED",
        "frequency": "M",
        "cycle": "M",
        "units": "Billions of USD",
        "start_date": "1990-01-01",
    },

    # =========================================================================
    # ECOS — South Korea (9 series)
    # =========================================================================
    {
        "id": "901Y009_0",
        "title": "소비자물가지수 총지수",
        "source": "ECOS",
        "frequency": "M",
        "cycle": "M",
        "units": None,
        "start_date": "199001",
        "stat_code": "901Y009",
        "item_code": "0",
    },
    {
        "id": "901Y009_A",
        "title": "소비자물가지수 식료품",
        "source": "ECOS",
        "frequency": "M",
        "cycle": "M",
        "units": None,
        "start_date": "199001",
        "stat_code": "901Y009",
        "item_code": "A",
    },
    {
        "id": "722Y001_0101000",
        "title": "한국은행 기준금리",
        "source": "ECOS",
        "frequency": "M",
        "cycle": "M",
        "units": None,
        "start_date": "199901",
        "stat_code": "722Y001",
        "item_code": "0101000",
    },
    {
        "id": "200Y108_10601",
        "title": "실질국내총생산(GDP)",
        "source": "ECOS",
        "frequency": "Q",
        "cycle": "Q",
        "units": None,
        "start_date": "199001",
        "stat_code": "200Y108",
        "item_code": "10601",
    },
    {
        "id": "102Y004_ABA1",
        "title": "본원통화 M1",
        "source": "ECOS",
        "frequency": "M",
        "cycle": "M",
        "units": None,
        "start_date": "199001",
        "stat_code": "102Y004",
        "item_code": "ABA1",
    },
    {
        "id": "901Y118_T002",
        "title": "수출금액",
        "source": "ECOS",
        "frequency": "M",
        "cycle": "M",
        "units": None,
        "start_date": "199001",
        "stat_code": "901Y118",
        "item_code": "T002",
    },
    {
        "id": "901Y118_T004",
        "title": "수입금액",
        "source": "ECOS",
        "frequency": "M",
        "cycle": "M",
        "units": None,
        "start_date": "199001",
        "stat_code": "901Y118",
        "item_code": "T004",
    },
    {
        "id": "511Y002_FMAA",
        "title": "현재생활형편CSI",
        "source": "ECOS",
        "frequency": "M",
        "cycle": "M",
        "units": None,
        "start_date": "200809",
        "stat_code": "511Y002",
        "item_code": "FMAA",
    },
    {
        "id": "513Y001_E1000",
        "title": "경제심리지수(원계열)",
        "source": "ECOS",
        "frequency": "M",
        "cycle": "M",
        "units": None,
        "start_date": "200301",
        "stat_code": "513Y001",
        "item_code": "E1000",
    },
]

# =============================================================================
# Full unified schema — 6 tables + 2 performance indexes
# =============================================================================

SCHEMA: str = """
-- TABLE 1: series — unified FRED + ECOS metadata
CREATE TABLE IF NOT EXISTS series (
    id               TEXT PRIMARY KEY,
    title            TEXT,
    source           TEXT NOT NULL CHECK(source IN ('FRED', 'ECOS')),
    frequency        TEXT NOT NULL CHECK(frequency IN ('D', 'W', 'M', 'Q')),
    cycle            TEXT NOT NULL CHECK(cycle IN ('D', 'W', 'M', 'Q', 'A')),
    units            TEXT,
    observation_start DATE,
    observation_end   DATE,
    last_updated     TEXT
);

-- TABLE 2: observations — time-series data points (FRED + ECOS)
CREATE TABLE IF NOT EXISTS observations (
    series_id      TEXT NOT NULL,
    date           TEXT NOT NULL,
    value          REAL,
    realtime_start TEXT,
    realtime_end   TEXT,
    PRIMARY KEY (series_id, date),
    FOREIGN KEY (series_id) REFERENCES series(id)
);

CREATE INDEX IF NOT EXISTS idx_observations_series_date
    ON observations(series_id, date);

-- TABLE 3: update_log — fetch history for series-based data (FRED + ECOS)
CREATE TABLE IF NOT EXISTS update_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id         TEXT NOT NULL,
    fetch_date        TEXT NOT NULL,
    observation_start TEXT,
    observation_end   TEXT,
    rows_added        INTEGER,
    status            TEXT DEFAULT 'ok',
    message           TEXT,
    updated_at        TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (series_id) REFERENCES series(id)
);

CREATE INDEX IF NOT EXISTS idx_update_log_series_fetch
    ON update_log(series_id, fetch_date);

-- TABLE 4: debt — Treasury Debt to the Penny (kept separate)
CREATE TABLE IF NOT EXISTS debt (
    record_date          TEXT PRIMARY KEY,
    debt_held_public_amt REAL,
    intragov_hold_amt    REAL,
    tot_pub_debt_out_amt REAL
);

-- TABLE 5: auctions — Treasury securities auctions (kept separate)
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

-- TABLE 6: fetch_log — Treasury fetch history (kept separate)
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


# =============================================================================
# Shared utility helpers
# =============================================================================


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


def _ecos_time_to_date(time_str: str, cycle: str) -> str:
    """Convert an ECOS ``TIME`` value to an ISO date string.

    - Monthly: ``"202401"`` -> ``"2024-01-01"``
    - Quarterly: ``"2024Q1"`` -> ``"2024-01-01"``
    - Daily: ``"20240115"`` -> ``"2024-01-15"``
    - Annual: ``"2024"`` -> ``"2024-01-01"``
    """
    s = time_str.strip()
    if "Q" in s:
        year, quarter = s.split("Q", 1)
        month = (int(quarter) - 1) * 3 + 1
        return f"{year}-{month:02d}-01"
    if s.isdigit() and len(s) == 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    if s.isdigit() and len(s) == 6:
        return f"{s[:4]}-{s[4:6]}-01"
    if s.isdigit() and len(s) == 4:
        return f"{s}-01-01"
    raise ValueError(f"Unrecognized ECOS TIME format: {time_str!r} (cycle={cycle})")


# =============================================================================
# Date conversion helpers (used by fetch window resolution and ECOS fetch)
# =============================================================================


def _date_to_ecos(d: date, cycle: str) -> str:
    """Format ``d`` as an ECOS date string matching ``cycle``."""
    if cycle == "M":
        return f"{d.year}{d.month:02d}"
    if cycle == "Q":
        return f"{d.year}Q{(d.month - 1) // 3 + 1}"
    if cycle == "D":
        return f"{d.year}{d.month:02d}{d.day:02d}"
    if cycle == "A":
        return f"{d.year}"
    raise ValueError(f"Unknown cycle: {cycle}")


def _next_period_start(d: date, cycle: str) -> date:
    """Return the first day of the period after the one containing ``d``."""
    if cycle == "M":
        if d.month == 12:
            return date(d.year + 1, 1, 1)
        return date(d.year, d.month + 1, 1)
    if cycle == "Q":
        quarter_end_month = ((d.month - 1) // 3 + 1) * 3
        if quarter_end_month == 12:
            return date(d.year + 1, 1, 1)
        return date(d.year, quarter_end_month + 1, 1)
    return d + timedelta(days=1)


# =============================================================================
# Database initialization
# =============================================================================


def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Create the database, all tables, and seed the unified series registry.

    Seeds the ``series`` table with all 28 entries from :data:`CORE_SERIES`
    (19 FRED + 9 ECOS).  Every series row includes ``source`` and ``cycle``.
    ECOS ``start_date`` values are converted from native format to ISO via
    :func:`_ecos_time_to_date`.
    """
    _ensure_db_dir(db_path)
    with _connection(db_path) as conn:
        conn.executescript(SCHEMA)
        for s in CORE_SERIES:
            observation_start: str
            if s["source"] == "FRED":
                observation_start = s["start_date"]  # type: ignore[assignment]  # already ISO
            else:
                observation_start = _ecos_time_to_date(
                    s["start_date"],  # type: ignore[arg-type]
                    s["cycle"],  # type: ignore[arg-type]
                )

            conn.execute(
                "INSERT INTO series "
                "(id, title, source, frequency, cycle, units, observation_start) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "title=excluded.title, "
                "source=excluded.source, "
                "frequency=excluded.frequency, "
                "cycle=excluded.cycle, "
                "units=excluded.units, "
                "observation_start=excluded.observation_start",
                (
                    s["id"],
                    s["title"],
                    s["source"],
                    s["frequency"],
                    s["cycle"],
                    s["units"],
                    observation_start,
                ),
            )
        conn.commit()


# =============================================================================
# Series registry helpers
# =============================================================================


def _series_from_registry(series_id: str) -> Optional[Dict[str, Optional[str]]]:
    """Return the registry entry for ``series_id`` from :data:`CORE_SERIES`."""
    for s in CORE_SERIES:
        if s["id"] == series_id:
            return s
    return None


def _series_ids_for_source(source: str) -> List[str]:
    """Return series IDs from :data:`CORE_SERIES` filtered by ``source``."""
    if source == "all":
        return [s["id"] for s in CORE_SERIES]  # type: ignore[misc]
    return [
        s["id"]  # type: ignore[misc]
        for s in CORE_SERIES
        if s["source"] == source.upper()
    ]


# =============================================================================
# Observation / update_log helpers
# =============================================================================


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


def _log_series_fetch(
    conn: sqlite3.Connection,
    series_id: str,
    fetch_date: str,
    observation_start: str,
    observation_end: str,
    rows_added: int,
    status: str,
    message: Optional[str] = None,
) -> None:
    """Insert a row into the ``update_log`` table."""
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


# =============================================================================
# Fetch window resolution
# =============================================================================


def _resolve_fetch_window(
    conn: sqlite3.Connection,
    series_id: str,
    start_date: Optional[str],
    end_date: Optional[str],
) -> Tuple[str, str]:
    """Resolve the observation window for a fetch (ISO date strings).

    FRED: resumes from the day after the latest stored observation.
    ECOS: resumes from the period after the latest stored observation
          (respects the ECOS cycle concept).
    """
    if end_date is None:
        end_date = _today_str()
    if start_date is None:
        series = _series_from_registry(series_id)
        if series is None:
            raise ValueError(f"Unknown series: {series_id}")
        latest = _latest_observation_date(conn, series_id)
        if latest is not None:
            if series["source"] == "FRED":
                start_date = _next_date(latest).isoformat()
            else:
                start_date = _next_period_start(
                    latest, series["cycle"]  # type: ignore[arg-type]
                ).isoformat()
        else:
            if series["source"] == "FRED":
                start_date = series["start_date"]  # type: ignore[return-value]  # already ISO
            else:
                start_date = _ecos_time_to_date(
                    series["start_date"],  # type: ignore[arg-type]
                    series["cycle"],  # type: ignore[arg-type]
                )
    return start_date, end_date


# =============================================================================
# Due-date logic (shared, source-aware monthly threshold)
# =============================================================================


def _next_date(d: date) -> date:
    """Return the day after ``d``."""
    return d + timedelta(days=1)


def _last_monday(d: date) -> date:
    """Return the Monday of the week containing ``d``."""
    return d - timedelta(days=d.weekday())


def _is_due_weekly(today: date, last_fetch: Optional[date]) -> bool:
    """Return whether a weekly series should be fetched today."""
    if last_fetch is None:
        return True
    last_monday = _last_monday(today)
    return today >= last_monday and last_fetch < last_monday


def _is_due_monthly(
    today: date, last_fetch: Optional[date], source: str
) -> bool:
    """Return whether a monthly series should be fetched today.

    FRED uses day > 15 (mid-month release pattern — CPI ~10-13th,
    unemployment ~first Friday, consumer sentiment ~mid-month).
    ECOS uses day > 5 (early-month release pattern — Korean indicators
    are typically published in the first week of the month).
    """
    threshold = 15 if source == "FRED" else 5
    if today.day > threshold:
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


def _is_due(
    frequency: str, today: date, last_fetch: Optional[date], source: str
) -> bool:
    """Return whether a series with ``frequency`` is due for a fetch."""
    if frequency == "D":
        return True
    if frequency == "W":
        return _is_due_weekly(today, last_fetch)
    if frequency == "M":
        return _is_due_monthly(today, last_fetch, source)
    if frequency == "Q":
        return _is_due_quarterly(today, last_fetch)
    raise ValueError(f"Unknown frequency: {frequency}")


# =============================================================================
# FRED + ECOS — unified fetch API
# =============================================================================


def fetch_series(
    series_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    """Fetch observations for ``series_id`` and store them in the database.

    Dispatches to the FRED or ECOS API based on the series' ``source``
    field in :data:`CORE_SERIES`.
    """
    series = _series_from_registry(series_id)
    if series is None:
        raise ValueError(f"Unknown series: {series_id}")
    source = series["source"]

    _ensure_db_dir(db_path)
    with _connection(db_path) as conn:
        start_date, end_date = _resolve_fetch_window(
            conn, series_id, start_date, end_date
        )
        today = _today_str()

        if source == "FRED":
            from myquant.db.fred import _fetch_fred_series  # lazy — avoids circular import

            _fetch_fred_series(conn, series_id, start_date, end_date, today)
        else:  # ECOS
            from myquant.db.ecos import _fetch_ecos_series  # lazy — avoids circular import

            _fetch_ecos_series(conn, series_id, start_date, end_date, today, series)


def fetch_all(
    source: str = "all",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    """Fetch observations for all core series (FRED + ECOS)."""
    for series_id in _series_ids_for_source(source):
        try:
            fetch_series(series_id, start_date, end_date, db_path)
        except Exception as exc:
            print(f"Error fetching {series_id}: {exc}")


def fetch_due(
    source: str = "all",
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    """Fetch series that are due for update based on their frequency."""
    today = _today()
    with _connection(db_path) as conn:
        for s in CORE_SERIES:
            s_source = s["source"]
            if source != "all" and s_source != source.upper():
                continue
            last_fetch = _get_last_fetch_date(conn, s["id"])  # type: ignore[arg-type]
            if _is_due(
                s["frequency"],  # type: ignore[arg-type]
                today, last_fetch, s_source,  # type: ignore[arg-type]
            ):
                try:
                    fetch_series(s["id"], db_path=db_path)  # type: ignore[arg-type]
                except Exception as exc:
                    print(f"Error fetching {s['id']}: {exc}")


# =============================================================================
# FRED + ECOS — unified query API
# =============================================================================


def get_latest(
    series_id: str, db_path: Path = DEFAULT_DB_PATH
) -> Optional[Dict[str, Any]]:
    """Return the latest observation row for ``series_id``."""
    with _connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM observations WHERE series_id = ? "
            "ORDER BY date DESC LIMIT 1",
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
