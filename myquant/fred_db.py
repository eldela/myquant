"""Deprecated shim — use myquant.macro_db instead.

This module is a thin wrapper that re-exports from :mod:`myquant.macro_db`.
It emits a :class:`DeprecationWarning` on import.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "myquant.fred_db is deprecated; use myquant.macro_db instead.",
    DeprecationWarning,
    stacklevel=2,
)

from myquant.macro_db import (
    CORE_SERIES,
    DEFAULT_DB_PATH,
    fetch_all,
    fetch_due,
    fetch_series,
    get_history,
    get_latest,
    get_series_info,
    init_db,
)

__all__ = [
    "DEFAULT_DB_PATH",
    "CORE_SERIES",
    "init_db",
    "fetch_series",
    "fetch_all",
    "fetch_due",
    "get_latest",
    "get_history",
    "get_series_info",
]

if __name__ == "__main__":
    from myquant.macro_db import _main

    _main()
