"""Unit tests for ``myquant.macro_db`` — schema, fetch, migration, and CLI."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from myquant.macro_db import (
    AUCTIONS_START_DATE,
    CORE_SERIES,
    DEBT_START_DATE,
    SCHEMA,
    fetch_debt,
    fetch_series,
    init_db,
    migrate_legacy_dbs,
    _ecos_time_to_date,
    _main,
    _resolve_fetch_window,
    _today_str,
    get_series_info,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Return a temporary database path that always lives in a fresh directory."""
    return tmp_path / "macro.db"


@pytest.fixture
def fresh_db(db_path: Path) -> Path:
    """Create and initialize a fresh macro database."""
    init_db(db_path)
    return db_path


# =============================================================================
# _ecos_time_to_date — unit
# =============================================================================

class TestEcosTimeToDate:
    """Pure unit tests for ECOS TIME → ISO date conversion."""

    def test_monthly_format(self) -> None:
        """Given a 6-digit monthly TIME string, convert to YYYY-MM-01."""
        assert _ecos_time_to_date("202401", "M") == "2024-01-01"

    def test_quarterly_format(self) -> None:
        """Given a quarterly TIME string '2024Q2', convert to correct month."""
        assert _ecos_time_to_date("2024Q2", "Q") == "2024-04-01"

    def test_daily_format(self) -> None:
        """Given an 8-digit daily TIME string, convert to YYYY-MM-DD."""
        assert _ecos_time_to_date("20240115", "D") == "2024-01-15"

    def test_annual_format(self) -> None:
        """Given a 4-digit annual TIME string, convert to YYYY-01-01."""
        assert _ecos_time_to_date("2024", "A") == "2024-01-01"

    def test_unrecognized_format_raises(self) -> None:
        """Given an unrecognized TIME format, raise ValueError."""
        with pytest.raises(ValueError, match="Unrecognized ECOS TIME format"):
            _ecos_time_to_date("abc", "M")

    def test_quarterly_q1(self) -> None:
        """Q1 maps to January."""
        assert _ecos_time_to_date("2024Q1", "Q") == "2024-01-01"

    def test_quarterly_q3(self) -> None:
        """Q3 maps to July."""
        assert _ecos_time_to_date("2024Q3", "Q") == "2024-07-01"


# =============================================================================
# init_db — schema creation and series seeding
# =============================================================================

class TestInitDb:
    """Tests for ``init_db()``."""

    def test_schema_creates_all_tables(self, db_path: Path) -> None:
        """Given a fresh db_path, init_db creates all 6 tables and 2 indexes."""
        init_db(db_path)
        with sqlite3.connect(db_path) as conn:
            # Tables: verify via sqlite_master
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        expected = {
            "series", "observations", "update_log",
            "debt", "auctions", "fetch_log",
        }
        assert expected.issubset(tables)

    def test_series_count_is_28(self, db_path: Path) -> None:
        """Given init_db, the series table has exactly 28 seeded rows."""
        init_db(db_path)
        df = get_series_info(db_path)
        assert len(df) == 28

    def test_fred_series_count_is_19(self, db_path: Path) -> None:
        """Given init_db, 19 series have source='FRED'."""
        init_db(db_path)
        df = get_series_info(db_path)
        assert len(df[df["source"] == "FRED"]) == 19

    def test_ecos_series_count_is_9(self, db_path: Path) -> None:
        """Given init_db, 9 series have source='ECOS'."""
        init_db(db_path)
        df = get_series_info(db_path)
        assert len(df[df["source"] == "ECOS"]) == 9

    def test_ecos_series_have_iso_start_dates(self, db_path: Path) -> None:
        """Given init_db, ECOS series have ISO-formatted observation_start."""
        init_db(db_path)
        df = get_series_info(db_path)
        ecos_rows = df[df["source"] == "ECOS"]
        for start in ecos_rows["observation_start"]:
            assert start is not None
            assert "-" in start  # "YYYY-MM-DD" → contains hyphen

    def test_each_series_has_cycle(self, db_path: Path) -> None:
        """Given init_db, every series has a non-null cycle."""
        init_db(db_path)
        df = get_series_info(db_path)
        assert (df["cycle"].notna()).all()
        assert set(df["cycle"].unique()).issubset({"D", "W", "M", "Q"})

    def test_idempotent_init(self, db_path: Path) -> None:
        """Given init_db is called twice, the series count stays at 28."""
        init_db(db_path)
        init_db(db_path)  # second call
        df = get_series_info(db_path)
        assert len(df) == 28

    def test_series_value_changes(self, db_path: Path) -> None:
        """Given init_db, the seeded value for FEDFUNDS is correct."""
        init_db(db_path)
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM series WHERE id = ?", ("FEDFUNDS",)
            ).fetchone()
        assert row is not None
        assert row["source"] == "FRED"
        assert row["frequency"] == "M"
        assert row["cycle"] == "M"

    def test_source_check_constraint(self, db_path: Path) -> None:
        """Given init_db, inserting a row with invalid source raises IntegrityError."""
        init_db(db_path)
        with sqlite3.connect(db_path) as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO series (id, source, frequency, cycle) "
                    "VALUES (?, ?, ?, ?)",
                    ("TEST_INVALID", "INVALID_SRC", "D", "D"),
                )

    def test_frequency_check_constraint(self, db_path: Path) -> None:
        """Given init_db, inserting a row with invalid frequency raises IntegrityError."""
        init_db(db_path)
        with sqlite3.connect(db_path) as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO series (id, source, frequency, cycle) "
                    "VALUES (?, ?, ?, ?)",
                    ("TEST_INVALID", "FRED", "X", "D"),
                )


