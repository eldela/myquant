"""Secure client for the Bank of Korea ECOS (Economic Statistics System) API.

This module provides a small, safe wrapper around the ECOS web service.  It
validates the service key, keeps the key out of exception messages and repr,
and returns pandas DataFrames for list-like responses.

Security note
-------------
ECOS serves requests over plain HTTP (not HTTPS) and embeds the service key
directly in the URL path.  The key is therefore transmitted in plaintext and
may appear in proxy or server logs.  This client never logs or prints the full
URL and masks the key in every exception message, but callers should be aware
of the transport limitation imposed by the API itself.
"""

from __future__ import annotations

import os
from typing import Optional

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

__all__ = ["Ecos", "EcosAPIError"]


class EcosAPIError(Exception):
    """Raised when the ECOS API returns an error response."""


class Ecos:
    """Secure client for the Bank of Korea ECOS API.

    Parameters
    ----------
    service_key : str, optional
        An ECOS service key. If not supplied, the ``ECOS_SERVICE_KEY``,
        ``ECOS_KEY``, or ``ECOS_API`` environment variable is used (in that
        order). The key must be a non-empty string.
    """

    _BASE_URL = "http://ecos.bok.or.kr/api"
    _TIMEOUT = 30
    _FORMAT = "json"
    _LANG = "kr"
    _START_COUNT = "1"
    _END_COUNT = "99999"

    def __init__(self, service_key: Optional[str] = None) -> None:
        key = service_key
        if key is None:
            key = (
                os.getenv("ECOS_SERVICE_KEY")
                or os.getenv("ECOS_KEY")
                or os.getenv("ECOS_API")
            )
        if not key:
            raise ValueError(
                "Service key must be provided or set via the ECOS_SERVICE_KEY, "
                "ECOS_KEY, or ECOS_API environment variable."
            )
        if not isinstance(key, str):
            raise TypeError("Service key must be a string.")

        self._service_key = key

    def __repr__(self) -> str:
        masked = self._mask_key(self._service_key)
        return f"Ecos(service_key='{masked}')"

    # ------------------------------------------------------------------
    # Public service methods
    # ------------------------------------------------------------------

    def get_statistic_table_list(self, 통계표코드: str = "") -> pd.DataFrame:
        """서비스 통계 목록 API - list available statistical tables."""
        return self._get("StatisticTableList", 통계표코드)

    def get_statistic_word(self, 용어: str) -> pd.DataFrame:
        """통계용어사전 API - look up statistical terminology."""
        return self._get("StatisticWord", 용어)

    def get_statistic_item_list(self, 통계표코드: str) -> pd.DataFrame:
        """통계 세부항목 목록 API - list items within a statistical table."""
        return self._get("StatisticItemList", 통계표코드)

    def get_statistic_search(
        self,
        통계표코드: str,
        주기: str,
        검색시작일자: str,
        검색종료일자: str,
        통계항목코드1: str = "",
        통계항목코드2: str = "",
        통계항목코드3: str = "",
        통계항목코드4: str = "",
    ) -> pd.DataFrame:
        """통계 조회 API - retrieve time-series observations.

        Parameters
        ----------
        통계표코드 : str
            Statistical table code (e.g. ``"901Y009"``).
        주기 : str
            Frequency - A(연), S(반년), Q(분기), M(월), SM(반월), D(일).
        검색시작일자, 검색종료일자 : str
            Date window in the format matching ``주기``
            (e.g. ``2015``, ``2015Q1``, ``201501``, ``20150101``).
        통계항목코드1..4 : str, optional
            Item codes used to filter the results.
        """
        return self._get(
            "StatisticSearch",
            통계표코드,
            주기,
            검색시작일자,
            검색종료일자,
            통계항목코드1,
            통계항목코드2,
            통계항목코드3,
            통계항목코드4,
        )

    def get_key_statistic_list(self) -> pd.DataFrame:
        """100대 통계지표 API - top 100 key economic indicators."""
        return self._get("KeyStatisticList", end_count="100")

    def get_statistic_meta(self, 데이터명: str) -> pd.DataFrame:
        """통계메타DB API - statistical metadata search."""
        return self._get("StatisticMeta", 데이터명)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(
        self, service_name: str, *params: str, end_count: Optional[str] = None
    ) -> pd.DataFrame:
        """Call an ECOS service and return the rows as a DataFrame.

        The URL is built as
        ``{base}/{service}/{key}/{format}/{lang}/{start}/{end}/{params...}``.
        The full URL (which embeds the service key) is never logged, printed,
        or included in exception messages.
        """
        segments = [
            service_name,
            self._service_key,
            self._FORMAT,
            self._LANG,
            self._START_COUNT,
            end_count or self._END_COUNT,
            *[str(p) for p in params],
        ]
        url = f"{self._BASE_URL}/{'/'.join(segments)}"

        try:
            res = requests.get(url, timeout=self._TIMEOUT)
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

        if isinstance(data, dict) and "RESULT" in data:
            result = data["RESULT"]
            code = result.get("CODE", "")
            message = result.get("MESSAGE", "Unknown error")
            if code == "INFO-200":
                # ECOS uses INFO-200 when the query matches no data.
                return pd.DataFrame()
            raise EcosAPIError(
                f"ECOS API error {code}: {self._mask_in(message)}"
            )

        service_data = data.get(service_name) if isinstance(data, dict) else None
        if not isinstance(service_data, dict) or "row" not in service_data:
            raise ValueError(
                f"Unexpected ECOS response structure for {service_name}"
            )

        return pd.DataFrame(service_data["row"])

    def _mask_key(self, key: str) -> str:
        """Return a masked version of ``key``."""
        if len(key) <= 6:
            return "***"
        return f"{key[:3]}...{key[-3:]}"

    def _mask_in(self, text: str) -> str:
        """Replace the service key with its masked form inside ``text``."""
        return text.replace(self._service_key, self._mask_key(self._service_key))

    def _mask_exception(
        self, exc: requests.exceptions.RequestException
    ) -> requests.exceptions.RequestException:
        """Return a new RequestException with the service key masked."""
        exc_type = type(exc)
        masked_message = self._mask_in(str(exc))
        try:
            return exc_type(masked_message)
        except Exception:
            return requests.exceptions.RequestException(masked_message)
