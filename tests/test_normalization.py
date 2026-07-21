"""Unit tests for the normalization module."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from myquant.db import init_db, init_market_tables
from myquant.db.normalization import (
    NORMALIZATION_SCHEMA,
    _resample_to_daily,
    get_normalized_history,
    get_normalized_status,
    normalize_all,
    normalize_market_data,
    normalize_series,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Return a temporary database path."""
    return tmp_path / "macro.db"


@pytest.fixture
def fresh_db(db_path: Path) -> Path:
    """Create a fresh initialized database."""
    init_db(db_path)
    return db_path


@pytest.fixture
def market_db(fresh_db: Path) -> Path:
    """Create a database with market tables initialized."""
    init_market_tables(fresh_db)
    return fresh_db


# =============================================================================
# Helpers
# =============================================================================


def _insert_series(
    db_path: Path,
    series_id: str,
    source: str,
    frequency: str,
) -> None:
    """Insert a series row directly into the database."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO series "
            "(id, title, source, frequency, cycle, units, observation_start) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (series_id, f"Test {series_id}", source, frequency, frequency, "unit", "2024-01-01"),
        )
        conn.commit()


def _insert_observations(
    db_path: Path,
    series_id: str,
    dates: list[str],
    values: list[float],
) -> None:
    """Insert observation rows directly into the database."""
    with sqlite3.connect(db_path) as conn:
        for date, value in zip(dates, values):
            conn.execute(
                "INSERT OR REPLACE INTO observations (series_id, date, value) "
                "VALUES (?, ?, ?)",
                (series_id, date, value),
            )
        conn.commit()


def _insert_market_prices(
    db_path: Path,
    symbol: str,
    source: str,
    asset_type: str,
    dates: list[str],
    closes: list[float],
) -> None:
    """Insert market price rows directly into the database."""
    with sqlite3.connect(db_path) as conn:
        for date, close in zip(dates, closes):
            conn.execute(
                "INSERT OR REPLACE INTO market_prices "
                "(symbol, date, open, high, low, close, volume, adj_close, source, asset_type, name) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (symbol, date, close, close, close, close, 1000, close, source, asset_type, symbol),
            )
        conn.commit()


# =============================================================================
# _resample_to_daily
# =============================================================================


class TestResampleToDaily:
    """Pure unit tests for the resampling helper."""

    def test_daily_is_copied(self) -> None:
        """Daily data should be returned unchanged."""
        df = pd.DataFrame({"date": ["2024-01-01", "2024-01-02"], "value": [1.0, 2.0]})
        result = _resample_to_daily(df, "D")
        assert list(result["date"]) == ["2024-01-01", "2024-01-02"]
        assert list(result["value"]) == [1.0, 2.0]

    def test_monthly_forward_fills(self) -> None:
        """Monthly data should be assigned to the first of the month and forward-filled."""
        df = pd.DataFrame({"date": ["2024-01-01", "2024-02-01"], "value": [1.0, 2.0]})
        result = _resample_to_daily(df, "M")
        assert (result["date"] == "2024-01-01").any()
        assert (result["date"] == "2024-01-31").any()
        assert (result["date"] == "2024-02-01").any()
        # Value on 2024-01-15 should be the January value.
        jan_15 = result[result["date"] == "2024-01-15"]["value"].iloc[0]
        assert jan_15 == 1.0

    def test_quarterly_forward_fills(self) -> None:
        """Quarterly data should be assigned to the first of the quarter and forward-filled."""
        df = pd.DataFrame({"date": ["2024-01-01", "2024-04-01"], "value": [1.0, 2.0]})
        result = _resample_to_daily(df, "Q")
        assert (result["date"] == "2024-01-01").any()
        assert (result["date"] == "2024-03-31").any()
        assert (result["date"] == "2024-04-01").any()
        # Value on 2024-03-15 should be the Q1 value.
        mar_15 = result[result["date"] == "2024-03-15"]["value"].iloc[0]
        assert mar_15 == 1.0

    def test_unknown_frequency_raises(self) -> None:
        """An unsupported frequency should raise ValueError."""
        df = pd.DataFrame({"date": ["2024-01-01"], "value": [1.0]})
        with pytest.raises(ValueError, match="Unknown frequency"):
            _resample_to_daily(df, "W")


# =============================================================================
# init_normalization_tables
# =============================================================================


class TestInitNormalizationTables:
    """Tests for normalization table initialization."""

    def test_table_created(self, fresh_db: Path) -> None:
        """The normalized_daily table and indexes should be created."""
        from myquant.db.normalization import init_normalization_tables

        init_normalization_tables(fresh_db)
        with sqlite3.connect(fresh_db) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            indexes = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index'"
                ).fetchall()
            }
        assert "normalized_daily" in tables
        assert "idx_normalized_daily_series_date" in indexes
        assert "idx_normalized_daily_date" in indexes


# =============================================================================
# normalize_series
# =============================================================================


class TestNormalizeSeries:
    """Tests for single-series normalization."""

    def test_daily_series(self, fresh_db: Path) -> None:
        """Daily observations should be copied one-to-one."""
        _insert_series(fresh_db, "DGS10", "FRED", "D")
        _insert_observations(fresh_db, "DGS10", ["2024-01-01", "2024-01-02"], [4.0, 4.1])

        rows = normalize_series("DGS10", db_path=fresh_db)
        assert rows == 2

        df = get_normalized_history("DGS10", days=1000, db_path=fresh_db)
        assert len(df) == 2
        assert set(df["source"]) == {"FRED"}
        assert set(df["asset_type"]) == {"macro"}

    def test_monthly_series_forward_fills(self, fresh_db: Path) -> None:
        """Monthly observations should be forward-filled daily."""
        _insert_series(fresh_db, "CPI", "FRED", "M")
        _insert_observations(fresh_db, "CPI", ["2024-01-01", "2024-02-01"], [300.0, 301.0])

        rows = normalize_series("CPI", db_path=fresh_db)
        # January daily rows (2024-01-01 through 2024-02-01) = 32 days.
        assert rows == 32

        df = get_normalized_history("CPI", days=1000, db_path=fresh_db)
        assert len(df) == 32
        jan_15 = df[df["date"] == "2024-01-15"]["value"].iloc[0]
        assert jan_15 == 300.0

    def test_date_range_filtering(self, fresh_db: Path) -> None:
        """start_date and end_date should limit the normalized output."""
        _insert_series(fresh_db, "CPI", "FRED", "M")
        _insert_observations(fresh_db, "CPI", ["2024-01-01", "2024-02-01"], [300.0, 301.0])

        rows = normalize_series("CPI", start_date="2024-01-15", end_date="2024-01-20", db_path=fresh_db)
        assert rows == 6

        df = get_normalized_history("CPI", days=1000, db_path=fresh_db)
        assert list(df["date"]) == [
            "2024-01-15", "2024-01-16", "2024-01-17", "2024-01-18", "2024-01-19", "2024-01-20"
        ]


# =============================================================================
# normalize_all
# =============================================================================


class TestNormalizeAll:
    """Tests for normalizing all macro series."""

    def test_normalizes_all_series(self, fresh_db: Path) -> None:
        """normalize_all should process every series in the registry."""
        _insert_series(fresh_db, "S1", "FRED", "D")
        _insert_series(fresh_db, "S2", "ECOS", "M")
        _insert_observations(fresh_db, "S1", ["2024-01-01", "2024-01-02"], [1.0, 2.0])
        _insert_observations(fresh_db, "S2", ["2024-01-01"], [10.0])

        results = normalize_all(db_path=fresh_db)
        assert results["S1"] == 2
        assert results["S2"] == 1

        status = get_normalized_status(db_path=fresh_db)
        assert len(status) == 2


# =============================================================================
# normalize_market_data
# =============================================================================


class TestNormalizeMarketData:
    """Tests for market data normalization."""

    def test_normalizes_market_prices(self, market_db: Path) -> None:
        """Market prices should be copied into normalized_daily with source and asset_type."""
        _insert_market_prices(
            market_db,
            "KOSPI",
            "pykrx",
            "index",
            ["2024-01-01", "2024-01-02"],
            [2500.0, 2510.0],
        )

        results = normalize_market_data(db_path=market_db)
        assert results["KOSPI"] == 2

        df = get_normalized_history("KOSPI", days=1000, db_path=market_db)
        assert len(df) == 2
        assert set(df["source"]) == {"pykrx"}
        assert set(df["asset_type"]) == {"index"}

    def test_uses_adj_close_when_available(self, market_db: Path) -> None:
        """The adjusted close price should be preferred over close."""
        with sqlite3.connect(market_db) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO market_prices "
                "(symbol, date, open, high, low, close, volume, adj_close, source, asset_type, name) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("SPY", "2024-01-01", 100.0, 100.0, 100.0, 100.0, 1000, 99.5, "yfinance", "etf", "SPY"),
            )
            conn.commit()

        normalize_market_data(db_path=market_db)
        df = get_normalized_history("SPY", days=1000, db_path=market_db)
        assert len(df) == 1
        assert df["value"].iloc[0] == 99.5


# =============================================================================
# get_normalized_status
# =============================================================================


class TestGetNormalizedStatus:
    """Tests for the normalization status summary."""

    def test_empty_status(self, fresh_db: Path) -> None:
        """An empty normalized_daily table should return an empty DataFrame."""
        df = get_normalized_status(db_path=fresh_db)
        assert df.empty

    def test_status_summary(self, fresh_db: Path) -> None:
        """Status should summarize row counts and date ranges."""
        _insert_series(fresh_db, "S1", "FRED", "D")
        _insert_observations(fresh_db, "S1", ["2024-01-01", "2024-01-02"], [1.0, 2.0])
        normalize_series("S1", db_path=fresh_db)

        df = get_normalized_status(db_path=fresh_db)
        assert len(df) == 1
        assert df["row_count"].iloc[0] == 2
        assert df["earliest_date"].iloc[0] == "2024-01-01"
        assert df["latest_date"].iloc[0] == "2024-01-02"
