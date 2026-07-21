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
from myquant.db.market import (
    init_market_tables,
    seed_watchlist,
    fetch_market_data,
    fetch_all_market_data,
    get_market_history,
    get_market_status,
)
from myquant.db.normalization import (
    init_normalization_tables,
    normalize_all,
    normalize_market_data,
    normalize_series,
    get_normalized_status,
)


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

    # Market commands
    subparsers.add_parser("init-market", help="Initialize market tables and seed watchlist")
    subparsers.add_parser("fetch-market", help="Fetch all market data for watchlist symbols")
    subparsers.add_parser("market-status", help="Show market monitoring status")

    market_history_p = subparsers.add_parser(
        "market-history", help="Show price history for a symbol"
    )
    market_history_p.add_argument("symbol", help="Symbol to query (e.g. KOSPI, SPY)")

    # Normalization commands
    subparsers.add_parser(
        "init-normalization", help="Initialize normalized_daily table and indexes"
    )

    normalize_p = subparsers.add_parser(
        "normalize", help="Normalize macro series and market data to daily frequency"
    )
    normalize_p.add_argument(
        "--series",
        default=None,
        help="Normalize only a single series/symbol (default: all)",
    )
    normalize_p.add_argument(
        "--start-date",
        default=None,
        help="ISO start date for the normalization window",
    )
    normalize_p.add_argument(
        "--end-date",
        default=None,
        help="ISO end date for the normalization window",
    )
    normalize_p.add_argument(
        "--market-only",
        action="store_true",
        help="Normalize only market prices, skipping macro series",
    )
    normalize_p.add_argument(
        "--macro-only",
        action="store_true",
        help="Normalize only macro series, skipping market prices",
    )

    subparsers.add_parser(
        "normalized-status", help="Show normalization status"
    )

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
    elif args.command == "init-market":
        init_market_tables(args.db_path)
        seed_watchlist(args.db_path)
        print(f"Initialized market tables and seeded watchlist at {args.db_path}")
    elif args.command == "fetch-market":
        results = fetch_all_market_data(args.db_path)
        total = sum(results.values())
        print(f"Fetched {len(results)} symbols, {total} total records")
    elif args.command == "market-status":
        df = get_market_status(args.db_path)
        print(df.to_string(index=False))
    elif args.command == "market-history":
        df = get_market_history(args.symbol, days=90, db_path=args.db_path)
        if df.empty:
            print(f"No data found for {args.symbol}")
        else:
            print(df.to_string(index=False))
    elif args.command == "init-normalization":
        init_normalization_tables(args.db_path)
        print(f"Initialized normalization tables at {args.db_path}")
    elif args.command == "normalize":
        if args.market_only and args.macro_only:
            print("Error: --market-only and --macro-only cannot be used together")
            return
        if args.series is not None:
            rows = normalize_series(
                args.series,
                start_date=args.start_date,
                end_date=args.end_date,
                db_path=args.db_path,
            )
            print(f"Normalized {args.series}: {rows} rows")
        elif args.market_only:
            results = normalize_market_data(
                start_date=args.start_date,
                end_date=args.end_date,
                db_path=args.db_path,
            )
            total = sum(results.values())
            print(f"Normalized {len(results)} market symbols, {total} total rows")
        elif args.macro_only:
            results = normalize_all(
                start_date=args.start_date,
                end_date=args.end_date,
                db_path=args.db_path,
            )
            total = sum(results.values())
            print(f"Normalized {len(results)} macro series, {total} total rows")
        else:
            macro_results = normalize_all(
                start_date=args.start_date,
                end_date=args.end_date,
                db_path=args.db_path,
            )
            market_results = normalize_market_data(
                start_date=args.start_date,
                end_date=args.end_date,
                db_path=args.db_path,
            )
            total = sum(macro_results.values()) + sum(market_results.values())
            print(
                f"Normalized {len(macro_results)} macro series and "
                f"{len(market_results)} market symbols, {total} total rows"
            )
    elif args.command == "normalized-status":
        df = get_normalized_status(args.db_path)
        if df.empty:
            print("No normalized data")
        else:
            print(df.to_string(index=False))
    elif args.command == "migrate":
        migrate_legacy_dbs(args.db_path, args.source_dir)
    else:  # pragma: no cover — argparse handles this
        parser.print_help()
