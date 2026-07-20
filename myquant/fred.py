"""Secure client for the Federal Reserve Economic Data (FRED) API.

This module provides a small, safe wrapper around the FRED web service.  It
validates the API key, enforces HTTPS with certificate verification, keeps the
key out of exception messages, and returns pandas DataFrames for list-like
responses.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

__all__ = ["Fred", "FredAPIError"]


class FredAPIError(Exception):
    """Raised when the FRED API returns an error response."""


class Fred:
    """Secure client for the FRED API.

    Parameters
    ----------
    api_key : str, optional
        A FRED API key. If not supplied, the ``FRED_API_KEY`` environment
        variable is used. The key must be a 32-character lower-cased
        alphanumeric string.
    """

    _BASE_URL = "https://api.stlouisfed.org/fred/"
    _MAPS_BASE_URL = "https://api.stlouisfed.org/geofred/"
    _API_KEY_PATTERN = re.compile(r"^[a-z0-9]{32}$")
    _TIMEOUT = 30
    _LIST_KEYS = (
        "categories",
        "seriess",
        "tags",
        "releases",
        "release_dates",
        "sources",
        "elements",
        "observations",
        "vintage_dates",
    )

    def __init__(self, api_key: Optional[str] = None) -> None:
        key = api_key
        if key is None:
            key = os.getenv("FRED_API_KEY") or os.getenv("FRED_API")
        if not key:
            raise ValueError(
                "API key must be provided or set via the FRED_API_KEY or FRED_API "
                "environment variable."
            )
        if not isinstance(key, str):
            raise TypeError("API key must be a string.")
        if not self._API_KEY_PATTERN.match(key):
            raise ValueError(
                "API key must be a 32-character lower-cased alphanumeric string."
            )

        self._api_key = key

        self.meta_data: Dict[str, str] = {
            # Categories
            "category": f"{self._BASE_URL}category",
            "category_children": f"{self._BASE_URL}category/children",
            "category_related": f"{self._BASE_URL}category/related",
            "category_series": f"{self._BASE_URL}category/series",
            "category_tags": f"{self._BASE_URL}category/tags",
            "category_related_tags": f"{self._BASE_URL}category/related_tags",
            # Releases
            "releases": f"{self._BASE_URL}releases",
            "releases_dates": f"{self._BASE_URL}releases/dates",
            "release": f"{self._BASE_URL}release",
            "release_dates": f"{self._BASE_URL}release/dates",
            "release_series": f"{self._BASE_URL}release/series",
            "release_sources": f"{self._BASE_URL}release/sources",
            "release_tags": f"{self._BASE_URL}release/tags",
            "release_related_tags": f"{self._BASE_URL}release/related_tags",
            "release_tables": f"{self._BASE_URL}release/tables",
            # Series
            "series": f"{self._BASE_URL}series",
            "series_categories": f"{self._BASE_URL}series/categories",
            "series_observations": f"{self._BASE_URL}series/observations",
            "series_release": f"{self._BASE_URL}series/release",
            "series_search": f"{self._BASE_URL}series/search",
            "series_search_tags": f"{self._BASE_URL}series/search/tags",
            "series_search_related_tags": f"{self._BASE_URL}series/search/related_tags",
            "series_tags": f"{self._BASE_URL}series/tags",
            "series_updates": f"{self._BASE_URL}series/updates",
            "series_vintagedates": f"{self._BASE_URL}series/vintagedates",
            # Sources
            "sources": f"{self._BASE_URL}sources",
            "source": f"{self._BASE_URL}source",
            "source_releases": f"{self._BASE_URL}source/releases",
            # Tags
            "tags": f"{self._BASE_URL}tags",
            "related_tags": f"{self._BASE_URL}related_tags",
            "tags_series": f"{self._BASE_URL}tags/series",
            # Maps API
            "maps_shape_files": f"{self._MAPS_BASE_URL}shapes/file",
            "maps_series_group_meta": f"{self._MAPS_BASE_URL}series/group",
            "maps_series_regional_data": f"{self._MAPS_BASE_URL}series/data",
            "regional_data": f"{self._MAPS_BASE_URL}regional/data",
        }

    def __repr__(self) -> str:
        masked = self._mask_key(self._api_key)
        return f"Fred(api_key='{masked}')"

    def get_data(self, api_name: str, **kwargs: Any) -> Any:
        """Call a FRED endpoint and return parsed data.

        The query always includes ``api_key`` and ``file_type=json``.  Callers
        cannot override these values via ``kwargs``.

        Parameters
        ----------
        api_name : str
            Key in ``self.meta_data`` identifying the endpoint.
        **kwargs
            Additional query parameters.

        Returns
        -------
        pandas.DataFrame or dict
            A DataFrame when the response contains a known list key;
            otherwise the raw JSON dictionary.

        Raises
        ------
        FredAPIError
            If the FRED API returns an error response.
        requests.exceptions.RequestException
            If an HTTP or network error occurs.
        ValueError
            If ``api_name`` is unknown or the response cannot be parsed.
        """
        url = self.meta_data.get(api_name)
        if url is None:
            raise ValueError(f"Unknown API name: {api_name}")

        params: Dict[str, Any] = {
            "api_key": self._api_key,
            "file_type": "json",
        }
        # Ensure api_key and file_type cannot be overwritten by kwargs.
        for key, value in kwargs.items():
            if key not in params:
                params[key] = value

        try:
            res = requests.get(
                url, params=params, timeout=self._TIMEOUT, verify=True
            )
            res.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raise self._mask_exception(exc) from None

        try:
            data = res.json()
        except ValueError as exc:
            masked_message = self._mask_in(str(exc))
            raise ValueError(
                f"Failed to parse JSON response: {masked_message}"
            ) from None

        if isinstance(data, dict) and "error_code" in data:
            error_code = data.get("error_code")
            error_message = data.get("error_message", "Unknown error")
            raise FredAPIError(
                f"FRED API error {error_code}: {error_message}"
            )

        for key in self._LIST_KEYS:
            if key in data:
                if key == "elements":
                    return pd.DataFrame(data[key]).T
                return pd.DataFrame(data[key])

        return data

    def _mask_key(self, key: str) -> str:
        """Return a masked version of ``key``."""
        if len(key) <= 6:
            return "***"
        return f"{key[:3]}...{key[-3:]}"

    def _mask_in(self, text: str) -> str:
        """Replace the API key with its masked form inside ``text``."""
        return text.replace(self._api_key, self._mask_key(self._api_key))

    def _mask_exception(
        self, exc: requests.exceptions.RequestException
    ) -> requests.exceptions.RequestException:
        """Return a new RequestException with the API key masked."""
        exc_type = type(exc)
        masked_message = self._mask_in(str(exc))
        try:
            return exc_type(masked_message)
        except Exception:
            return requests.exceptions.RequestException(masked_message)