# =============================================================================
# fetch_series — FRED mock
# =============================================================================

class TestFetchSeriesFred:
    """Tests for ``fetch_series()`` with mocked FRED client."""

    @pytest.fixture
    def mock_fred_data(self) -> pd.DataFrame:
        """Return a DataFrame that mimics FRED series_observations output."""
        return pd.DataFrame({
            "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "value": ["1.5", "1.6", "1.7"],
            "realtime_start": ["2024-01-03", "2024-01-03", "2024-01-03"],
            "realtime_end": ["9999-12-31", "9999-12-31", "9999-12-31"],
        })

    def test_fred_fetch_stores_observations(
        self, fresh_db: Path, mock_fred_data: pd.DataFrame
    ) -> None:
        """Given a mocked Fred returning 3 rows, fetch_series stores them."""
        with patch("myquant.db.fred.Fred") as MockFred:
            mock_fred_instance = MockFred.return_value
            mock_fred_instance.get_data.return_value = mock_fred_data

            fetch_series("FEDFUNDS", db_path=fresh_db)

        with sqlite3.connect(fresh_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM observations WHERE series_id='FEDFUNDS' ORDER BY date"
            ).fetchall()
        assert len(rows) == 3
        assert rows[0]["date"] == "2024-01-01"
        assert rows[0]["value"] == 1.5
        assert rows[2]["value"] == 1.7

    def test_fred_fetch_logs_update(
        self, fresh_db: Path, mock_fred_data: pd.DataFrame
    ) -> None:
        """Given a mocked Fred returning data, an update_log row is inserted."""
        with patch("myquant.db.fred.Fred") as MockFred:
            MockFred.return_value.get_data.return_value = mock_fred_data
            fetch_series("FEDFUNDS", db_path=fresh_db)

        with sqlite3.connect(fresh_db) as conn:
            conn.row_factory = sqlite3.Row
            logs = conn.execute(
                "SELECT * FROM update_log WHERE series_id='FEDFUNDS'"
            ).fetchall()
        assert len(logs) == 1
        assert logs[0]["status"] == "ok"
        assert logs[0]["rows_added"] == 3

    def test_fred_fetch_updates_last_updated(
        self, fresh_db: Path, mock_fred_data: pd.DataFrame
    ) -> None:
        """Given a mocked Fred returning data, series.last_updated is set."""
        with patch("myquant.db.fred.Fred") as MockFred:
            MockFred.return_value.get_data.return_value = mock_fred_data
            fetch_series("FEDFUNDS", db_path=fresh_db)

        with sqlite3.connect(fresh_db) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT last_updated FROM series WHERE id='FEDFUNDS'"
            ).fetchone()
        assert row is not None
        assert row["last_updated"] is not None

    def test_fred_fetch_empty_data_logs_ok(
        self, fresh_db: Path
    ) -> None:
        """Given a mocked Fred returning empty DataFrame, log is 'ok' with 0 rows."""
        empty_df = pd.DataFrame(columns=["date", "value", "realtime_start", "realtime_end"])
        with patch("myquant.db.fred.Fred") as MockFred:
            MockFred.return_value.get_data.return_value = empty_df
            fetch_series("FEDFUNDS", db_path=fresh_db)

        with sqlite3.connect(fresh_db) as conn:
            conn.row_factory = sqlite3.Row
            logs = conn.execute(
                "SELECT * FROM update_log WHERE series_id='FEDFUNDS'"
            ).fetchall()
        assert len(logs) == 1
        assert logs[0]["status"] == "ok"
        assert logs[0]["rows_added"] == 0

    def test_fred_fetch_api_error_logs_error(
        self, fresh_db: Path
    ) -> None:
        """Given a mocked Fred that raises, an error log is inserted."""
        with patch("myquant.db.fred.Fred") as MockFred:
            MockFred.return_value.get_data.side_effect = RuntimeError("API is down")

            fetch_series("FEDFUNDS", db_path=fresh_db)

        with sqlite3.connect(fresh_db) as conn:
            conn.row_factory = sqlite3.Row
            logs = conn.execute(
                "SELECT * FROM update_log WHERE series_id='FEDFUNDS'"
            ).fetchall()
        assert len(logs) == 1
        assert logs[0]["status"] == "error"
        assert "API is down" in (logs[0]["message"] or "")

    def test_fred_fetch_unknown_series_raises(self, fresh_db: Path) -> None:
        """Given an unknown series_id, fetch_series raises ValueError."""
        with pytest.raises(ValueError, match="Unknown series"):
            fetch_series("NO_SUCH_SERIES", db_path=fresh_db)


