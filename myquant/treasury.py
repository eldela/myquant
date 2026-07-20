"""Client for the U.S. Treasury Fiscal Data API.

This module provides a small wrapper around the Treasury's Fiscal Data
web service. The API is fully public: no API key or authentication is
required. Responses are returned as the raw ``data`` list of records.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

import requests

__all__ = ["Treasury", "TreasuryAPIError"]


class TreasuryAPIError(Exception):
    """Raised when the Treasury Fiscal Data API returns an error response."""


class Treasury:
    """Client for the U.S. Treasury Fiscal Data API.

    No authentication is required; the API is fully public.
    """

    _BASE_URL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/"
    _TIMEOUT = 30

    def __repr__(self) -> str:
        return "Treasury()"

    def get_debt(
        self,
        page: int = 1,
        page_size: int = 100,
        fields: Optional[Union[str, List[str]]] = None,
        filters: Optional[Union[str, List[str]]] = None,
        sort: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch Debt to the Penny records.

        Calls ``v2/accounting/od/debt_to_penny`` and returns the ``data``
        list from the JSON response. All values are returned as strings.
        """
        return self._get(
            "v2/accounting/od/debt_to_penny",
            page=page,
            page_size=page_size,
            fields=fields,
            filters=filters,
            sort=sort,
        )

    def get_auctions(
        self,
        page: int = 1,
        page_size: int = 100,
        fields: Optional[Union[str, List[str]]] = None,
        filters: Optional[Union[str, List[str]]] = None,
        sort: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch Treasury securities auction results.

        Calls ``v1/accounting/od/auctions_query`` and returns the ``data``
        list from the JSON response. All values are returned as strings.
        """
        return self._get(
            "v1/accounting/od/auctions_query",
            page=page,
            page_size=page_size,
            fields=fields,
            filters=filters,
            sort=sort,
        )

    def _get(
        self,
        endpoint: str,
        page: int,
        page_size: int,
        fields: Optional[Union[str, List[str]]],
        filters: Optional[Union[str, List[str]]],
        sort: Optional[str],
    ) -> List[Dict[str, Any]]:
        """GET ``endpoint`` and return the ``data`` list from the response."""
        params: Dict[str, Any] = {
            "page[number]": page,
            "page[size]": page_size,
        }
        if fields:
            params["fields"] = (
                ",".join(fields) if isinstance(fields, (list, tuple)) else fields
            )
        if filters:
            params["filter"] = (
                ",".join(filters) if isinstance(filters, (list, tuple)) else filters
            )
        if sort:
            params["sort"] = sort

        url = f"{self._BASE_URL}{endpoint}"
        try:
            res = requests.get(url, params=params, timeout=self._TIMEOUT, verify=True)
            res.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raise TreasuryAPIError(f"Request to {endpoint} failed: {exc}") from None

        try:
            payload = res.json()
        except ValueError as exc:
            raise TreasuryAPIError(
                f"Failed to parse JSON response from {endpoint}: {exc}"
            ) from None

        if not isinstance(payload, dict) or "data" not in payload:
            raise TreasuryAPIError(
                f"Unexpected response shape from {endpoint}: "
                f"{str(payload)[:200]}"
            )

        return payload["data"]
