import json
import os
import sys

import pytest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "package", "contents", "code"))

import stoxx  # noqa: E402


# --- TENORS ----------------------------------------------------------------

def test_tenors_are_ordered_and_complete():
    assert [t["label"] for t in stoxx.TENORS] == ["1M", "2M", "3M", "6M", "12M"]
    assert [t["days"] for t in stoxx.TENORS] == [30, 60, 90, 180, 365]
    for tenor in stoxx.TENORS:
        assert tenor["isin"].startswith("DE")
        assert tenor["symbol"].startswith("v6i")


# --- parse_series (STOXX quotes API) ---------------------------------------

def test_parse_series_reads_date_and_close():
    payload = json.dumps([
        {"close": 21.2458, "t": "1999-01-04 00:00:00"},
        {"close": 36.64, "t": "1999-01-05 00:00:00"},
    ])
    assert stoxx.parse_series(payload) == [
        ("1999-01-04", 21.2458),
        ("1999-01-05", 36.64),
    ]


def test_parse_series_skips_null_and_non_finite_closes():
    payload = json.dumps([
        {"close": None, "t": "2026-08-11 00:00:00"},
        {"close": "nan", "t": "2026-08-12 00:00:00"},
        {"close": 15.5, "t": "2026-08-13 00:00:00"},
    ])
    assert stoxx.parse_series(payload) == [("2026-08-13", 15.5)]


def test_parse_series_sorts_by_date():
    payload = json.dumps([
        {"close": 2.0, "t": "2026-08-13 00:00:00"},
        {"close": 1.0, "t": "2026-08-12 00:00:00"},
    ])
    assert stoxx.parse_series(payload) == [("2026-08-12", 1.0), ("2026-08-13", 2.0)]


def test_parse_series_rejects_empty_payload():
    with pytest.raises(ValueError):
        stoxx.parse_series("[]")


def test_parse_series_rejects_malformed_payload():
    with pytest.raises(ValueError):
        stoxx.parse_series("not json")


# --- parse_chart_data (HTML fallback) --------------------------------------

def test_parse_chart_data_reads_embedded_series():
    html = (
        "<script>window.index_id = '40769';</script>"
        "<script>window.chart_data = [[915408000000,21.2458],[1786579200000,11.7975]];</script>"
    )
    assert stoxx.parse_chart_data(html) == [
        ("1999-01-04", 21.2458),
        ("2026-08-13", 11.7975),
    ]


def test_parse_chart_data_rejects_page_without_series():
    with pytest.raises(ValueError):
        stoxx.parse_chart_data("<html><body>no data here</body></html>")


# --- percentile_rank -------------------------------------------------------

def test_percentile_rank_counts_values_at_or_below():
    assert stoxx.percentile_rank([10.0, 20.0, 30.0, 40.0], 30.0) == 75.0


def test_percentile_rank_at_maximum_is_hundred():
    assert stoxx.percentile_rank([10.0, 20.0], 20.0) == 100.0


def test_percentile_rank_rejects_empty_series():
    with pytest.raises(ValueError):
        stoxx.percentile_rank([], 10.0)


# --- window_last_year ------------------------------------------------------

def test_window_last_year_keeps_only_trailing_365_days():
    series = [
        ("2024-01-01", 1.0),   # older than one year -> dropped
        ("2025-08-14", 2.0),   # exactly 365 days before the last point -> kept
        ("2026-08-13", 3.0),
    ]
    assert stoxx.window_last_year(series) == [("2025-08-14", 2.0), ("2026-08-13", 3.0)]


def test_window_last_year_rejects_empty_series():
    with pytest.raises(ValueError):
        stoxx.window_last_year([])


# --- summarize -------------------------------------------------------------

def test_summarize_builds_value_percentile_range_and_prev_close():
    series = [
        ("2026-08-11", 14.0),
        ("2026-08-12", 16.0),
        ("2026-08-13", 15.0),
    ]
    summary = stoxx.summarize(series)
    assert summary == {
        "value": 15.0,
        "percentile": 66.7,
        "min_1y": 14.0,
        "max_1y": 16.0,
        "prev_close": 16.0,
        "as_of": "2026-08-13",
    }


def test_summarize_without_previous_close():
    summary = stoxx.summarize([("2026-08-13", 15.0)])
    assert summary["prev_close"] is None
    assert summary["value"] == 15.0


def test_summarize_rejects_non_positive_value():
    with pytest.raises(ValueError):
        stoxx.summarize([("2026-08-13", 0.0)])


def test_summarize_percentile_uses_one_year_window_only():
    # A 2019 spike must not widen the 1y range.
    series = [("2019-03-01", 80.0), ("2026-08-12", 14.0), ("2026-08-13", 15.0)]
    summary = stoxx.summarize(series)
    assert summary["max_1y"] == 15.0
    assert summary["percentile"] == 100.0


# --- fetch_tenor (transport wiring, no live network) -----------------------

def _api_payload():
    return json.dumps([
        {"close": 14.0, "t": "2026-08-12 00:00:00"},
        {"close": 15.0, "t": "2026-08-13 00:00:00"},
    ])


def test_fetch_tenor_uses_quotes_api_when_it_answers():
    calls = []

    def fake_get(url, headers, timeout):
        calls.append(url)
        return _api_payload()

    summary = stoxx.fetch_tenor(stoxx.TENORS[0], timeout=5, get=fake_get)
    assert summary["value"] == 15.0
    assert calls == [stoxx.SERIES_URL.format(isin=stoxx.TENORS[0]["isin"])]


def test_fetch_tenor_sends_authorization_header():
    seen = {}

    def fake_get(url, headers, timeout):
        seen.update(headers)
        return _api_payload()

    stoxx.fetch_tenor(stoxx.TENORS[0], timeout=5, get=fake_get)
    assert seen["Authorization"] == stoxx.API_KEY


def test_fetch_tenor_falls_back_to_page_scrape_when_api_fails():
    html = "<script>window.chart_data = [[1786492800000,14.0],[1786579200000,15.0]];</script>"

    def fake_get(url, headers, timeout):
        if url.startswith(stoxx.SERIES_URL.split("?")[0]):
            raise OSError("HTTP Error 401: Unauthorized")
        return html

    summary = stoxx.fetch_tenor(stoxx.TENORS[0], timeout=5, get=fake_get)
    assert summary["value"] == 15.0
    assert summary["prev_close"] == 14.0


def test_fetch_tenor_falls_back_when_api_returns_unusable_payload():
    html = "<script>window.chart_data = [[1786579200000,15.0]];</script>"

    def fake_get(url, headers, timeout):
        return "[]" if "quotes.stoxx.com" in url else html

    assert stoxx.fetch_tenor(stoxx.TENORS[0], timeout=5, get=fake_get)["value"] == 15.0


def test_fetch_tenor_raises_when_both_sources_fail():
    def fake_get(url, headers, timeout):
        raise OSError("network down")

    with pytest.raises(ValueError):
        stoxx.fetch_tenor(stoxx.TENORS[0], timeout=5, get=fake_get)