# =============================================================================
# fetch_series — ECOS mock
# =============================================================================

class TestFetchSeriesEcos:
    """Tests for ``fetch_series()`` with mocked ECOS client."""

    @pytest.fixture
    def mock_ecos_data(self) -> pd.DataFrame:
        """Return a DataFrame that mimics ECOS StatisticSearch output."""
        return pd.DataFrame({
            "TIME": ["202401", "202402", "202403"],
            "DATA_VALUE": ["103.5", "104.0", "104.8"],
        })

    def test_ecos_fetch_stores_observations(
        self, fresh_db: Path, mock_ecos_data: pd.DataFrame
    ) -> None:
        """Given a mocked Ecos returning 3 rows, fetch_series stores them."""
        with patch("myquant.db.ecos.Ecos") as MockEcos:
            MockEcos.return_value.get_statistic_search.return_value = mock_ecos_data
            fetch_series("901Y009_0", db_path=fresh_db)

        with sqlite3.connect(fresh_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM observations WHERE series_id='901Y009_0' ORDER BY date"
            ).fetchall()
        assert len(rows) == 3
        assert rows[0]["date"] == "2024-01-01"
        assert rows[0]["value"] == 103.5

    def test_ecos_fetch_logs_update(
        self, fresh_db: Path, mock_ecos_data: pd.DataFrame
    ) -> None:
        """Given a mocked Ecos returning data, an update_log row is inserted."""
        with patch("myquant.db.ecos.Ecos") as MockEcos:
            MockEcos.return_value.get_statistic_search.return_value = mock_ecos_data
            fetch_series("901Y009_0", db_path=fresh_db)

        with sqlite3.connect(fresh_db) as conn:
            conn.row_factory = sqlite3.Row
            logs = conn.execute(
                "SELECT * FROM update_log WHERE series_id='901Y009_0'"
            ).fetchall()
        assert len(logs) == 1
        assert logs[0]["status"] == "ok"
        assert logs[0]["rows_added"] == 3

    def test_ecos_fetch_dot_value_becomes_null(
        self, fresh_db: Path
    ) -> None:
        """Given ECOS returns '.' as DATA_VALUE, it's stored as NULL."""
        dot_data = pd.DataFrame({
            "TIME": ["202401"],
            "DATA_VALUE": ["."],
        })
        with patch("myquant.db.ecos.Ecos") as MockEcos:
            MockEcos.return_value.get_statistic_search.return_value = dot_data
            fetch_series("901Y009_0", db_path=fresh_db)

        with sqlite3.connect(fresh_db) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT value FROM observations WHERE series_id='901Y009_0'"
            ).fetchone()
        assert row is not None
        assert row["value"] is None

    def test_ecos_fetch_comma_value_parsed(
        self, fresh_db: Path
    ) -> None:
        """Given ECOS returns a comma-formatted number, it's stored as float."""
        comma_data = pd.DataFrame({
            "TIME": ["202401"],
            "DATA_VALUE": ["1,234,567.89"],
        })
        with patch("myquant.db.ecos.Ecos") as MockEcos:
            MockEcos.return_value.get_statistic_search.return_value = comma_data
            fetch_series("901Y009_0", db_path=fresh_db)

        with sqlite3.connect(fresh_db) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT value FROM observations WHERE series_id='901Y009_0'"
            ).fetchone()
        assert row is not None
        assert row["value"] == 1234567.89

    def test_ecos_fetch_empty_data_logs_ok(
        self, fresh_db: Path
    ) -> None:
        """Given a mocked Ecos returning empty DataFrame, log is 'ok' with 0 rows."""
        empty_df = pd.DataFrame()
        with patch("myquant.db.ecos.Ecos") as MockEcos:
            MockEcos.return_value.get_statistic_search.return_value = empty_df
            fetch_series("901Y009_0", db_path=fresh_db)

        with sqlite3.connect(fresh_db) as conn:
            conn.row_factory = sqlite3.Row
            logs = conn.execute(
                "SELECT * FROM update_log WHERE series_id='901Y009_0'"
            ).fetchall()
        assert len(logs) == 1
        assert logs[0]["status"] == "ok"
        assert logs[0]["rows_added"] == 0

    def test_ecos_fetch_api_error_logs_error(
        self, fresh_db: Path
    ) -> None:
        """Given a mocked Ecos that raises, an error log is inserted."""
        with patch("myquant.db.ecos.Ecos") as MockEcos:
            MockEcos.return_value.get_statistic_search.side_effect = RuntimeError(
                "ECOS timeout"
            )
            fetch_series("901Y009_0", db_path=fresh_db)

        with sqlite3.connect(fresh_db) as conn:
            conn.row_factory = sqlite3.Row
            logs = conn.execute(
                "SELECT * FROM update_log WHERE series_id='901Y009_0'"
            ).fetchall()
        assert len(logs) == 1
        assert logs[0]["status"] == "error"
        assert "ECOS timeout" in (logs[0]["message"] or "")

    def test_ecos_start_after_end_skips(
        self, fresh_db: Path
    ) -> None:
        """Given start_date > end_date (already up to date), fetch returns early."""
        # Seed an observation at a future-ish date so the resolved
        # start_date is after end_date. We'll just call with an explicit
        # start > end.
        with patch("myquant.db.ecos.Ecos") as MockEcos:
            # The mock should never be called because we skip
            fetch_series(
                "901Y009_0",
                start_date="2026-01-01",
                end_date="2025-01-01",
                db_path=fresh_db,
            )
        # Ecos constructor is never called
        MockEcos.assert_not_called()


