"""myquant - secure FRED and ECOS API client package."""

import importlib

from myquant.fred import Fred, FredAPIError
from myquant.ecos import Ecos, EcosAPIError
from myquant.treasury import Treasury, TreasuryAPIError

# Lazy imports for deprecated shim modules (fred_db, ecos_db, treasury_db).
# These shims import ``macro_db`` eagerly, so importing them at module level
# triggers a ``RuntimeWarning`` when ``python -m myquant.macro_db`` is invoked
# (Python finds ``macro_db`` already in ``sys.modules`` before running it as
# ``__main__``).  Using ``__getattr__`` defers the import until the name is
# first accessed, so ``import myquant`` stays quiet.
_LAZY: dict[str, tuple[str, str]] = {
    # name → (module, attribute_in_that_module)
    #
    # fred_db
    "CORE_SERIES": ("myquant.fred_db", "CORE_SERIES"),
    "init_db": ("myquant.fred_db", "init_db"),
    "fetch_series": ("myquant.fred_db", "fetch_series"),
    "fetch_all": ("myquant.fred_db", "fetch_all"),
    "fetch_due": ("myquant.fred_db", "fetch_due"),
    "get_latest": ("myquant.fred_db", "get_latest"),
    "get_history": ("myquant.fred_db", "get_history"),
    "get_series_info": ("myquant.fred_db", "get_series_info"),
    # ecos_db (aliased to ecos_ prefix in myquant namespace)
    "ECOS_CORE_SERIES": ("myquant.ecos_db", "CORE_SERIES"),
    "ecos_init_db": ("myquant.ecos_db", "init_db"),
    "ecos_fetch_series": ("myquant.ecos_db", "fetch_series"),
    "ecos_fetch_all": ("myquant.ecos_db", "fetch_all"),
    "ecos_fetch_due": ("myquant.ecos_db", "fetch_due"),
    "ecos_get_latest": ("myquant.ecos_db", "get_latest"),
    "ecos_get_history": ("myquant.ecos_db", "get_history"),
    "ecos_get_series_info": ("myquant.ecos_db", "get_series_info"),
    # treasury_db (aliased to treasury_ prefix in myquant namespace)
    "treasury_init_db": ("myquant.treasury_db", "init_db"),
    "treasury_fetch_debt": ("myquant.treasury_db", "fetch_debt"),
    "treasury_fetch_auctions": ("myquant.treasury_db", "fetch_auctions"),
    "treasury_fetch_all": ("myquant.treasury_db", "fetch_all"),
    "treasury_get_debt_history": ("myquant.treasury_db", "get_debt_history"),
    "treasury_get_auction_history": ("myquant.treasury_db", "get_auction_history"),
    "treasury_get_latest_debt": ("myquant.treasury_db", "get_latest_debt"),
    "treasury_get_latest_auction": ("myquant.treasury_db", "get_latest_auction"),
}


def __getattr__(name: str):
    """Lazily import symbols from deprecated shim modules on first access."""
    if name not in _LAZY:
        raise AttributeError(
            f"module 'myquant' has no attribute {name!r}"
        )
    module_name, attr = _LAZY[name]
    module = importlib.import_module(module_name)
    obj = getattr(module, attr)
    globals()[name] = obj  # cache for subsequent lookups
    return obj

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
