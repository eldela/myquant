"""Deprecated shim — use myquant.macro_db instead.

This module is a thin wrapper that re-exports from :mod:`myquant.macro_db`.
It emits a :class:`DeprecationWarning` on import.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "myquant.treasury_db is deprecated; use myquant.macro_db instead.",
    DeprecationWarning,
    stacklevel=2,
)

from myquant.macro_db import (
    DEFAULT_DB_PATH,
    fetch_all_treasury as fetch_all,
    fetch_auctions,
    fetch_debt,
    get_auction_history,
    get_debt_history,
    get_latest_auction,
    get_latest_debt,
    init_db,
)

__all__ = [
    "DEFAULT_DB_PATH",
    "init_db",
    "fetch_debt",
    "fetch_auctions",
    "fetch_all",
    "get_debt_history",
    "get_auction_history",
    "get_latest_debt",
    "get_latest_auction",
]

if __name__ == "__main__":
    from myquant.macro_db import _main

    _main()