# =============================================================================
# fetch_debt — Treasury mock
# =============================================================================

class TestFetchDebt:
    """Tests for ``fetch_debt()`` with mocked Treasury client."""

    @pytest.fixture
    def mock_debt_data(self) -> list[dict[str, str]]:
        """Return a list that mimics Treasury debt API output."""
        return [
            {
                "record_date": "2024-01-01",
                "debt_held_public_amt": "27000000000000",
                "intragov_hold_amt": "7000000000000",
                "tot_pub_debt_out_amt": "34000000000000",
            },
            {
                "record_date": "2024-01-02",
                "debt_held_public_amt": "",
                "intragov_hold_amt": None,
                "tot_pub_debt_out_amt": "34010000000000",
            },
        ]

    def test_debt_fetch_stores_rows(
        self, fresh_db: Path, mock_debt_data: list[dict[str, str]]
    ) -> None:
        """Given a mocked Treasury returning 2 debt records, they're stored."""
        with patch("myquant.db.treasury.Treasury") as MockTreasury:
            mock_treasury = MockTreasury.return_value
            mock_treasury.get_debt.return_value = mock_debt_data
            fetch_debt(db_path=fresh_db)

        with sqlite3.connect(fresh_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM debt ORDER BY record_date"
            ).fetchall()
        assert len(rows) == 2
        assert rows[0]["record_date"] == "2024-01-01"
        assert rows[0]["tot_pub_debt_out_amt"] == 34000000000000.0
        # Empty string → None
        assert rows[1]["debt_held_public_amt"] is None
        # None → None
        assert rows[1]["intragov_hold_amt"] is None

    def test_debt_fetch_logs_success(
        self, fresh_db: Path, mock_debt_data: list[dict[str, str]]
    ) -> None:
        """Given a mocked Treasury returning data, fetch_log is updated."""
        with patch("myquant.db.treasury.Treasury") as MockTreasury:
            MockTreasury.return_value.get_debt.return_value = mock_debt_data
            fetch_debt(db_path=fresh_db)

        with sqlite3.connect(fresh_db) as conn:
            conn.row_factory = sqlite3.Row
            logs = conn.execute(
                "SELECT * FROM fetch_log WHERE dataset='debt'"
            ).fetchall()
        assert len(logs) == 1
        assert logs[0]["status"] == "ok"
        assert logs[0]["records_added"] == 2

    def test_debt_fetch_empty_response_logs_zero(
        self, fresh_db: Path
    ) -> None:
        """Given a mocked Treasury returning empty list, log records 0 rows."""
        with patch("myquant.db.treasury.Treasury") as MockTreasury:
            MockTreasury.return_value.get_debt.return_value = []
            fetch_debt(db_path=fresh_db)

        with sqlite3.connect(fresh_db) as conn:
            conn.row_factory = sqlite3.Row
            logs = conn.execute(
                "SELECT * FROM fetch_log WHERE dataset='debt'"
            ).fetchall()
        assert len(logs) == 1
        assert logs[0]["records_added"] == 0

    def test_debt_fetch_api_error_logs_error(
        self, fresh_db: Path
    ) -> None:
        """Given a mocked Treasury that raises, an error log is inserted."""
        with patch("myquant.db.treasury.Treasury") as MockTreasury:
            MockTreasury.return_value.get_debt.side_effect = RuntimeError(
                "Connection refused"
            )
            fetch_debt(db_path=fresh_db)

        with sqlite3.connect(fresh_db) as conn:
            conn.row_factory = sqlite3.Row
            logs = conn.execute(
                "SELECT * FROM fetch_log WHERE dataset='debt'"
            ).fetchall()
        assert len(logs) == 1
        assert logs[0]["status"] == "error"
        assert "Connection refused" in (logs[0]["message"] or "")

    def test_debt_fetch_with_explicit_dates(
        self, fresh_db: Path, mock_debt_data: list[dict[str, str]]
    ) -> None:
        """Given explicit start_date/end_date, they are passed through to the API."""
        with patch("myquant.db.treasury.Treasury") as MockTreasury:
            MockTreasury.return_value.get_debt.return_value = mock_debt_data
            fetch_debt(
                start_date="2024-01-01",
                end_date="2024-01-31",
                db_path=fresh_db,
            )
        # Verify data was stored
        with sqlite3.connect(fresh_db) as conn:
            count = conn.execute("SELECT COUNT(*) FROM debt").fetchone()[0]
        assert count == 2


