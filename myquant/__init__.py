"""myquant - a secure FRED API client package."""

from myquant.fred import Fred, FredAPIError
from myquant.fred_db import (
    CORE_SERIES,
    fetch_all,
    fetch_due,
    fetch_series,
    get_history,
    get_latest,
    get_series_info,
    init_db,
)

__all__ = [
    "Fred",
    "FredAPIError",
    "CORE_SERIES",
    "init_db",
    "fetch_series",
    "fetch_all",
    "fetch_due",
    "get_latest",
    "get_history",
    "get_series_info",
]
