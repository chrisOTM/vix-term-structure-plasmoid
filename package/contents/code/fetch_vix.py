#!/usr/bin/env python3
"""Fetch a volatility term structure for the plasmoid.

Two markets, two data sources:

* ``vix``    — VIX cash indices from Yahoo Finance (stdlib, see ``yahoo.py``;
  yfinance is only a fallback when plain HTTP requests are blocked).
* ``vstoxx`` — VSTOXX sub-indices from STOXX (stdlib only, see ``stoxx.py``).

The pandas/yfinance imports stay lazy so both markets keep working on a machine
without them.
"""

import argparse
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

import stoxx
import trend
import yahoo

pd = None
yf = None

# Yahoo truncates the history of the thinner indices at random (see
# ``yahoo.py``); the tickers are fetched in parallel so retrying stays inside
# the plasmoid's fetch timeout.
MIN_HISTORY_BARS = yahoo.MIN_HISTORY_BARS
HISTORY_RETRIES = yahoo.RETRIES

# ^VIX1Y is quoted but not backfilled at Yahoo: even range=max returns one bar.
NO_HISTORY_LABELS = {"1Y"}

VIX_TICKERS = [
    {"ticker": "^VIX9D", "label": "9D",  "name": "VIX 9-Day",    "days": 9},
    {"ticker": "^VIX",   "label": "30D", "name": "VIX 30-Day",   "days": 30},
    {"ticker": "^VIX3M", "label": "3M",  "name": "VIX 3-Month",  "days": 90},
    {"ticker": "^VIX6M", "label": "6M",  "name": "VIX 6-Month",  "days": 180},
    {"ticker": "^VIX1Y", "label": "1Y",  "name": "VIX 1-Year",   "days": 365},
]

MARKETS = {
    "vix": {
        "source": "Yahoo Finance",
        # 9D > 30D or 30D > 3M means the front end is bid: backwardation.
        "curve_labels": ("9D", "30D", "3M"),
    },
    "vstoxx": {
        "source": "STOXX (delayed)",
        "curve_labels": ("1M", "2M", "3M"),
    },
}


def require_yahoo():
    """Import pandas/yfinance on first use; raise a readable error otherwise."""
    global pd, yf
    if pd is None or yf is None:
        try:
            import pandas as _pd
            import yfinance as _yf
        except Exception as exc:
            raise RuntimeError(f"Missing Python dependency or import error: {exc}")
        pd, yf = _pd, _yf
    return pd, yf


def now_iso() -> str:
    return datetime.now(ZoneInfo("Europe/Berlin")).isoformat(timespec="seconds")


def close_series(data: "pd.DataFrame", ticker: str) -> "pd.Series":
    if data is None or data.empty:
        raise ValueError("No data returned")

    if isinstance(data.columns, pd.MultiIndex):
        if ("Close", ticker) in data.columns:
            close = data[("Close", ticker)]
        elif (ticker, "Close") in data.columns:
            close = data[(ticker, "Close")]
        elif "Close" in data.columns.get_level_values(0):
            close = data["Close"].iloc[:, 0]
        elif "Close" in data.columns.get_level_values(-1):
            close = data.xs("Close", axis=1, level=-1).iloc[:, 0]
        else:
            raise ValueError("No Close column returned")
    else:
        if "Close" not in data.columns:
            raise ValueError("No Close column returned")
        close = data["Close"]

    close = pd.to_numeric(close, errors="coerce").dropna()
    if close.empty:
        raise ValueError("No valid close value returned")

    return close


def compute_percentile(close: "pd.Series", current_value: float) -> float:
    """Percentile Rank (0–100): Anteil der Tage mit Close ≤ current_value."""
    count = int((close <= current_value).sum())
    total = int(close.count())
    if total == 0:
        raise ValueError("Empty series for percentile computation")
    return round(count / total * 100, 1)


