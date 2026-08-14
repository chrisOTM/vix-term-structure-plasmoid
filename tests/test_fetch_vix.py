import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "package", "contents", "code"))

import fetch_vix  # noqa: E402


def _points(values: dict) -> list:
    return [{"label": label, "value": value} for label, value in values.items()]


VIX_LABELS = fetch_vix.MARKETS["vix"]["curve_labels"]
VSTOXX_LABELS = fetch_vix.MARKETS["vstoxx"]["curve_labels"]


# --- classify_curve --------------------------------------------------------

def test_vix_contango():
    points = _points({"9D": 14.0, "30D": 15.0, "3M": 17.0})
    assert fetch_vix.classify_curve(points, VIX_LABELS) == "Contango"


def test_vix_backwardation_at_the_front():
    points = _points({"9D": 22.0, "30D": 20.0, "3M": 21.0})
    assert fetch_vix.classify_curve(points, VIX_LABELS) == "Backwardation"


def test_vix_flat_within_half_a_point():
    points = _points({"9D": 14.0, "30D": 15.0, "3M": 15.3})
    assert fetch_vix.classify_curve(points, VIX_LABELS) == "Flat"


def test_vix_unknown_when_a_tenor_is_missing():
    points = _points({"9D": 14.0, "3M": 17.0})
    assert fetch_vix.classify_curve(points, VIX_LABELS) == "Unknown"


def test_vstoxx_uses_its_own_tenor_labels():
    points = _points({"1M": 11.5, "2M": 15.5, "3M": 17.0})
    assert fetch_vix.classify_curve(points, VSTOXX_LABELS) == "Contango"


def test_vstoxx_backwardation():
    points = _points({"1M": 30.0, "2M": 28.0, "3M": 27.0})
    assert fetch_vix.classify_curve(points, VSTOXX_LABELS) == "Backwardation"


def test_vix_labels_do_not_classify_a_vstoxx_curve():
    # Guards against feeding the wrong market's labels: no 9D/30D in EU data.
    points = _points({"1M": 11.5, "2M": 15.5, "3M": 17.0})
    assert fetch_vix.classify_curve(points, VIX_LABELS) == "Unknown"


# --- build_result ----------------------------------------------------------

def test_build_result_tags_the_market_and_source():
    result = fetch_vix.build_result("vstoxx", "ok",
                                    _points({"1M": 11.5, "2M": 15.5, "3M": 17.0}),
                                    [], as_of="2026-08-14")
    assert result["market"] == "vstoxx"
    assert result["source"] == "STOXX (delayed) · 2026-08-14"
    assert result["curve_state"] == "Contango"


def test_build_result_source_without_data_date():
    result = fetch_vix.build_result("vix", "ok", [], [])
    assert result["source"] == "Yahoo Finance via yfinance"
    assert result["curve_state"] == "Unknown"


# --- build_point -----------------------------------------------------------

def test_build_point_attaches_trend():
    item = {"label": "1M", "name": "VSTOXX 1-Month", "days": 30}
    point = fetch_vix.build_point(item, 15.0, 40.0, 11.0, 30.0, 14.0,
                                  deadband_pct=0.5)
    assert point["label"] == "1M"
    assert point["value"] == 15.0
    assert point["trend"] == "up"
    assert point["trend_pct"] == 7.14


def test_build_point_without_previous_close_has_no_trend():
    item = {"label": "1M", "name": "VSTOXX 1-Month", "days": 30}
    point = fetch_vix.build_point(item, 15.0, 40.0, 11.0, 30.0, None,
                                  deadband_pct=0.5)
    assert point["trend"] is None
    assert point["trend_pct"] is None


# --- fetch_vstoxx_points ---------------------------------------------------

class _Args:
    timeout = 5
    trend_deadband_pct = 0.5


def test_fetch_vstoxx_points_reports_newest_data_date(monkeypatch):
    def fake_fetch_tenor(tenor, timeout):
        return {"value": 15.0, "percentile": 40.0, "min_1y": 11.0,
                "max_1y": 30.0, "prev_close": 14.0,
                "as_of": "2026-08-13" if tenor["label"] == "1M" else "2026-08-14"}

    monkeypatch.setattr(fetch_vix.stoxx, "fetch_tenor", fake_fetch_tenor)

    points, errors = [], []
    as_of = fetch_vix.fetch_vstoxx_points(_Args(), points, errors)

    assert as_of == "2026-08-14"
    assert [p["label"] for p in points] == ["1M", "2M", "3M", "6M", "12M"]
    assert errors == []


def test_fetch_vstoxx_points_keeps_going_after_one_tenor_fails(monkeypatch):
    def fake_fetch_tenor(tenor, timeout):
        if tenor["label"] == "3M":
            raise ValueError("network down")
        return {"value": 15.0, "percentile": 40.0, "min_1y": 11.0,
                "max_1y": 30.0, "prev_close": 14.0, "as_of": "2026-08-14"}

    monkeypatch.setattr(fetch_vix.stoxx, "fetch_tenor", fake_fetch_tenor)

    points, errors = [], []
    fetch_vix.fetch_vstoxx_points(_Args(), points, errors)

    assert [p["label"] for p in points] == ["1M", "2M", "6M", "12M"]
    assert errors == [{"ticker": "V6I3", "message": "network down"}]


# --- fetch_vix_points ------------------------------------------------------

def test_fetch_vix_points_reports_missing_dependency_as_an_error(monkeypatch):
    def boom():
        raise RuntimeError("Missing Python dependency or import error: no pandas")

    monkeypatch.setattr(fetch_vix, "require_yahoo", boom)

    points, errors = [], []
    fetch_vix.fetch_vix_points(_Args(), points, errors)

    assert points == []
    assert errors == [
        {"message": "Missing Python dependency or import error: no pandas"}]
