"""Market price storage and fetch logic for the unified macro database.

Stores daily OHLCV/Adjusted Close data for Korean (pykrx) and US (yfinance)
indices and ETFs in ``macro.db`` alongside the macro series tables.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from myquant.db.core import DEFAULT_DB_PATH, _connection, _ensure_db_dir, _today_str

# =============================================================================
# Market schema
# =============================================================================

MARKET_SCHEMA: str = """
-- TABLE: market_prices — daily OHLCV for indices and ETFs
CREATE TABLE IF NOT EXISTS market_prices (
    symbol      TEXT NOT NULL,
    date        TEXT NOT NULL,
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    volume      INTEGER,
    adj_close   REAL,
    source      TEXT NOT NULL CHECK(source IN ('pykrx', 'yfinance')),
    asset_type  TEXT NOT NULL CHECK(asset_type IN ('index', 'etf')),
    name        TEXT,
    PRIMARY KEY (symbol, date)
);

CREATE INDEX IF NOT EXISTS idx_market_prices_symbol_date
    ON market_prices(symbol, date);

-- TABLE: market_watchlist — symbols to monitor
CREATE TABLE IF NOT EXISTS market_watchlist (
    symbol      TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    source      TEXT NOT NULL CHECK(source IN ('pykrx', 'yfinance')),
    asset_type  TEXT NOT NULL CHECK(asset_type IN ('index', 'etf')),
    category    TEXT,
    is_active   INTEGER DEFAULT 1,
    added_date  TEXT,
    notes       TEXT
);

-- TABLE: market_update_log — per-symbol fetch history
CREATE TABLE IF NOT EXISTS market_update_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT NOT NULL,
    fetch_date      TEXT NOT NULL,
    records_added   INTEGER,
    status          TEXT DEFAULT 'ok',
    message         TEXT,
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_market_update_log_symbol_fetch
    ON market_update_log(symbol, fetch_date);
"""

# =============================================================================
# Default watchlist
# =============================================================================

MARKET_WATCHLIST: List[Dict[str, Optional[str]]] = [
    # -------------------------------------------------------------------------
    # Korea — pykrx (indices)
    # -------------------------------------------------------------------------
    {
        "symbol": "KOSPI",
        "name": "코스피 지수",
        "source": "pykrx",
        "asset_type": "index",
        "category": "market_cap",
    },
    {
        "symbol": "KOSDAQ",
        "name": "코스닥 지수",
        "source": "pykrx",
        "asset_type": "index",
        "category": "market_cap",
    },
    {
        "symbol": "KOSPI200",
        "name": "코스피200 지수",
        "source": "pykrx",
        "asset_type": "index",
        "category": "market_cap",
    },
    # -------------------------------------------------------------------------
    # Korea — pykrx (ETFs)
    # -------------------------------------------------------------------------
    {
        "symbol": "069500",
        "name": "KODEX 200 ETF",
        "source": "pykrx",
        "asset_type": "etf",
        "category": "market_cap",
    },
    {
        "symbol": "364980",
        "name": "TIGER 250 ETF",
        "source": "pykrx",
        "asset_type": "etf",
        "category": "market_cap",
    },
    # -------------------------------------------------------------------------
    # US — yfinance (indices)
    # -------------------------------------------------------------------------
    {
        "symbol": "^GSPC",
        "name": "S&P 500",
        "source": "yfinance",
        "asset_type": "index",
        "category": "market_cap",
    },
    {
        "symbol": "^IXIC",
        "name": "NASDAQ",
        "source": "yfinance",
        "asset_type": "index",
        "category": "market_cap",
    },
    {
        "symbol": "^DJI",
        "name": "Dow Jones",
        "source": "yfinance",
        "asset_type": "index",
        "category": "market_cap",
    },
    {
        "symbol": "^VIX",
        "name": "VIX",
        "source": "yfinance",
        "asset_type": "index",
        "category": None,
    },
    # -------------------------------------------------------------------------
    # US — yfinance (ETFs)
    # -------------------------------------------------------------------------
    {
        "symbol": "SPY",
        "name": "SPDR S&P 500 ETF",
        "source": "yfinance",
        "asset_type": "etf",
        "category": "market_cap",
    },
    {
        "symbol": "QQQ",
        "name": "Invesco QQQ Trust",
        "source": "yfinance",
        "asset_type": "etf",
        "category": "market_cap",
    },
    {
        "symbol": "VOO",
        "name": "Vanguard S&P 500 ETF",
        "source": "yfinance",
        "asset_type": "etf",
        "category": "market_cap",
    },
    {
        "symbol": "VT",
        "name": "Vanguard Total World Stock ETF",
        "source": "yfinance",
        "asset_type": "etf",
        "category": "market_cap",
    },
    {
        "symbol": "TLT",
        "name": "iShares 20+ Year Treasury Bond ETF",
        "source": "yfinance",
        "asset_type": "etf",
        "category": None,
    },
    {
        "symbol": "RSP",
        "name": "Invesco S&P 500 Equal Weight ETF",
        "source": "yfinance",
        "asset_type": "etf",
        "category": "equal_weight",
    },
]

# Watchlist symbols exposed as a set for quick lookups.
_MARKET_SYMBOLS: set[str] = {w["symbol"] for w in MARKET_WATCHLIST}  # type: ignore[misc]


# =============================================================================
# Initialization
# =============================================================================


def init_market_tables(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Create market tables in ``macro.db``.

    Creates ``market_prices``, ``market_watchlist``, and ``market_update_log``.
    Safe to call multiple times (``IF NOT EXISTS``).
    """
    _ensure_db_dir(db_path)
    with _connection(db_path) as conn:
        conn.executescript(MARKET_SCHEMA)
        conn.commit()


