"""Thin clients for fetching market prices from pykrx and yfinance.

Normalizes both data sources into a simple DataFrame with columns:
``date, open, high, low, close, volume, adj_close``.

.. note::

    Korean index and ETF symbols are fetched through pykrx (requires KRX_ID/KRX_PW
    in .env). US symbols use yfinance.
"""

from __future__ import annotations

import warnings
from datetime import date, timedelta
from typing import Optional

import pandas as pd

__all__ = ["fetch_pykrx", "fetch_yfinance"]


# =============================================================================
# pykrx — Korean market
# =============================================================================


def _pykrx_ticker(symbol: str) -> str:
    """Map a watchlist symbol to the pykrx internal ticker code.

    pykrx uses numeric ticker codes for indices; ETFs keep their standard
    Korean ticker strings.
    """
    mapping = {
        "KOSPI": "1001",
        "KOSDAQ": "2001",
        "KOSPI200": "1028",
    }
    return mapping.get(symbol.upper(), symbol)


def _pykrx_date(d: str) -> str:
    """Convert ISO date ``YYYY-MM-DD`` to pykrx ``YYYYMMDD`` format."""
    return d.replace("-", "")


def fetch_pykrx(
    symbol: str,
    start_date: str,
    end_date: str,
) -> Optional[pd.DataFrame]:
    """Fetch daily OHLCV from pykrx for a Korean index or ETF.

    Parameters
    ----------
    symbol
        Watchlist symbol (e.g. ``"KOSPI"``, ``"069500"``).
    start_date
        ISO start date.
    end_date
        ISO end date.

    Returns
    -------
    pandas.DataFrame or None
        Normalized DataFrame with columns
        ``date, open, high, low, close, volume, adj_close``.
        Returns ``None`` if no data is available.
    """
    try:
        from pykrx import stock
    except ImportError as exc:  # pragma: no cover — tested at install time
        raise ImportError("pykrx is not installed") from exc

    ticker = _pykrx_ticker(symbol)
    pykrx_start = _pykrx_date(start_date)
    pykrx_end = _pykrx_date(end_date)

    # Suppress pykrx progress / warning chatter when fetching data.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if symbol.upper() in {"KOSPI", "KOSDAQ", "KOSPI200"}:
            raw = stock.get_index_ohlcv_by_date(
                pykrx_start, pykrx_end, ticker, freq="d"
            )
        else:
            raw = stock.get_etf_ohlcv_by_date(
                pykrx_start, pykrx_end, ticker, freq="d"
            )

    if raw is None or raw.empty:
        return None

    df = raw.reset_index()
    # The first column after reset_index is the date column.
    date_col = df.columns[0]
    df = df.rename(
        columns={
            date_col: "date",
            "시가": "open",
            "고가": "high",
            "저가": "low",
            "종가": "close",
            "거래량": "volume",
        }
    )
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df["volume"] = pd.to_numeric(df.get("volume"), errors="coerce")
    # pykrx does not provide adjusted close; use close as the proxy.
    df["adj_close"] = pd.to_numeric(df["close"], errors="coerce")
    df["open"] = pd.to_numeric(df["open"], errors="coerce")
    df["high"] = pd.to_numeric(df["high"], errors="coerce")
    df["low"] = pd.to_numeric(df["low"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df[["date", "open", "high", "low", "close", "volume", "adj_close"]]


# =============================================================================
# yfinance — US and Korean markets
# =============================================================================


def _yfinance_ticker(symbol: str) -> str:
    """Map a watchlist symbol to the yfinance ticker.

    Korean index/ETF symbols need the exchange suffix or index ticker form
    that yfinance recognizes.
    """
    mapping = {
        "KOSPI": "^KS11",
        "KOSDAQ": "^KQ11",
        "KOSPI200": "^KS200",
        "069500": "069500.KS",
        "364980": "364980.KS",
    }
    return mapping.get(symbol.upper(), symbol)


def fetch_yfinance(
    symbol: str,
    start_date: str,
    end_date: str,
) -> Optional[pd.DataFrame]:
    """Fetch daily OHLCV from yfinance for a US or Korean index or ETF.

    Watchlist symbols are mapped to the yfinance ticker that the service
    expects (e.g. ``"KOSPI"`` → ``"^KS11"`` and ``"069500"`` →
    ``"069500.KS"``).
    start_date
        ISO start date.
    end_date
        ISO end date.

    Returns
    -------
    pandas.DataFrame or None
        Normalized DataFrame with columns
        ``date, open, high, low, close, volume, adj_close``.
        Returns ``None`` if no data is available.
    """
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover — tested at install time
        raise ImportError("yfinance is not installed") from exc

    # ``end`` in yfinance is exclusive; add one day to make the window inclusive.
    end_exclusive = (date.fromisoformat(end_date) + timedelta(days=1)).isoformat()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ticker = yf.Ticker(_yfinance_ticker(symbol))
        hist = ticker.history(start=start_date, end=end_exclusive)

    if hist is None or hist.empty:
        return None

    df = hist.reset_index()
    # The date column may be 'Date' or the index name.
    date_col = df.columns[0]
    df = df.rename(
        columns={
            date_col: "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
            "Adj Close": "adj_close",
        }
    )
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df["open"] = pd.to_numeric(df.get("open"), errors="coerce")
    df["high"] = pd.to_numeric(df.get("high"), errors="coerce")
    df["low"] = pd.to_numeric(df.get("low"), errors="coerce")
    df["close"] = pd.to_numeric(df.get("close"), errors="coerce")
    df["volume"] = pd.to_numeric(df.get("volume"), errors="coerce")
    # Indices (^GSPC, ^IXIC, ^DJI, ^VIX) do not provide adjusted close.
    if "adj_close" in df.columns and not df["adj_close"].isna().all():
        df["adj_close"] = pd.to_numeric(df["adj_close"], errors="coerce")
    else:
        df["adj_close"] = df["close"]
    return df[["date", "open", "high", "low", "close", "volume", "adj_close"]]
