import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "package", "contents", "code"))

import trend  # noqa: E402


def s(ts, v):
    return {"ts": ts, "value": v}


# --- compute_trend ---------------------------------------------------------

def test_trend_up():
    series = [s("2026-07-08T15:00:00+02:00", 16.0),
              s("2026-07-08T15:15:00+02:00", 17.0)]
    d, pct, win = trend.compute_trend(series, k=1, deadband_pct=0.5, max_gap_min=45)
    assert d == "up"
    assert pct == 6.25
    assert win == 15


def test_trend_down():
    series = [s("2026-07-08T15:00:00+02:00", 17.0),
              s("2026-07-08T15:15:00+02:00", 16.0)]
    d, _, _ = trend.compute_trend(series, k=1, deadband_pct=0.5, max_gap_min=45)
    assert d == "down"


def test_trend_flat_within_deadband():
    series = [s("2026-07-08T15:00:00+02:00", 16.00),
              s("2026-07-08T15:15:00+02:00", 16.05)]
    d, _, _ = trend.compute_trend(series, k=1, deadband_pct=0.5, max_gap_min=45)
    assert d == "flat"


def test_trend_warmup_returns_none():
    series = [s("2026-07-08T15:00:00+02:00", 16.0)]
    assert trend.compute_trend(series, k=1, deadband_pct=0.5, max_gap_min=45) == (None, None, None)


def test_trend_stale_gap_returns_none():
    series = [s("2026-07-08T13:00:00+02:00", 16.0),
              s("2026-07-08T15:00:00+02:00", 17.0)]  # 120 min gap
    assert trend.compute_trend(series, k=1, deadband_pct=0.5, max_gap_min=45) == (None, None, None)


def test_trend_uses_k_back_not_previous():
    series = [s("2026-07-08T15:00:00+02:00", 10.0),
              s("2026-07-08T15:15:00+02:00", 20.0),
              s("2026-07-08T15:30:00+02:00", 21.0)]
    # k=2 compares last(21) vs series[-3](10) -> up; window 30 min
    d, pct, win = trend.compute_trend(series, k=2, deadband_pct=0.5, max_gap_min=90)
    assert d == "up"
    assert win == 30


def test_trend_zero_reference_returns_none():
    series = [s("2026-07-08T15:00:00+02:00", 0.0),
              s("2026-07-08T15:15:00+02:00", 17.0)]
    assert trend.compute_trend(series, k=1, deadband_pct=0.5, max_gap_min=45) == (None, None, None)


# --- history round-trip ----------------------------------------------------

def test_history_roundtrip_and_trim(tmp_path):
    path = str(tmp_path / "history.json")
    h = trend.load_history(path)
    assert h == {}
    pts = [{"ticker": "^VIX", "value": 16.0}, {"ticker": "^VIX3M", "value": 19.0}]
    trend.append_and_trim(h, pts, "2026-07-08T15:00:00+02:00", cap=2)
    trend.append_and_trim(h, [{"ticker": "^VIX", "value": 16.5}], "2026-07-08T15:15:00+02:00", cap=2)
    trend.append_and_trim(h, [{"ticker": "^VIX", "value": 17.0}], "2026-07-08T15:30:00+02:00", cap=2)
    trend.save_history(path, h)
    reloaded = trend.load_history(path)
    assert [p["value"] for p in reloaded["^VIX"]] == [16.5, 17.0]  # trimmed to cap=2
    assert len(reloaded["^VIX3M"]) == 1


def test_append_skips_missing_value():
    h = {}
    trend.append_and_trim(h, [{"ticker": "^VIX", "value": None}], "2026-07-08T15:00:00+02:00")
    assert h == {}


def test_load_corrupt_returns_empty(tmp_path):
    path = tmp_path / "history.json"
    path.write_text("{not json")
    assert trend.load_history(str(path)) == {}