def download_close(ticker: str, period: str, interval: str, timeout: float,
                   retries: int = HISTORY_RETRIES,
                   min_bars: int = MIN_HISTORY_BARS) -> "pd.Series":
    """Download daily closes, retrying while Yahoo returns a truncated series.

    Keeps the longest series any attempt produced, so a run that never sees the
    full year still reports today's value instead of failing outright.
    """
    close = None
    last_error = None

    for attempt in range(max(1, retries)):
        if attempt:
            time.sleep(yahoo.RETRY_DELAY_S)
        try:
            data = yf.download(
                tickers=ticker,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=False,
                threads=False,
                timeout=timeout,
            )
            candidate = close_series(data, ticker)
        except Exception as exc:
            last_error = exc
            continue

        if close is None or len(candidate) > len(close):
            close = candidate
        if len(close) >= min_bars:
            break

    if close is None:
        raise last_error if last_error else ValueError("No data returned")

    return close


def summarize_close_series(close: "pd.Series", min_bars: int) -> dict:
    """Same summary shape as ``yahoo.summarize``, from a pandas close series."""
    value = float(close.iloc[-1])

    if not math.isfinite(value):
        raise ValueError("Invalid non-finite value")
    if value <= 0:
        raise ValueError("Invalid non-positive value")

    bars = int(close.count())
    if bars >= min_bars:
        percentile = compute_percentile(close, value)
        min_1y = round(float(close.min()), 2)
        max_1y = round(float(close.max()), 2)
    else:
        percentile = min_1y = max_1y = None

    prev_close = None
    if bars >= 2:
        candidate = float(close.iloc[-2])
        if math.isfinite(candidate):
            prev_close = round(candidate, 2)

    return {"value": round(value, 2), "percentile": percentile,
            "min_1y": min_1y, "max_1y": max_1y, "prev_close": prev_close,
            "bars": bars}


def fetch_via_yfinance(ticker: str, period: str, interval: str, timeout: float,
                       retries: int, min_bars: int) -> dict:
    """Fallback path: same data through pandas + yfinance."""
    require_yahoo()
    close = download_close(ticker, period, interval, timeout, retries, min_bars)
    return summarize_close_series(close, min_bars)


def fetch_latest_value(ticker: str, period: str, interval: str, timeout: float,
                       retries: int = HISTORY_RETRIES,
                       min_bars: int = MIN_HISTORY_BARS) -> dict:
    """Latest close plus its 1y statistics.

    Chart API first; yfinance only if that transport fails outright, so a
    machine without pandas still gets the curve.

    ``percentile``/``min_1y``/``max_1y`` are None when fewer than ``min_bars``
    closes came back — a one-bar series would otherwise report a 100th
    percentile and a range collapsed onto today's value. ``prev_close`` is the
    previous trading day's close (None on a single-bar series); it is the basis
    for the day-over-day trend.
    """
    try:
        return yahoo.fetch_ticker(ticker, timeout=timeout, retries=retries,
                                  min_bars=min_bars)
    except Exception as exc:
        print(f"{ticker}: chart API failed ({exc}); trying yfinance",
              file=sys.stderr)
        return fetch_via_yfinance(ticker, period, interval, timeout, retries,
                                  min_bars)


def classify_curve(points: list, curve_labels: tuple) -> str:
    """Contango / Backwardation / Flat from the three front tenors."""
    values = {point["label"]: point["value"] for point in points}

    near, mid, far = curve_labels
    if not all(label in values for label in curve_labels):
        return "Unknown"

    if values[near] > values[mid] or values[mid] > values[far]:
        return "Backwardation"

    if abs(values[mid] - values[far]) < 0.5:
        return "Flat"

    return "Contango"


def build_result(market: str, status: str, points: list, errors: list,
                 as_of: str = None) -> dict:
    profile = MARKETS[market]
    source = profile["source"]
    if as_of:
        source = f"{source} · {as_of}"

    return {
        "status": status,
        "market": market,
        "timestamp": now_iso(),
        "source": source,
        "curve_state": classify_curve(points, profile["curve_labels"]),
        "points": points,
        "errors": errors,
    }


