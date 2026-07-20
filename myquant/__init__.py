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
from myquant.treasury import Treasury, TreasuryAPIError
from myquant.treasury_db import (
    fetch_all as treasury_fetch_all,
    fetch_auctions as treasury_fetch_auctions,
    fetch_debt as treasury_fetch_debt,
    get_auction_history as treasury_get_auction_history,
    get_debt_history as treasury_get_debt_history,
    get_latest_auction as treasury_get_latest_auction,
    get_latest_debt as treasury_get_latest_debt,
    init_db as treasury_init_db,
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
    "Treasury",
    "TreasuryAPIError",
    "treasury_init_db",
    "treasury_fetch_debt",
    "treasury_fetch_auctions",
    "treasury_fetch_all",
    "treasury_get_debt_history",
    "treasury_get_auction_history",
    "treasury_get_latest_debt",
    "treasury_get_latest_auction",
]
