"""Unified macro database — facade module.

.. note::
   The implementation has been moved to the :mod:`myquant.db` package.
   This module re-exports the public API for backward compatibility.
"""

from myquant.db import (
    AUCTIONS_START_DATE,
    CORE_SERIES,
    DEBT_START_DATE,
    DEFAULT_DB_PATH,
    PAGE_SIZE,
    SCHEMA,
    fetch_all,
    fetch_all_treasury,
    fetch_auctions,
    fetch_debt,
    fetch_due,
    fetch_series,
    get_auction_history,
    get_debt_history,
    get_history,
    get_latest,
    get_latest_auction,
    get_latest_debt,
    get_series_info,
    init_db,
    migrate_legacy_dbs,
)

# Private helpers re-exported for backward compatibility (used by tests and
# the deprecated shim modules via ``if __name__ == "__main__"``).
from myquant.db.core import (
    _ecos_time_to_date,
    _resolve_fetch_window,
    _today_str,
)
from myquant.db.cli import _main

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

if __name__ == "__main__":
    from myquant.db.cli import _main

    _main()
