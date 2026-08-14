#!/usr/bin/env python3
"""VSTOXX term-structure data source for the term-structure plasmoid.

Yahoo Finance carries no VSTOXX quotes, so the EURO STOXX 50 volatility curve
comes straight from STOXX. Two transports, in order:

1. ``quotes.stoxx.com`` delayed-series API, authorised with the API key that
   the public index pages ship in their HTML.
2. The index page itself, which embeds the same daily history in a
   ``window.chart_data`` literal. Used when the API key rotates.

Both give end-of-day closes back to 1999 — VSTOXX has no intraday feed here,
so values are the previous exchange close.

Stdlib only (no pandas/yfinance), so this module stays unit-testable offline
and the EU mode does not inherit the US mode's dependencies.
"""

import json
import math
import re
import urllib.request
from datetime import date, datetime, timedelta, timezone

API_KEY = "1388a22f-b1d4-4804-9a17-a59827c90e86"
SERIES_URL = "https://quotes.stoxx.com/api/v2/quote/delayed/series?isin={isin}"
PAGE_URL = "https://stoxx.com/index/{symbol}/"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) vix-term-structure-plasmoid"

# VSTOXX sub-indices as STOXX publishes them: one index per EURO STOXX 50
# option expiry, so these are fixed-expiry — not constant-maturity like the
# VIX cash indices. The front point therefore drifts down as its expiry nears.
TENORS = [
    {"symbol": "v6i1", "isin": "DE000A0G87B2", "label": "1M",
     "name": "VSTOXX 1-Month", "days": 30},
    {"symbol": "v6i2", "isin": "DE000A0G87C0", "label": "2M",
     "name": "VSTOXX 2-Month", "days": 60},
    {"symbol": "v6i3", "isin": "DE000A0G87D8", "label": "3M",
     "name": "VSTOXX 3-Month", "days": 90},
    {"symbol": "v6i4", "isin": "DE000A0G87E6", "label": "6M",
     "name": "VSTOXX 6-Month", "days": 180},
    {"symbol": "v6i6", "isin": "DE000A0G87G1", "label": "12M",
     "name": "VSTOXX 12-Month", "days": 365},
]

WINDOW_DAYS = 365


def http_get(url: str, headers: dict, timeout: float) -> str:
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _clean(points: list) -> list:
    """Drop non-finite closes and sort chronologically."""
    cleaned = []
    for day, close in points:
        try:
            value = float(close)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            cleaned.append((day, value))

    cleaned.sort(key=lambda item: item[0])
    if not cleaned:
        raise ValueError("No usable close values in series")
    return cleaned


def parse_series(payload: str) -> list:
    """Parse the quotes API response into ``[(YYYY-MM-DD, close), ...]``."""
    try:
        rows = json.loads(payload)
    except ValueError as exc:
        raise ValueError(f"Malformed series payload: {exc}")

    if not isinstance(rows, list):
        raise ValueError("Series payload is not a list")

    points = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        stamp = row.get("t")
        if not isinstance(stamp, str) or len(stamp) < 10:
            continue
        points.append((stamp[:10], row.get("close")))

    return _clean(points)


def parse_chart_data(html: str) -> list:
    """Parse the ``window.chart_data`` literal embedded in an index page."""
    match = re.search(r"window\.chart_data\s*=\s*(\[\[.*?\]\])\s*;", html, re.S)
    if not match:
        raise ValueError("No chart_data series found in page")

    try:
        rows = json.loads(match.group(1))
    except ValueError as exc:
        raise ValueError(f"Malformed chart_data series: {exc}")

    points = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 2:
            continue
        try:
            day = datetime.fromtimestamp(row[0] / 1000, timezone.utc).date().isoformat()
        except (TypeError, ValueError, OSError, OverflowError):
            continue
        points.append((day, row[1]))

    return _clean(points)


def percentile_rank(values: list, current: float) -> float:
    """Percentile Rank (0–100): share of observations at or below ``current``."""
    if not values:
        raise ValueError("Empty series for percentile computation")
    at_or_below = sum(1 for value in values if value <= current)
    return round(at_or_below / len(values) * 100, 1)


def window_last_year(series: list) -> list:
    """Trailing ``WINDOW_DAYS`` of ``series``, relative to its last data point."""
    if not series:
        raise ValueError("Empty series")
    cutoff = date.fromisoformat(series[-1][0]) - timedelta(days=WINDOW_DAYS)
    return [item for item in series if date.fromisoformat(item[0]) >= cutoff]


def summarize(series: list) -> dict:
    """Reduce a daily close series to the fields one chart point needs."""
    series = _clean(series)
    as_of, value = series[-1]

    if value <= 0:
        raise ValueError("Invalid non-positive value")

    window = window_last_year(series)
    closes = [close for _, close in window]

    prev_close = round(series[-2][1], 2) if len(series) >= 2 else None

    return {
        "value": round(value, 2),
        "percentile": percentile_rank(closes, value),
        "min_1y": round(min(closes), 2),
        "max_1y": round(max(closes), 2),
        "prev_close": prev_close,
        "as_of": as_of,
    }


def fetch_tenor(tenor: dict, timeout: float, get=http_get) -> dict:
    """Fetch one sub-index, API first and page scrape as fallback."""
    failures = []

    try:
        payload = get(SERIES_URL.format(isin=tenor["isin"]),
                      {"Authorization": API_KEY,
                       "Accept": "application/json",
                       "User-Agent": USER_AGENT},
                      timeout)
        return summarize(parse_series(payload))
    except Exception as exc:
        failures.append(f"quotes API: {exc}")

    try:
        html = get(PAGE_URL.format(symbol=tenor["symbol"]),
                   {"User-Agent": USER_AGENT},
                   timeout)
        return summarize(parse_chart_data(html))
    except Exception as exc:
        failures.append(f"index page: {exc}")

    raise ValueError("; ".join(failures))