def seed_watchlist(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Seed the default market watchlist.

    Inserts the 15 default symbols (5 Korean + 10 US) with
    ``ON CONFLICT(symbol) DO UPDATE`` so it is idempotent.
    """
    _ensure_db_dir(db_path)
    with _connection(db_path) as conn:
        conn.executescript(MARKET_SCHEMA)
        for w in MARKET_WATCHLIST:
            conn.execute(
                "INSERT INTO market_watchlist "
                "(symbol, name, source, asset_type, category, is_active, added_date) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(symbol) DO UPDATE SET "
                "name=excluded.name, "
                "source=excluded.source, "
                "asset_type=excluded.asset_type, "
                "category=excluded.category, "
                "is_active=excluded.is_active",
                (
                    w["symbol"],
                    w["name"],
                    w["source"],
                    w["asset_type"],
                    w["category"],
                    1,
                    _today_str(),
                ),
            )
        conn.commit()


# =============================================================================
# Watchlist helpers
# =============================================================================


def _get_watchlist_row(
    conn: sqlite3.Connection, symbol: str
) -> Optional[sqlite3.Row]:
    """Return a watchlist row for ``symbol`` or ``None``."""
    return conn.execute(
        "SELECT * FROM market_watchlist WHERE symbol = ?", (symbol,)
    ).fetchone()


def add_to_watchlist(
    symbol: str,
    name: str,
    source: str,
    asset_type: str,
    category: Optional[str] = None,
    is_active: int = 1,
    notes: Optional[str] = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    """Add a new symbol to the market watchlist.

    Parameters
    ----------
    symbol
        Ticker/symbol to monitor (e.g. ``"KOSPI"`` or ``"SPY"``).
    name
        Human-readable name.
    source
        Either ``"pykrx"`` or ``"yfinance"``.
    asset_type
        Either ``"index"`` or ``"etf"``.
    category
        Optional category such as ``"equal_weight"`` or ``"market_cap"``.
    is_active
        Whether the symbol is actively monitored (default 1).
    notes
        Optional free-form notes.
    db_path
        Path to the SQLite database.
    """
    source = source.lower()
    asset_type = asset_type.lower()
    if source not in {"pykrx", "yfinance"}:
        raise ValueError(f"source must be 'pykrx' or 'yfinance', got {source!r}")
    if asset_type not in {"index", "etf"}:
        raise ValueError(f"asset_type must be 'index' or 'etf', got {asset_type!r}")

    _ensure_db_dir(db_path)
    with _connection(db_path) as conn:
        conn.executescript(MARKET_SCHEMA)
        conn.execute(
            "INSERT INTO market_watchlist "
            "(symbol, name, source, asset_type, category, is_active, added_date, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(symbol) DO UPDATE SET "
            "name=excluded.name, "
            "source=excluded.source, "
            "asset_type=excluded.asset_type, "
            "category=excluded.category, "
            "is_active=excluded.is_active, "
            "notes=excluded.notes",
            (
                symbol.upper(),
                name,
                source,
                asset_type,
                category,
                is_active,
                _today_str(),
                notes,
            ),
        )
        conn.commit()


def get_watchlist(
    active_only: bool = True, db_path: Path = DEFAULT_DB_PATH
) -> pd.DataFrame:
    """Return the watchlist as a DataFrame.

    Parameters
    ----------
    active_only
        If True, filter to rows with ``is_active = 1``.
    db_path
        Path to the SQLite database.
    """
    query = "SELECT * FROM market_watchlist"
    params: List[Any] = []
    if active_only:
        query += " WHERE is_active = 1"
    query += " ORDER BY source, symbol"
    with _connection(db_path) as conn:
        return pd.read_sql_query(query, conn, params=params)


# =============================================================================
# Fetch helpers
# =============================================================================


def _max_market_date(
    conn: sqlite3.Connection, symbol: str
) -> Optional[date]:
    """Return the latest stored price date for ``symbol`` or ``None``."""
    row = conn.execute(
        "SELECT MAX(date) AS max_date FROM market_prices WHERE symbol = ?",
        (symbol,),
    ).fetchone()
    if row is None or row["max_date"] is None:
        return None
    return date.fromisoformat(row["max_date"])


def _next_date(d: date) -> date:
    """Return the day after ``d``."""
    return d + timedelta(days=1)


def _resolve_market_window(
    conn: sqlite3.Connection,
    symbol: str,
    start_date: Optional[str],
    end_date: Optional[str],
    default_start: str = "2020-01-01",
) -> Tuple[str, str]:
    """Resolve the fetch window for a market symbol (ISO date strings)."""
    if end_date is None:
        end_date = _today_str()
    if start_date is None:
        latest = _max_market_date(conn, symbol)
        start_date = _next_date(latest).isoformat() if latest else default_start
    return start_date, end_date


def _log_market_fetch(
    conn: sqlite3.Connection,
    symbol: str,
    fetch_date: str,
    records_added: int,
    status: str,
    message: Optional[str] = None,
) -> None:
    """Insert a row into ``market_update_log``."""
    conn.execute(
        "INSERT INTO market_update_log "
        "(symbol, fetch_date, records_added, status, message) "
        "VALUES (?, ?, ?, ?, ?)",
        (symbol, fetch_date, records_added, status, message),
    )
    conn.commit()


# =============================================================================
# Fetch/store API
# =============================================================================


def fetch_market_data(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> int:
    """Fetch daily prices for ``symbol`` and store them in ``market_prices``.

    Parameters
    ----------
    symbol
        Watchlist symbol (e.g. ``"KOSPI"`` or ``"SPY"``).
    start_date
        ISO start date. If omitted, resumes from the day after the latest
        stored price, or from ``2020-01-01`` if the table is empty.
    end_date
        ISO end date. If omitted, defaults to today.
    db_path
        Path to the SQLite database.

    Returns
    -------
    int
        Number of price rows inserted or updated.
    """
    _ensure_db_dir(db_path)
    with _connection(db_path) as conn:
        row = _get_watchlist_row(conn, symbol)
        if row is None:
            raise ValueError(f"Unknown market symbol: {symbol}")
        source = row["source"]
        asset_type = row["asset_type"]
        name = row["name"]

        start_date, end_date = _resolve_market_window(
            conn, symbol, start_date, end_date
        )
        today = _today_str()

        try:
            if source == "pykrx":
                from myquant.market import fetch_pykrx

                df = fetch_pykrx(symbol, start_date, end_date)
            else:  # yfinance
                from myquant.market import fetch_yfinance

                df = fetch_yfinance(symbol, start_date, end_date)
        except Exception as exc:
            _log_market_fetch(conn, symbol, today, 0, "error", str(exc))
            return 0

        if df is None or df.empty:
            _log_market_fetch(
                conn, symbol, today, 0, "ok", "No price data returned"
            )
            return 0

        rows = [
            (
                symbol,
                r.date,
                r.open,
                r.high,
                r.low,
                r.close,
                None if pd.isna(r.volume) else int(r.volume),
                r.adj_close,
                source,
                asset_type,
                name,
            )
            for r in df.itertuples(index=False)
        ]
        conn.executemany(
            "INSERT OR REPLACE INTO market_prices "
            "(symbol, date, open, high, low, close, volume, adj_close, source, asset_type, name) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        _log_market_fetch(conn, symbol, today, len(rows), "ok")
        return len(rows)


def fetch_all_market_data(db_path: Path = DEFAULT_DB_PATH) -> Dict[str, int]:
    """Fetch daily prices for all active watchlist symbols.

    Returns a mapping ``symbol -> records_added``.
    """
    _ensure_db_dir(db_path)
    results: Dict[str, int] = {}
    with _connection(db_path) as conn:
        rows = conn.execute(
            "SELECT symbol FROM market_watchlist WHERE is_active = 1 ORDER BY symbol"
        ).fetchall()
    for row in rows:
        symbol = row["symbol"]
        try:
            results[symbol] = fetch_market_data(symbol, db_path=db_path)
        except Exception as exc:
            print(f"Error fetching {symbol}: {exc}")
            results[symbol] = 0
    return results


# =============================================================================
# Query API
# =============================================================================


def get_market_history(
    symbol: str,
    days: int = 30,
    db_path: Path = DEFAULT_DB_PATH,
) -> pd.DataFrame:
    """Return price history for ``symbol`` as a DataFrame.

    Parameters
    ----------
    symbol
        Watchlist symbol.
    days
        Number of calendar days to look back (default 30).
    db_path
        Path to the SQLite database.
    """
    start = (date.today() - timedelta(days=days)).isoformat()
    query = (
        "SELECT * FROM market_prices "
        "WHERE symbol = ? AND date >= ? "
        "ORDER BY date"
    )
    with _connection(db_path) as conn:
        return pd.read_sql_query(query, conn, params=(symbol, start))


def get_latest_price(
    symbol: str, db_path: Path = DEFAULT_DB_PATH
) -> Optional[Dict[str, Any]]:
    """Return the latest price row for ``symbol`` or ``None``."""
    with _connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM market_prices "
            "WHERE symbol = ? "
            "ORDER BY date DESC LIMIT 1",
            (symbol,),
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def get_market_status(db_path: Path = DEFAULT_DB_PATH) -> pd.DataFrame:
    """Return a status summary for each watchlist symbol."""
    with _connection(db_path) as conn:
        return pd.read_sql_query(
            """
            SELECT
                w.symbol,
                w.name,
                w.source,
                w.asset_type,
                w.category,
                COUNT(DISTINCT p.date) AS price_records,
                MAX(p.date) AS latest_price_date,
                MAX(l.fetch_date) AS last_fetch_date,
                MAX(l.records_added) AS last_records_added
            FROM market_watchlist w
            LEFT JOIN market_prices p ON w.symbol = p.symbol
            LEFT JOIN market_update_log l ON w.symbol = l.symbol AND l.status = 'ok'
            GROUP BY w.symbol
            ORDER BY w.source, w.symbol
            """,
            conn,
        )
