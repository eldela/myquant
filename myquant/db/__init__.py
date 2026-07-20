"""Unified macro database package.

Re-exports all public names from the submodules so that callers can
``from myquant.db import fetch_series``.
"""

from myquant.db.cli import _main, _status
from myquant.db.core import (
    AUCTIONS_START_DATE,
    CORE_SERIES,
    DEBT_START_DATE,
    DEFAULT_DB_PATH,
    PAGE_SIZE,
    SCHEMA,
    fetch_all,
    fetch_due,
    fetch_series,
    get_history,
    get_latest,
    get_series_info,
    init_db,
)
from myquant.db.migration import migrate_legacy_dbs
from myquant.db.treasury import (
    fetch_all_treasury,
    fetch_auctions,
    fetch_debt,
    get_auction_history,
    get_debt_history,
    get_latest_auction,
    get_latest_debt,
)

__all__ = [
    "CORE_SERIES",
    "DEFAULT_DB_PATH",
    "SCHEMA",
    "init_db",
    "fetch_series",
    "fetch_all",
    "fetch_due",
    "get_latest",
    "get_history",
    "get_series_info",
    "fetch_debt",
    "fetch_auctions",
    "fetch_all_treasury",
    "get_debt_history",
    "get_auction_history",
    "get_latest_debt",
    "get_latest_auction",
    "DEBT_START_DATE",
    "AUCTIONS_START_DATE",
    "PAGE_SIZE",
    "migrate_legacy_dbs",
]
