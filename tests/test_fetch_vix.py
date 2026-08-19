import os
import sys

import pytest

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
    assert result["source"] == "Yahoo Finance"
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
    period = "1y"
    interval = "1d"
    timeout = 5
    trend_deadband_pct = 0.5
    retries = 3
    min_history_bars = 120


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

def test_fetch_vix_points_reports_a_dead_fallback_per_ticker(monkeypatch):
    """Chart API down and no pandas: every ticker reports the fallback error."""
    def no_chart(ticker, timeout, retries, min_bars):
        raise OSError("connection reset")

    def boom():
        raise RuntimeError("Missing Python dependency or import error: no pandas")

    monkeypatch.setattr(fetch_vix.yahoo, "fetch_ticker", no_chart)
    monkeypatch.setattr(fetch_vix, "require_yahoo", boom)

    points, errors = [], []
    fetch_vix.fetch_vix_points(_Args(), points, errors)

    assert points == []
    assert [e["ticker"] for e in errors] == [t["ticker"] for t in fetch_vix.VIX_TICKERS]
    assert all("no pandas" in e["message"] for e in errors)


# --- download_close retries ------------------------------------------------

pd = pytest.importorskip("pandas")


def _frame(n: int, start: float = 15.0):
    """A daily Close frame with ``n`` bars, shaped like a yfinance download."""
    index = pd.date_range("2025-08-19", periods=n, freq="D")
    return pd.DataFrame({"Close": [start + i * 0.01 for i in range(n)]},
                        index=index)


class _FakeYahoo:
    """Serves a canned sequence of frames, one per download() call."""

    def __init__(self, frames):
        self.frames = list(frames)
        self.calls = 0

    def download(self, **kwargs):
        self.calls += 1
        return self.frames[min(self.calls - 1, len(self.frames) - 1)]


@pytest.fixture
def yfinance(monkeypatch):
    monkeypatch.setattr(fetch_vix, "pd", pd)
    monkeypatch.setattr(fetch_vix, "require_yahoo", lambda: (pd, None))

    def install(frames):
        fake = _FakeYahoo(frames)
        monkeypatch.setattr(fetch_vix, "yf", fake)
        return fake

    return install


def test_download_close_retries_a_truncated_series(yfinance, monkeypatch):
    monkeypatch.setattr(fetch_vix.time, "sleep", lambda _s: None)
    fake = yfinance([_frame(1), _frame(1), _frame(250)])

    close = fetch_vix.download_close("^VIX9D", "1y", "1d", 10)

    assert len(close) == 250
    assert fake.calls == 3


def test_download_close_stops_at_the_first_full_series(yfinance):
    fake = yfinance([_frame(250)])

    fetch_vix.download_close("^VIX9D", "1y", "1d", 10)

    assert fake.calls == 1


def test_download_close_returns_the_longest_series_it_saw(yfinance, monkeypatch):
    monkeypatch.setattr(fetch_vix.time, "sleep", lambda _s: None)
    yfinance([_frame(1), _frame(30), _frame(1)])

    close = fetch_vix.download_close("^VIX9D", "1y", "1d", 10)

    assert len(close) == 30


def test_download_close_raises_when_every_attempt_fails(yfinance, monkeypatch):
    monkeypatch.setattr(fetch_vix.time, "sleep", lambda _s: None)
    yfinance([pd.DataFrame()])

    with pytest.raises(ValueError):
        fetch_vix.download_close("^VIX9D", "1y", "1d", 10)


# --- fetch_latest_value on a truncated series ------------------------------

def test_fetch_latest_value_uses_the_chart_api_first(monkeypatch):
    monkeypatch.setattr(fetch_vix.yahoo, "fetch_ticker",
                        lambda ticker, timeout, retries, min_bars: {
                            "value": 12.87, "bars": 250, "percentile": 14.8,
                            "min_1y": 9.17, "max_1y": 30.64,
                            "prev_close": 12.9, "as_of": "2026-08-19"})

    result = fetch_vix.fetch_latest_value("^VIX9D", "1y", "1d", 10)

    assert result["value"] == 12.87
    assert result["percentile"] == 14.8


def test_fetch_latest_value_falls_back_to_yfinance(yfinance, monkeypatch):
    def no_chart(ticker, timeout, retries, min_bars):
        raise OSError("connection reset")

    monkeypatch.setattr(fetch_vix.yahoo, "fetch_ticker", no_chart)
    yfinance([_frame(250, start=15.0)])

    result = fetch_vix.fetch_latest_value("^VIX", "1y", "1d", 10)

    assert result["bars"] == 250
    assert result["percentile"] == 100.0
    assert result["min_1y"] == 15.0
    assert result["prev_close"] == 17.48


def test_fetch_latest_value_drops_1y_stats_when_the_fallback_is_short(
        yfinance, monkeypatch):
    def no_chart(ticker, timeout, retries, min_bars):
        raise OSError("connection reset")

    monkeypatch.setattr(fetch_vix.yahoo, "fetch_ticker", no_chart)
    monkeypatch.setattr(fetch_vix.time, "sleep", lambda _s: None)
    yfinance([_frame(1, start=12.87)])

    result = fetch_vix.fetch_latest_value("^VIX9D", "1y", "1d", 10)

    assert result["value"] == 12.87
    assert result["bars"] == 1
    assert result["percentile"] is None
    assert result["min_1y"] is None
    assert result["max_1y"] is None


# --- fetch_vix_points flags truncated history ------------------------------

def test_fetch_vix_points_reports_truncated_history_as_an_error(monkeypatch):
    def fake_fetch(ticker, period, interval, timeout, **kwargs):
        bars = 1 if ticker == "^VIX9D" else 250
        return {"value": 15.0, "bars": bars,
                "percentile": None if bars == 1 else 40.0,
                "min_1y": None if bars == 1 else 11.0,
                "max_1y": None if bars == 1 else 30.0,
                "prev_close": None if bars == 1 else 14.0}

    monkeypatch.setattr(fetch_vix, "require_yahoo", lambda: (None, None))
    monkeypatch.setattr(fetch_vix, "fetch_latest_value", fake_fetch)

    points, errors = [], []
    fetch_vix.fetch_vix_points(_Args(), points, errors)

    assert [p["label"] for p in points] == ["9D", "30D", "3M", "6M", "1Y"]
    assert [e["ticker"] for e in errors] == ["^VIX9D"]
    assert "1" in errors[0]["message"]


def test_fetch_vix_points_does_not_warn_about_vix1y(monkeypatch):
    """^VIX1Y has no history at Yahoo at all — that is expected, not an error."""
    def fake_fetch(ticker, period, interval, timeout, **kwargs):
        bars = 1 if ticker == "^VIX1Y" else 250
        return {"value": 22.8, "bars": bars,
                "percentile": None if bars == 1 else 40.0,
                "min_1y": None if bars == 1 else 11.0,
                "max_1y": None if bars == 1 else 30.0,
                "prev_close": None if bars == 1 else 14.0}

    monkeypatch.setattr(fetch_vix, "require_yahoo", lambda: (None, None))
    monkeypatch.setattr(fetch_vix, "fetch_latest_value", fake_fetch)

    points, errors = [], []
    fetch_vix.fetch_vix_points(_Args(), points, errors)

    assert errors == []
    one_year = [p for p in points if p["label"] == "1Y"][0]
    assert one_year["percentile"] is None
    assert one_year["min_1y"] is None
