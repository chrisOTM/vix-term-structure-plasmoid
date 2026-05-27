#!/usr/bin/env python3
import argparse
import json
import math
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

try:
    import pandas as pd
    import yfinance as yf
except Exception as exc:
    def fallback_timestamp() -> str:
        return datetime.now(ZoneInfo("Europe/Berlin")).isoformat(timespec="seconds")

    print(json.dumps({
        "status": "error",
        "timestamp": fallback_timestamp(),
        "source": "Yahoo Finance via yfinance",
        "curve_state": "Unknown",
        "points": [],
        "errors": [{"message": f"Missing Python dependency or import error: {exc}"}],
    }, ensure_ascii=False))
    raise SystemExit(0)


TICKERS = [
    {"ticker": "^VIX9D", "label": "9D",  "name": "VIX 9-Day",    "days": 9},
    {"ticker": "^VIX",   "label": "30D", "name": "VIX 30-Day",   "days": 30},
    {"ticker": "^VIX3M", "label": "3M",  "name": "VIX 3-Month",  "days": 90},
    {"ticker": "^VIX6M", "label": "6M",  "name": "VIX 6-Month",  "days": 180},
    {"ticker": "^VIX1Y", "label": "1Y",  "name": "VIX 1-Year",   "days": 365},
]


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
    """Returns (value, percentile, min_1y, max_1y) for the given ticker."""
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

    return round(value, 2), percentile, min_1y, max_1y


def classify_curve(points: list) -> str:
    values = {point["label"]: point["value"] for point in points}

    required = ["9D", "30D", "3M"]
    if not all(label in values for label in required):
        return "Unknown"

    if values["9D"] > values["30D"] or values["30D"] > values["3M"]:
        return "Backwardation"

    if abs(values["30D"] - values["3M"]) < 0.5:
        return "Flat"

    return "Contango"


def build_result(status: str, points: list, errors: list) -> dict:
    return {
        "status": status,
        "timestamp": now_iso(),
        "source": "Yahoo Finance via yfinance",
        "curve_state": classify_curve(points),
        "points": points,
        "errors": errors,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch VIX cash term structure data.")
    parser.add_argument("--period",   default="1y")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--timeout",  type=float, default=10)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    points: list = []
    errors: list = []

    try:
        for item in TICKERS:
            try:
                value, percentile, min_1y, max_1y = fetch_latest_value(
                    ticker=item["ticker"],
                    period=args.period,
                    interval=args.interval,
                    timeout=args.timeout,
                )
                if item["label"] == "1Y":
                    percentile = None
                    min_1y = None
                    max_1y = None
                points.append({**item, "value": value, "percentile": percentile, "min_1y": min_1y, "max_1y": max_1y})
            except Exception as exc:
                print(f"{item['ticker']}: {exc}", file=sys.stderr)
                errors.append({"ticker": item["ticker"], "message": str(exc)})
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

    print(json.dumps(build_result(status, points, errors), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
