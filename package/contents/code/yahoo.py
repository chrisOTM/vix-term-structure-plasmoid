#!/usr/bin/env python3
"""VIX cash-index data source for the term-structure plasmoid.

Yahoo's chart endpoint intermittently answers with a single bar instead of the
requested year for the thinner indices (``^VIX9D``, ``^VIX3M``): the last close
is current, but every 1y statistic derived from such a payload is wrong — the
percentile collapses to 100 and min/max collapse onto today's value.

Which payload a request gets is decided by the backend node it lands on: every
request over one connection answers the same way, while a fresh connection is
a fresh draw. Retries therefore have to open new connections, and since the TLS
handshake dominates their cost they are fired as a small concurrent wave rather
than one after another. The longest series any attempt returned wins.

Stdlib only, and the caller fetches the tickers in parallel too, so retrying
stays inside the plasmoid's fetch timeout. ``fetch_vix.py`` keeps yfinance as a
fallback for hosts where plain urllib requests are blocked.
"""

import json
import math
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

CHART_URL = "https://{host}/v8/finance/chart/{symbol}?range={range}&interval=1d"
HOSTS = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) vix-term-structure-plasmoid"
RANGE = "1y"

# A year of daily closes is ~250 bars; anything under this is a truncated
# payload, not a genuinely short history.
MIN_HISTORY_BARS = 120
RETRIES = 3
PARALLEL_ATTEMPTS = 3
RETRY_DELAY_S = 0.25


def http_get(url: str, headers: dict, timeout: float) -> str:
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def chart_url(ticker: str, host: str) -> str:
    return CHART_URL.format(host=host, symbol=urllib.parse.quote(ticker),
                            range=RANGE)


def parse_chart(payload: str) -> list:
    """Parse a chart response into ``[(YYYY-MM-DD, close), ...]``."""
    try:
        document = json.loads(payload)
    except ValueError as exc:
        raise ValueError(f"Malformed chart payload: {exc}")

    chart = document.get("chart") if isinstance(document, dict) else None
    if not isinstance(chart, dict):
        raise ValueError("No chart object in payload")

    error = chart.get("error")
    if error:
        description = error.get("description") if isinstance(error, dict) else None
        raise ValueError(description or str(error))

    results = chart.get("result") or []
    if not results:
        raise ValueError("No chart result returned")

    result = results[0]
    stamps = result.get("timestamp") or []
    quotes = (result.get("indicators") or {}).get("quote") or [{}]
    closes = quotes[0].get("close") or []

    points = []
    for stamp, close in zip(stamps, closes):
        try:
            value = float(close)
            day = datetime.fromtimestamp(stamp, timezone.utc).date().isoformat()
        except (TypeError, ValueError, OSError, OverflowError):
            continue
        if math.isfinite(value):
            points.append((day, value))

    if not points:
        raise ValueError("No usable close values in chart payload")

    points.sort(key=lambda item: item[0])
    return points


def fetch_series(ticker: str, timeout: float, retries: int = RETRIES,
                 min_bars: int = MIN_HISTORY_BARS, get=http_get,
                 sleep=time.sleep, attempts: int = PARALLEL_ATTEMPTS) -> list:
    """Fetch daily closes, repeating while Yahoo truncates the series.

    Each wave opens ``attempts`` connections at once — alternating the two
    query hosts — because a truncated answer is a property of the node the
    connection landed on, not of the request. Keeps the longest series any
    attempt returned, so a run that never sees a full year still reports the
    current value instead of failing outright.
    """
    series = None
    last_error = None

    def attempt(index: int):
        try:
            payload = get(chart_url(ticker, HOSTS[index % len(HOSTS)]),
                          {"User-Agent": USER_AGENT,
                           "Accept": "application/json"},
                          timeout)
            return parse_chart(payload)
        except Exception as exc:
            return exc

    width = max(1, attempts)
    for wave in range(max(1, retries)):
        if wave:
            sleep(RETRY_DELAY_S)

        with ThreadPoolExecutor(max_workers=width) as pool:
            results = list(pool.map(attempt,
                                    range(wave * width, wave * width + width)))

        for result in results:
            if isinstance(result, Exception):
                last_error = result
            elif series is None or len(result) > len(series):
                series = result

        if series is not None and len(series) >= min_bars:
            break

    if series is None:
        raise last_error if last_error else ValueError("No data returned")

    return series


def percentile_rank(values: list, current: float) -> float:
    """Percentile Rank (0–100): share of observations at or below ``current``."""
    if not values:
        raise ValueError("Empty series for percentile computation")
    at_or_below = sum(1 for value in values if value <= current)
    return round(at_or_below / len(values) * 100, 1)


def summarize(series: list, min_bars: int = MIN_HISTORY_BARS) -> dict:
    """Reduce a daily close series to the fields one chart point needs.

    ``percentile``/``min_1y``/``max_1y`` stay None below ``min_bars`` bars:
    statistics from a truncated payload would be worse than none at all.
    """
    if not series:
        raise ValueError("Empty series")

    as_of, value = series[-1]
    if not math.isfinite(value):
        raise ValueError("Invalid non-finite value")
    if value <= 0:
        raise ValueError("Invalid non-positive value")

    closes = [close for _, close in series]
    bars = len(closes)

    if bars >= min_bars:
        percentile = percentile_rank(closes, value)
        min_1y = round(min(closes), 2)
        max_1y = round(max(closes), 2)
    else:
        percentile = min_1y = max_1y = None

    prev_close = round(series[-2][1], 2) if bars >= 2 else None

    return {
        "value": round(value, 2),
        "percentile": percentile,
        "min_1y": min_1y,
        "max_1y": max_1y,
        "prev_close": prev_close,
        "bars": bars,
        "as_of": as_of,
    }


def fetch_ticker(ticker: str, timeout: float, retries: int = RETRIES,
                 min_bars: int = MIN_HISTORY_BARS, get=http_get) -> dict:
    """Fetch one index and summarize it."""
    return summarize(fetch_series(ticker, timeout, retries, min_bars, get=get),
                     min_bars)
