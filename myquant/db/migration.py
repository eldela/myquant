"""Legacy database migration into the unified ``macro.db``.

Copies ``series``, ``observations``, and ``update_log`` from ``fred.db``
and ``ecos.db``, plus ``debt``, ``auctions``, and ``fetch_log`` from
``treasury.db``.  Fully idempotent: running twice produces no new rows.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict

from myquant.db.core import CORE_SERIES, DEFAULT_DB_PATH, init_db


def _build_ecos_cycle_map() -> Dict[str, str]:
    """Build ``{series_id: cycle}`` from :data:`CORE_SERIES` for ECOS entries."""
    return {
        s["id"]: s["cycle"]  # type: ignore[misc]
        for s in CORE_SERIES
        if s.get("source") == "ECOS"
    }


def _check_no_collisions(fred_path: Path, ecos_path: Path) -> None:
    """Assert no series ID appears in both FRED and ECOS databases.

    Raises :class:`ValueError` if any overlap is found — the migration aborts.
    """
    uri_fred = f"file:{fred_path}?mode=ro"
    uri_ecos = f"file:{ecos_path}?mode=ro"

    fconn = sqlite3.connect(uri_fred, uri=True)
    econn = sqlite3.connect(uri_ecos, uri=True)
    fconn.row_factory = sqlite3.Row
    econn.row_factory = sqlite3.Row

    try:
        fred_ids: set[str] = set(
            r["id"] for r in fconn.execute("SELECT id FROM series").fetchall()
        )
        ecos_ids: set[str] = set(
            r["id"] for r in econn.execute("SELECT id FROM series").fetchall()
        )
        overlap = fred_ids & ecos_ids
        if overlap:
            raise ValueError(
                f"ID collision detected between FRED and ECOS: {overlap}"
            )
    finally:
        fconn.close()
        econn.close()


def _migrate_fred(fred_path: Path, macro_conn: sqlite3.Connection) -> None:
    """Migrate FRED data into the unified database.

    Uses ``ATTACH`` for cross-database queries.  ``series`` and ``observations``
    use ``INSERT OR IGNORE`` (natural PKs); ``update_log`` uses ``WHERE NOT
    EXISTS`` deduplication because its ``id`` is AUTOINCREMENT.
    """
    macro_conn.execute(f"ATTACH DATABASE '{fred_path}' AS fred")
    try:
        # --- series (cycle = frequency for FRED) ---
        cur = macro_conn.execute(
            """
            INSERT OR IGNORE INTO main.series
                (id, title, source, frequency, cycle, units,
                 observation_start, observation_end, last_updated)
            SELECT
                id, title, 'FRED', frequency, frequency, units,
                observation_start, observation_end, last_updated
            FROM fred.series
            """
        )
        print(f"FRED series: {cur.rowcount} rows migrated")

        # --- observations (realtime fields preserved as-is) ---
        cur = macro_conn.execute(
            """
            INSERT OR IGNORE INTO main.observations
                (series_id, date, value, realtime_start, realtime_end)
            SELECT series_id, date, value, realtime_start, realtime_end
            FROM fred.observations
            """
        )
        print(f"FRED observations: {cur.rowcount} rows migrated")

        # --- update_log (dedup on business key) ---
        cur = macro_conn.execute(
            """
            INSERT INTO main.update_log
                (series_id, fetch_date, observation_start, observation_end,
                 rows_added, status, message, updated_at)
            SELECT
                series_id, fetch_date, observation_start, observation_end,
                rows_added, status, message, updated_at
            FROM fred.update_log AS src
            WHERE NOT EXISTS (
                SELECT 1 FROM main.update_log AS t
                WHERE t.series_id  = src.series_id
                  AND t.fetch_date = src.fetch_date
                  AND COALESCE(t.observation_start, '') = COALESCE(src.observation_start, '')
                  AND COALESCE(t.observation_end,   '') = COALESCE(src.observation_end,   '')
                  AND t.rows_added = src.rows_added
                  AND t.status     = src.status
            )
            """
        )
        print(f"FRED update_log: {cur.rowcount} rows migrated")
        macro_conn.commit()
    finally:
        macro_conn.execute("DETACH DATABASE fred")


def _migrate_ecos(
    ecos_path: Path, macro_conn: sqlite3.Connection
) -> None:
    """Migrate ECOS data into the unified database.

    Special handling vs FRED:
        - ``series.cycle`` is resolved from :data:`CORE_SERIES` (the ECOS
          ``series`` table does not store it).
        - ``observations.realtime_start`` / ``realtime_end`` are set to
          ``NULL`` because ECOS fills them with the fetch date rather than
          true revision timestamps.
    """
    cycle_map = _build_ecos_cycle_map()

    macro_conn.execute(f"ATTACH DATABASE '{ecos_path}' AS ecos")
    try:
        # --- series (cycle resolved per-row from CORE_SERIES) ---
        ecos_series_rows = macro_conn.execute(
            "SELECT * FROM ecos.series"
        ).fetchall()

        series_count = 0
        for row in ecos_series_rows:
            sid: str = row["id"]
            cycle: str = cycle_map.get(sid, "")
            if not cycle:
                # Fallback: use frequency if not found in registry
                cycle = row["frequency"]
                print(
                    f"WARNING: {sid} not found in CORE_SERIES registry "
                    f"— defaulting cycle to frequency ({cycle})"
                )
            cur = macro_conn.execute(
                "INSERT OR IGNORE INTO main.series "
                "(id, title, source, frequency, cycle, units, "
                " observation_start, observation_end, last_updated) "
                "VALUES (?, ?, 'ECOS', ?, ?, ?, ?, ?, ?)",
                (
                    sid,
                    row["title"],
                    row["frequency"],
                    cycle,
                    row["units"],
                    row["observation_start"],
                    row["observation_end"],
                    row["last_updated"],
                ),
            )
            if cur.rowcount > 0:
                series_count += 1
        print(f"ECOS series: {series_count} rows migrated")

        # --- observations (realtime fields → NULL) ---
        cur = macro_conn.execute(
            """
            INSERT OR IGNORE INTO main.observations
                (series_id, date, value, realtime_start, realtime_end)
            SELECT series_id, date, value, NULL, NULL
            FROM ecos.observations
            """
        )
        print(f"ECOS observations: {cur.rowcount} rows migrated")

        # --- update_log (dedup on business key) ---
        cur = macro_conn.execute(
            """
            INSERT INTO main.update_log
                (series_id, fetch_date, observation_start, observation_end,
                 rows_added, status, message, updated_at)
            SELECT
                series_id, fetch_date, observation_start, observation_end,
                rows_added, status, message, updated_at
            FROM ecos.update_log AS src
            WHERE NOT EXISTS (
                SELECT 1 FROM main.update_log AS t
                WHERE t.series_id  = src.series_id
                  AND t.fetch_date = src.fetch_date
                  AND COALESCE(t.observation_start, '') = COALESCE(src.observation_start, '')
                  AND COALESCE(t.observation_end,   '') = COALESCE(src.observation_end,   '')
                  AND t.rows_added = src.rows_added
                  AND t.status     = src.status
            )
            """
        )
        print(f"ECOS update_log: {cur.rowcount} rows migrated")
        macro_conn.commit()
    finally:
        macro_conn.execute("DETACH DATABASE ecos")


def _migrate_treasury(
    treasury_path: Path, macro_conn: sqlite3.Connection
) -> None:
    """Migrate Treasury data into the unified database.

    ``debt`` and ``auctions`` use ``INSERT OR IGNORE`` (natural PKs);
    ``fetch_log`` uses ``WHERE NOT EXISTS`` dedup (AUTOINCREMENT PK).
    """
    macro_conn.execute(f"ATTACH DATABASE '{treasury_path}' AS treasury")
    try:
        # --- debt (natural PK: record_date) ---
        cur = macro_conn.execute(
            """
            INSERT OR IGNORE INTO main.debt
                (record_date, debt_held_public_amt, intragov_hold_amt,
                 tot_pub_debt_out_amt)
            SELECT
                record_date, debt_held_public_amt, intragov_hold_amt,
                tot_pub_debt_out_amt
            FROM treasury.debt
            """
        )
        print(f"Treasury debt: {cur.rowcount} rows migrated")

        # --- auctions (natural PK: auction_date, cusip) ---
        cur = macro_conn.execute(
            """
            INSERT OR IGNORE INTO main.auctions
                (record_date, cusip, security_type, security_term,
                 auction_date, issue_date, maturity_date, interest_rate,
                 average_price, bid_to_cover_ratio, total_accepted,
                 competitive_accepted)
            SELECT
                record_date, cusip, security_type, security_term,
                auction_date, issue_date, maturity_date, interest_rate,
                average_price, bid_to_cover_ratio, total_accepted,
                competitive_accepted
            FROM treasury.auctions
            """
        )
        print(f"Treasury auctions: {cur.rowcount} rows migrated")

        # --- fetch_log (dedup on business key) ---
        cur = macro_conn.execute(
            """
            INSERT INTO main.fetch_log
                (dataset, fetch_date, records_added, status, message, updated_at)
            SELECT
                dataset, fetch_date, records_added, status, message, updated_at
            FROM treasury.fetch_log AS src
            WHERE NOT EXISTS (
                SELECT 1 FROM main.fetch_log AS t
                WHERE t.dataset       = src.dataset
                  AND t.fetch_date    = src.fetch_date
                  AND t.records_added = src.records_added
                  AND t.status        = src.status
            )
            """
        )
        print(f"Treasury fetch_log: {cur.rowcount} rows migrated")
        macro_conn.commit()
    finally:
        macro_conn.execute("DETACH DATABASE treasury")


def migrate_legacy_dbs(
    target_db_path: Path = DEFAULT_DB_PATH,
    source_dir: Optional[Path] = None,
) -> None:
    """Migrate data from legacy databases into the unified ``macro.db``.

    Copies ``series``, ``observations``, ``update_log`` from ``fred.db``
    and ``ecos.db``, plus ``debt``, ``auctions``, and ``fetch_log`` from
    ``treasury.db``.

    The migration is fully idempotent — running it twice on the same data
    produces zero additional rows.

    Parameters
    ----------
    target_db_path
        Path to the target ``macro.db``.
    source_dir
        Directory containing the legacy databases.  Defaults to the
        parent directory of ``target_db_path``.
    """
    if source_dir is None:
        source_dir = target_db_path.parent

    fred_path = source_dir / "fred.db"
    ecos_path = source_dir / "ecos.db"
    treasury_path = source_dir / "treasury.db"

    # 0. Ensure the target schema exists
    init_db(target_db_path)

    macro_conn = sqlite3.connect(target_db_path)
    macro_conn.row_factory = sqlite3.Row
    macro_conn.execute("PRAGMA foreign_keys = ON")

    try:
        # 1. ID collision check (before any data is copied)
        if fred_path.exists() and ecos_path.exists():
            _check_no_collisions(fred_path, ecos_path)

        # 2. FRED — series → observations → update_log
        if fred_path.exists():
            _migrate_fred(fred_path, macro_conn)
        else:
            print(f"WARNING: {fred_path} not found — skipping FRED migration")

        # 3. ECOS — series → observations → update_log
        if ecos_path.exists():
            _migrate_ecos(ecos_path, macro_conn)
        else:
            print(f"WARNING: {ecos_path} not found — skipping ECOS migration")

        # 4. Treasury — debt → auctions → fetch_log
        if treasury_path.exists():
            _migrate_treasury(treasury_path, macro_conn)
        else:
            print(
                f"WARNING: {treasury_path} not found "
                f"— skipping Treasury migration"
            )

        macro_conn.commit()
        print("Migration complete.")

    except Exception:
        macro_conn.rollback()
        raise
    finally:
        macro_conn.close()