def build_point(item: dict, value, percentile, min_1y, max_1y, prev_close,
                deadband_pct: float) -> dict:
    direction, trend_pct = trend.classify_dod(value, prev_close, deadband_pct)
    return {**item, "value": value, "percentile": percentile,
            "min_1y": min_1y, "max_1y": max_1y,
            "trend": direction, "trend_pct": trend_pct}


def fetch_vix_point(item: dict, args) -> tuple:
    """Fetch one ticker; returns (point, error) with either side possibly None."""
    no_history = item["label"] in NO_HISTORY_LABELS
    try:
        result = fetch_latest_value(
            ticker=item["ticker"],
            period=args.period,
            interval=args.interval,
            timeout=args.timeout,
            retries=1 if no_history else args.retries,
            min_bars=args.min_history_bars,
        )
    except Exception as exc:
        print(f"{item['ticker']}: {exc}", file=sys.stderr)
        return None, {"ticker": item["ticker"], "message": str(exc)}

    error = None
    if no_history:
        result["percentile"] = None
        result["min_1y"] = None
        result["max_1y"] = None
    elif result["percentile"] is None:
        message = (f"Only {result['bars']} daily close(s) returned; "
                   "1y stats unavailable")
        print(f"{item['ticker']}: {message}", file=sys.stderr)
        error = {"ticker": item["ticker"], "message": message}

    point = build_point(item, result["value"], result["percentile"],
                        result["min_1y"], result["max_1y"],
                        result["prev_close"], args.trend_deadband_pct)
    return point, error


def fetch_vix_points(args, points: list, errors: list) -> None:
    with ThreadPoolExecutor(max_workers=len(VIX_TICKERS)) as pool:
        results = list(pool.map(lambda item: fetch_vix_point(item, args),
                                VIX_TICKERS))

    for point, error in results:
        if point is not None:
            points.append(point)
        if error is not None:
            errors.append(error)


def fetch_vstoxx_points(args, points: list, errors: list) -> str:
    """Fill ``points`` from STOXX; returns the newest data date seen."""
    as_of = None

    for tenor in stoxx.TENORS:
        item = {"ticker": tenor["symbol"].upper(), "label": tenor["label"],
                "name": tenor["name"], "days": tenor["days"]}
        try:
            summary = stoxx.fetch_tenor(tenor, timeout=args.timeout)
            points.append(build_point(
                item, summary["value"], summary["percentile"],
                summary["min_1y"], summary["max_1y"], summary["prev_close"],
                args.trend_deadband_pct))
            if as_of is None or summary["as_of"] > as_of:
                as_of = summary["as_of"]
        except Exception as exc:
            print(f"{item['ticker']}: {exc}", file=sys.stderr)
            errors.append({"ticker": item["ticker"], "message": str(exc)})

    return as_of


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch a volatility cash term structure (VIX or VSTOXX).")
    parser.add_argument("--market",   default="vix", choices=sorted(MARKETS))
    parser.add_argument("--period",   default="1y")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--timeout",  type=float, default=10)
    parser.add_argument("--trend-deadband-pct",  type=float, default=0.5)
    parser.add_argument("--retries", type=int, default=HISTORY_RETRIES,
                        help="attempts per ticker when Yahoo truncates history")
    parser.add_argument("--min-history-bars", type=int, default=MIN_HISTORY_BARS,
                        help="daily closes required before 1y stats are trusted")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    points: list = []
    errors: list = []
    as_of = None

    try:
        if args.market == "vstoxx":
            as_of = fetch_vstoxx_points(args, points, errors)
        else:
            fetch_vix_points(args, points, errors)
    except Exception as exc:
        print(f"Unexpected error during fetch loop: {exc}", file=sys.stderr)
        errors.append({"message": f"Network or data source error: {exc}"})

    if points and errors:
        status = "partial"
    elif points:
        status = "ok"
    else:
        status = "error"
        if not errors:
            errors.append({"message": "No data returned"})

    print(json.dumps(build_result(args.market, status, points, errors, as_of),
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
