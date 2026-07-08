#!/usr/bin/env python3
"""Refresh-history-based trend detection for the VIX term-structure plasmoid.

Stdlib only — no pandas/yfinance — so it stays unit-testable offline.
"""
import json
import os
import sys
from datetime import datetime


def default_state_path() -> str:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(base, "vix-term-structure", "history.json")


def load_history(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def append_and_trim(history: dict, points: list, ts: str, cap: int = 32) -> dict:
    for point in points:
        ticker = point.get("ticker")
        value = point.get("value")
        if ticker is None or value is None:
            continue
        series = history.setdefault(ticker, [])
        series.append({"ts": ts, "value": float(value)})
        history[ticker] = series[-cap:]
    return history


def save_history(path: str, history: dict) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(history, fh, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception as exc:
        print(f"trend: could not save history: {exc}", file=sys.stderr)


def compute_trend(series: list, k: int, deadband_pct: float, max_gap_min: float) -> tuple:
    if not series or len(series) < k + 1:
        return (None, None, None)

    last = series[-1]
    ref = series[-1 - k]
    try:
        last_ts = datetime.fromisoformat(last["ts"])
        ref_ts = datetime.fromisoformat(ref["ts"])
    except Exception:
        return (None, None, None)

    window_min = (last_ts - ref_ts).total_seconds() / 60.0
    if window_min > max_gap_min:
        return (None, None, None)

    ref_val = ref["value"]
    if ref_val == 0:
        return (None, None, None)

    pct = (last["value"] - ref_val) / ref_val * 100.0
    if pct > deadband_pct:
        direction = "up"
    elif pct < -deadband_pct:
        direction = "down"
    else:
        direction = "flat"

    return (direction, round(pct, 2), int(round(window_min)))


def _set_null_trend(points: list) -> None:
    for point in points:
        point["trend"] = None
        point["trend_pct"] = None
        point["trend_window_min"] = None


def enrich_points_with_trend(points, state_path, k, deadband_pct,
                             refresh_interval_min, now_ts, cap=32) -> list:
    if not points:
        return points
    try:
        max_gap_min = refresh_interval_min * 3
        history = load_history(state_path)
        append_and_trim(history, points, now_ts, cap)
        save_history(state_path, history)
        for point in points:
            series = history.get(point.get("ticker"), [])
            direction, pct, window_min = compute_trend(
                series, k, deadband_pct, max_gap_min)
            point["trend"] = direction
            point["trend_pct"] = pct
            point["trend_window_min"] = window_min
    except Exception as exc:
        print(f"trend: enrichment failed: {exc}", file=sys.stderr)
        _set_null_trend(points)
    return points
