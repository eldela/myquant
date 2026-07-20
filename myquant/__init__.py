"""myquant - secure FRED and ECOS API client package."""

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
from myquant.ecos import Ecos, EcosAPIError
from myquant.ecos_db import (
    CORE_SERIES as ECOS_CORE_SERIES,
    fetch_all as ecos_fetch_all,
    fetch_due as ecos_fetch_due,
    fetch_series as ecos_fetch_series,
    get_history as ecos_get_history,
    get_latest as ecos_get_latest,
    get_series_info as ecos_get_series_info,
    init_db as ecos_init_db,
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
    "Ecos",
    "EcosAPIError",
    "ECOS_CORE_SERIES",
    "ecos_init_db",
    "ecos_fetch_series",
    "ecos_fetch_all",
    "ecos_fetch_due",
    "ecos_get_latest",
    "ecos_get_history",
    "ecos_get_series_info",
]
