"""Command-line interface for the unified macro database.

Provides the ``python -m myquant.macro_db <command>`` entry point.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from myquant.db.core import (
    DEFAULT_DB_PATH,
    _connection,
    fetch_all,
    fetch_due,
    init_db,
)
from myquant.db.migration import migrate_legacy_dbs
from myquant.db.treasury import fetch_auctions, fetch_debt


def _status(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Print series info, observation counts, and last fetch dates."""
    with _connection(db_path) as conn:
        df = pd.read_sql_query(
            """
            SELECT
                s.id,
                s.title,
                s.source,
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
    """Command-line interface for the unified macro database."""
    parser = argparse.ArgumentParser(
        description="Unified macro database CLI (FRED + ECOS + Treasury)"
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Path to the SQLite database (default: %(default)s)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Create DB, tables, and seed series registry")

    fetch_all_p = subparsers.add_parser("fetch-all", help="Fetch all series")
    fetch_all_p.add_argument(
        "--source",
        choices=["fred", "ecos", "treasury", "all"],
        default="all",
        help="Data source to fetch from (default: all)",
    )

    fetch_due_p = subparsers.add_parser("fetch-due", help="Fetch only due series")
    fetch_due_p.add_argument(
        "--source",
        choices=["fred", "ecos", "treasury", "all"],
        default="all",
        help="Data source to fetch from (default: all)",
    )

    subparsers.add_parser("fetch-debt", help="Fetch Treasury Debt to the Penny")
    subparsers.add_parser("fetch-auctions", help="Fetch Treasury auction results")

    subparsers.add_parser("status", help="Show database status")

    migrate_p = subparsers.add_parser(
        "migrate", help="Migrate data from legacy DBs into macro.db"
    )
    migrate_p.add_argument(
        "--source-dir",
        type=Path,
        default=None,
        help="Directory containing fred.db, ecos.db, treasury.db "
             "(default: same directory as --db-path)",
    )

    args = parser.parse_args()

    if args.command == "init":
        init_db(args.db_path)
        print(f"Initialized database at {args.db_path}")
    elif args.command == "fetch-all":
        fetch_all(source=args.source, db_path=args.db_path)
    elif args.command == "fetch-due":
        fetch_due(source=args.source, db_path=args.db_path)
    elif args.command == "fetch-debt":
        fetch_debt(db_path=args.db_path)
    elif args.command == "fetch-auctions":
        fetch_auctions(db_path=args.db_path)
    elif args.command == "status":
        _status(args.db_path)
    elif args.command == "migrate":
        migrate_legacy_dbs(args.db_path, args.source_dir)
    else:  # pragma: no cover — argparse handles this
        parser.print_help()
