#!/usr/bin/env python3
"""Fetch a volatility term structure for the plasmoid.

Two markets, two data sources:

* ``vix``    — VIX cash indices from Yahoo Finance (needs pandas + yfinance).
* ``vstoxx`` — VSTOXX sub-indices from STOXX (stdlib only, see ``stoxx.py``).

The Yahoo dependencies are imported lazily so the VSTOXX mode keeps working on
a machine without pandas or yfinance.
"""

import argparse
import json
import math
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import stoxx
import trend

pd = None
yf = None

VIX_TICKERS = [
    {"ticker": "^VIX9D", "label": "9D",  "name": "VIX 9-Day",    "days": 9},
    {"ticker": "^VIX",   "label": "30D", "name": "VIX 30-Day",   "days": 30},
    {"ticker": "^VIX3M", "label": "3M",  "name": "VIX 3-Month",  "days": 90},
    {"ticker": "^VIX6M", "label": "6M",  "name": "VIX 6-Month",  "days": 180},
    {"ticker": "^VIX1Y", "label": "1Y",  "name": "VIX 1-Year",   "days": 365},
]

MARKETS = {
    "vix": {
        "source": "Yahoo Finance via yfinance",
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


def fetch_latest_value(ticker: str, period: str, interval: str, timeout: float) -> tuple:
    """Returns (value, percentile, min_1y, max_1y, prev_close) for the ticker.

    ``prev_close`` is the previous trading day's close (or None if the series
    has only one point); it is the basis for the day-over-day trend.
    """
    data = yf.download(
        tickers=ticker,
        period=period,
        interval=interval,
        progress=False,
        auto_adjust=False,
        threads=False,
        timeout=timeout,
    )

    close = close_series(data, ticker)
    value = float(close.iloc[-1])

    if not math.isfinite(value):
        raise ValueError("Invalid non-finite value")
    if value <= 0:
        raise ValueError("Invalid non-positive value")

    percentile = compute_percentile(close, value)
    min_1y = round(float(close.min()), 2)
    max_1y = round(float(close.max()), 2)

    prev_close = None
    if len(close) >= 2:
        candidate = float(close.iloc[-2])
        if math.isfinite(candidate):
            prev_close = round(candidate, 2)

    return round(value, 2), percentile, min_1y, max_1y, prev_close


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


def fetch_vix_points(args, points: list, errors: list) -> None:
    try:
        require_yahoo()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        errors.append({"message": str(exc)})
        return

    for item in VIX_TICKERS:
        try:
            value, percentile, min_1y, max_1y, prev_close = fetch_latest_value(
                ticker=item["ticker"],
                period=args.period,
                interval=args.interval,
                timeout=args.timeout,
            )
            # ^VIX1Y has less than a year of history: no meaningful 1y stats.
            if item["label"] == "1Y":
                percentile = None
                min_1y = None
                max_1y = None
            points.append(build_point(item, value, percentile, min_1y, max_1y,
                                      prev_close, args.trend_deadband_pct))
        except Exception as exc:
            print(f"{item['ticker']}: {exc}", file=sys.stderr)
            errors.append({"ticker": item["ticker"], "message": str(exc)})


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