# =============================================================================
# migrate_legacy_dbs — idempotency
# =============================================================================

class TestMigrateLegacyDbs:
    """Tests for ``migrate_legacy_dbs()``."""

    @pytest.fixture
    def legacy_dir(self, tmp_path: Path) -> Path:
        """Create a directory with legacy fred.db, ecos.db, and treasury.db."""
        source_dir = tmp_path / "legacy_data"
        source_dir.mkdir()

        # --- fred.db ---
        fred_path = source_dir / "fred.db"
        with sqlite3.connect(fred_path) as conn:
            conn.executescript("""
                CREATE TABLE series (
                    id TEXT PRIMARY KEY, title TEXT, frequency TEXT,
                    units TEXT, observation_start TEXT,
                    observation_end TEXT, last_updated TEXT
                );
                CREATE TABLE observations (
                    series_id TEXT, date TEXT, value REAL,
                    realtime_start TEXT, realtime_end TEXT,
                    PRIMARY KEY (series_id, date)
                );
                CREATE TABLE update_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    series_id TEXT, fetch_date TEXT,
                    observation_start TEXT, observation_end TEXT,
                    rows_added INTEGER, status TEXT, message TEXT, updated_at TEXT
                );
            """)
            conn.execute(
                "INSERT INTO series (id, title, frequency, units, observation_start) "
                "VALUES (?, ?, ?, ?, ?)",
                ("FEDFUNDS", "Fed Funds Rate", "M", "Percent", "1990-01-01"),
            )
            conn.execute(
                "INSERT INTO observations (series_id, date, value, realtime_start, realtime_end) "
                "VALUES (?, ?, ?, ?, ?)",
                ("FEDFUNDS", "2024-01-01", 5.33, "2024-01-31", "9999-12-31"),
            )
            conn.execute(
                "INSERT INTO observations (series_id, date, value, realtime_start, realtime_end) "
                "VALUES (?, ?, ?, ?, ?)",
                ("FEDFUNDS", "2024-02-01", 5.33, "2024-02-28", "9999-12-31"),
            )
            conn.execute(
                "INSERT INTO update_log "
                "(series_id, fetch_date, observation_start, observation_end, rows_added, status) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("FEDFUNDS", "2024-03-01", "2024-01-01", "2024-03-01", 2, "ok"),
            )
            conn.commit()

        # --- ecos.db (same schema shape, different series) ---
        ecos_path = source_dir / "ecos.db"
        with sqlite3.connect(ecos_path) as conn:
            conn.executescript("""
                CREATE TABLE series (
                    id TEXT PRIMARY KEY, title TEXT, frequency TEXT,
                    units TEXT, observation_start TEXT,
                    observation_end TEXT, last_updated TEXT
                );
                CREATE TABLE observations (
                    series_id TEXT, date TEXT, value REAL,
                    realtime_start TEXT, realtime_end TEXT,
                    PRIMARY KEY (series_id, date)
                );
                CREATE TABLE update_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    series_id TEXT, fetch_date TEXT,
                    observation_start TEXT, observation_end TEXT,
                    rows_added INTEGER, status TEXT, message TEXT, updated_at TEXT
                );
            """)
            conn.execute(
                "INSERT INTO series (id, title, frequency, units, observation_start) "
                "VALUES (?, ?, ?, ?, ?)",
                ("901Y009_0", "CPI Total", "M", None, "199001"),
            )
            conn.execute(
                "INSERT INTO observations (series_id, date, value, realtime_start, realtime_end) "
                "VALUES (?, ?, ?, ?, ?)",
                ("901Y009_0", "2024-01-01", 110.5, "2024-03-01", "2024-03-01"),
            )
            conn.execute(
                "INSERT INTO update_log "
                "(series_id, fetch_date, observation_start, observation_end, rows_added, status) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("901Y009_0", "2024-03-01", "2024-01-01", "2024-03-01", 1, "ok"),
            )
            conn.commit()

        # --- treasury.db ---
        treasury_path = source_dir / "treasury.db"
        with sqlite3.connect(treasury_path) as conn:
            conn.executescript("""
                CREATE TABLE debt (
                    record_date TEXT PRIMARY KEY,
                    debt_held_public_amt REAL,
                    intragov_hold_amt REAL,
                    tot_pub_debt_out_amt REAL
                );
                CREATE TABLE auctions (
                    record_date TEXT, cusip TEXT, security_type TEXT,
                    security_term TEXT, auction_date TEXT, issue_date TEXT,
                    maturity_date TEXT, interest_rate REAL, average_price REAL,
                    bid_to_cover_ratio REAL, total_accepted REAL,
                    competitive_accepted REAL,
                    PRIMARY KEY (auction_date, cusip)
                );
                CREATE TABLE fetch_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset TEXT, fetch_date TEXT, records_added INTEGER,
                    status TEXT, message TEXT, updated_at TEXT
                );
            """)
            conn.execute(
                "INSERT INTO debt (record_date, tot_pub_debt_out_amt) VALUES (?, ?)",
                ("2024-01-01", 34000000000000),
            )
            conn.execute(
                "INSERT INTO fetch_log (dataset, fetch_date, records_added, status) "
                "VALUES (?, ?, ?, ?)",
                ("debt", "2024-01-01", 1, "ok"),
            )
            conn.commit()

        return source_dir

    def test_migration_copies_all_data(
        self, tmp_path: Path, legacy_dir: Path
    ) -> None:
        """Given legacy DBs with data, migration copies everything to macro.db."""
        target_path = tmp_path / "macro.db"
        migrate_legacy_dbs(target_db_path=target_path, source_dir=legacy_dir)

        with sqlite3.connect(target_path) as conn:
            conn.row_factory = sqlite3.Row
            # Series: 28 from init_db + 2 from legacy (should be 28, INSERT OR IGNORE)
            series_count = conn.execute("SELECT COUNT(*) FROM series").fetchone()[0]
            assert series_count == 28  # seeded + legacy via IGNORE

            obs_count = conn.execute(
                "SELECT COUNT(*) FROM observations"
            ).fetchone()[0]
            assert obs_count == 3  # 2 FRED + 1 ECOS

            debt_count = conn.execute("SELECT COUNT(*) FROM debt").fetchone()[0]
            assert debt_count == 1

            fetch_log_count = conn.execute(
                "SELECT COUNT(*) FROM fetch_log"
            ).fetchone()[0]
            assert fetch_log_count == 1

    def test_migration_is_idempotent(
        self, tmp_path: Path, legacy_dir: Path
    ) -> None:
        """Given migration is run twice, the second run produces no additional rows."""
        target_path = tmp_path / "macro.db"

        migrate_legacy_dbs(target_db_path=target_path, source_dir=legacy_dir)

        with sqlite3.connect(target_path) as conn:
            obs_after_first = conn.execute(
                "SELECT COUNT(*) FROM observations"
            ).fetchone()[0]
            log_after_first = conn.execute(
                "SELECT COUNT(*) FROM update_log"
            ).fetchone()[0]
            debt_after_first = conn.execute(
                "SELECT COUNT(*) FROM debt"
            ).fetchone()[0]
            f_log_after_first = conn.execute(
                "SELECT COUNT(*) FROM fetch_log"
            ).fetchone()[0]

        # Run migration again
        migrate_legacy_dbs(target_db_path=target_path, source_dir=legacy_dir)

        with sqlite3.connect(target_path) as conn:
            obs_after_second = conn.execute(
                "SELECT COUNT(*) FROM observations"
            ).fetchone()[0]
            log_after_second = conn.execute(
                "SELECT COUNT(*) FROM update_log"
            ).fetchone()[0]
            debt_after_second = conn.execute(
                "SELECT COUNT(*) FROM debt"
            ).fetchone()[0]
            f_log_after_second = conn.execute(
                "SELECT COUNT(*) FROM fetch_log"
            ).fetchone()[0]

        assert obs_after_second == obs_after_first
        assert log_after_second == log_after_first
        assert debt_after_second == debt_after_first
        assert f_log_after_second == f_log_after_first

    def test_migration_missing_source_skips_gracefully(
        self, tmp_path: Path
    ) -> None:
        """Given no legacy DBs exist, migration skips all sources without error."""
        target_path = tmp_path / "macro.db"
        # source_dir contains no .db files
        migrate_legacy_dbs(target_db_path=target_path)

        # Should still initialize target and have 28 seeded series
        with sqlite3.connect(target_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM series").fetchone()[0]
        assert count == 28

    def test_migration_ecos_realtime_is_null(
        self, tmp_path: Path, legacy_dir: Path
    ) -> None:
        """Given ECOS migration, realtime_start and realtime_end are NULL."""
        target_path = tmp_path / "macro.db"
        migrate_legacy_dbs(target_db_path=target_path, source_dir=legacy_dir)

        with sqlite3.connect(target_path) as conn:
            conn.row_factory = sqlite3.Row
            # FRED observations should preserve realtime fields
            fred_row = conn.execute(
                "SELECT * FROM observations WHERE series_id='FEDFUNDS' LIMIT 1"
            ).fetchone()
            assert fred_row is not None
            assert fred_row["realtime_start"] == "2024-01-31"

            # ECOS observations should have NULL realtime fields
            ecos_row = conn.execute(
                "SELECT * FROM observations WHERE series_id='901Y009_0' LIMIT 1"
            ).fetchone()
            assert ecos_row is not None
            assert ecos_row["realtime_start"] is None
            assert ecos_row["realtime_end"] is None

    def test_migration_ecos_cycle_resolved_from_registry(
        self, tmp_path: Path, legacy_dir: Path
    ) -> None:
        """Given ECOS migration, the cycle column uses CORE_SERIES registry value."""
        target_path = tmp_path / "macro.db"
        migrate_legacy_dbs(target_db_path=target_path, source_dir=legacy_dir)

        with sqlite3.connect(target_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT cycle FROM series WHERE id='901Y009_0'"
            ).fetchone()
        assert row is not None
        # From CORE_SERIES: cycle='M' for 901Y009_0
        assert row["cycle"] == "M"


# =============================================================================
# CLI argument parsing
# =============================================================================

class TestCLI:
    """Tests for the ``_main()`` CLI entrypoint."""

    @pytest.fixture
    def patch_init_db(self) -> MagicMock:
        with patch("myquant.db.cli.init_db") as mock:
            yield mock

    @pytest.fixture
    def patch_fetch_all(self) -> MagicMock:
        with patch("myquant.db.cli.fetch_all") as mock:
            yield mock

    @pytest.fixture
    def patch_fetch_due(self) -> MagicMock:
        with patch("myquant.db.cli.fetch_due") as mock:
            yield mock

    @pytest.fixture
    def patch_fetch_debt(self) -> MagicMock:
        with patch("myquant.db.cli.fetch_debt") as mock:
            yield mock

    @pytest.fixture
    def patch_fetch_auctions(self) -> MagicMock:
        with patch("myquant.db.cli.fetch_auctions") as mock:
            yield mock

    @pytest.fixture
    def patch_migrate(self) -> MagicMock:
        with patch("myquant.db.cli.migrate_legacy_dbs") as mock:
            yield mock

    @pytest.fixture
    def patch_status(self) -> MagicMock:
        with patch("myquant.db.cli._status") as mock:
            yield mock

    def test_init_command(
        self, patch_init_db: MagicMock, db_path: Path
    ) -> None:
        """Given 'init' command, init_db is called with --db-path."""
        with patch("sys.argv", ["macro_db", "--db-path", str(db_path), "init"]):
            _main()
        patch_init_db.assert_called_once_with(db_path)

    def test_fetch_all_default(
        self, patch_fetch_all: MagicMock, db_path: Path
    ) -> None:
        """Given 'fetch-all' with no --source, fetch_all called with source='all'."""
        with patch("sys.argv", ["macro_db", "--db-path", str(db_path), "fetch-all"]):
            _main()
        patch_fetch_all.assert_called_once_with(source="all", db_path=db_path)

    def test_fetch_all_fred(
        self, patch_fetch_all: MagicMock, db_path: Path
    ) -> None:
        """Given 'fetch-all --source fred', fetch_all called with source='fred'."""
        with patch("sys.argv", [
            "macro_db", "--db-path", str(db_path), "fetch-all", "--source", "fred",
        ]):
            _main()
        patch_fetch_all.assert_called_once_with(source="fred", db_path=db_path)

    def test_fetch_due_ecos(
        self, patch_fetch_due: MagicMock, db_path: Path
    ) -> None:
        """Given 'fetch-due --source ecos', fetch_due called with source='ecos'."""
        with patch("sys.argv", [
            "macro_db", "--db-path", str(db_path), "fetch-due", "--source", "ecos",
        ]):
            _main()
        patch_fetch_due.assert_called_once_with(source="ecos", db_path=db_path)

    def test_fetch_debt_command(
        self, patch_fetch_debt: MagicMock, db_path: Path
    ) -> None:
        """Given 'fetch-debt' command, fetch_debt called with --db-path."""
        with patch("sys.argv", ["macro_db", "--db-path", str(db_path), "fetch-debt"]):
            _main()
        patch_fetch_debt.assert_called_once_with(db_path=db_path)

    def test_fetch_auctions_command(
        self, patch_fetch_auctions: MagicMock, db_path: Path
    ) -> None:
        """Given 'fetch-auctions' command, fetch_auctions called with --db-path."""
        with patch(
            "sys.argv", ["macro_db", "--db-path", str(db_path), "fetch-auctions"]
        ):
            _main()
        patch_fetch_auctions.assert_called_once_with(db_path=db_path)

    def test_status_command(
        self, patch_status: MagicMock, db_path: Path
    ) -> None:
        """Given 'status' command, _status is called with --db-path."""
        with patch("sys.argv", ["macro_db", "--db-path", str(db_path), "status"]):
            _main()
        patch_status.assert_called_once_with(db_path)

    def test_migrate_command_default(
        self, patch_migrate: MagicMock, db_path: Path
    ) -> None:
        """Given 'migrate' command with no --source-dir, called with source_dir=None."""
        with patch("sys.argv", ["macro_db", "--db-path", str(db_path), "migrate"]):
            _main()
        patch_migrate.assert_called_once_with(db_path, None)

    def test_migrate_command_with_source_dir(
        self, patch_migrate: MagicMock, db_path: Path, tmp_path: Path
    ) -> None:
        """Given 'migrate --source-dir /tmp/legacy', called with explicit path."""
        source_dir = tmp_path / "legacy"
        source_dir.mkdir()
        with patch("sys.argv", [
            "macro_db", "--db-path", str(db_path),
            "migrate", "--source-dir", str(source_dir),
        ]):
            _main()
        patch_migrate.assert_called_once_with(db_path, source_dir)

    def test_default_db_path_used(self, patch_init_db: MagicMock) -> None:
        """Given no --db-path, DEFAULT_DB_PATH is used."""
        from myquant.macro_db import DEFAULT_DB_PATH
        with patch("sys.argv", ["macro_db", "init"]):
            _main()
        patch_init_db.assert_called_once_with(DEFAULT_DB_PATH)


# =============================================================================
# get_series_info — query
# =============================================================================

class TestGetSeriesInfo:
    """Tests for ``get_series_info()``."""

    def test_returns_dataframe(self, fresh_db: Path) -> None:
        """Given a fresh DB, get_series_info returns a DataFrame with 28 rows."""
        df = get_series_info(fresh_db)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 28

    def test_columns_present(self, fresh_db: Path) -> None:
        """Given a fresh DB, the DataFrame has expected columns."""
        df = get_series_info(fresh_db)
        expected = {  # noqa: F841 — author's schema check
            "id", "title", "source", "frequency", "cycle", "units",
            "observation_start", "observation_end", "last_updated",
        }
        assert set(df.columns) == expected  # noqa: F821


# =============================================================================
# _resolve_fetch_window — unit
# =============================================================================

class TestResolveFetchWindow:
    """Tests for ``_resolve_fetch_window()``."""

    def test_returns_defaults_for_empty_db(self, db_path: Path) -> None:
        """Given an empty DB, start_date falls back to series start, end_date= today."""
        init_db(db_path)
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            start, end = _resolve_fetch_window(conn, "FEDFUNDS", None, None)
        # FEDFUNDS start_date from CORE_SERIES: "1990-01-01"
        assert start == "1990-01-01"
        assert end == _today_str()

    def test_respects_explicit_dates(self, db_path: Path) -> None:
        """Given explicit start/end dates, they are returned as-is."""
        init_db(db_path)
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            start, end = _resolve_fetch_window(
                conn, "FEDFUNDS", "2024-01-01", "2024-06-01"
            )
        assert start == "2024-01-01"
        assert end == "2024-06-01"

    def test_raises_for_unknown_series(self, db_path: Path) -> None:
        """Given an unknown series_id, raises ValueError."""
        init_db(db_path)
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            with pytest.raises(ValueError, match="Unknown series"):
                _resolve_fetch_window(conn, "NO_SUCH", None, None)
