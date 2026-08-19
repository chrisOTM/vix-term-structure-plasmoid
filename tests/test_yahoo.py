import json
import os
import sys
import threading

import pytest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "package", "contents", "code"))

import yahoo  # noqa: E402


DAY = 86400
FIRST = 1755561600  # 2025-08-19T00:00:00Z


def _payload(closes: list, start: int = FIRST) -> str:
    stamps = [start + i * DAY for i in range(len(closes))]
    return json.dumps({"chart": {"error": None, "result": [{
        "meta": {"symbol": "^VIX9D"},
        "timestamp": stamps,
        "indicators": {"quote": [{"close": closes}]},
    }]}})


def _series(n: int, start_value: float = 15.0) -> list:
    return [(f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", start_value + i * 0.01)
            for i in range(n)]


# --- parse_chart -----------------------------------------------------------

def test_parse_chart_reads_dates_and_closes():
    assert yahoo.parse_chart(_payload([12.5, 13.0])) == [
        ("2025-08-19", 12.5),
        ("2025-08-20", 13.0),
    ]


def test_parse_chart_skips_null_and_non_finite_closes():
    parsed = yahoo.parse_chart(_payload([None, float("nan"), 15.5]))
    assert parsed == [("2025-08-21", 15.5)]


def test_parse_chart_raises_on_a_yahoo_error_object():
    payload = json.dumps({"chart": {"result": None, "error": {
        "code": "Not Found", "description": "No data found, symbol may be delisted"}}})
    with pytest.raises(ValueError, match="No data found"):
        yahoo.parse_chart(payload)


def test_parse_chart_raises_on_an_empty_result():
    with pytest.raises(ValueError, match="No chart result"):
        yahoo.parse_chart(json.dumps({"chart": {"result": [], "error": None}}))


def test_parse_chart_raises_on_malformed_json():
    with pytest.raises(ValueError, match="Malformed chart payload"):
        yahoo.parse_chart("<html>rate limited</html>")


# --- fetch_series ----------------------------------------------------------

class _FakeHttp:
    """Serves canned payloads, one per call, and records the URLs it saw.

    A wave of attempts calls this from several threads at once, so the payload
    order within one wave is arbitrary — tests keep a wave uniform.
    """

    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.urls = []
        self.lock = threading.Lock()

    def __call__(self, url, headers, timeout):
        with self.lock:
            self.urls.append(url)
            index = min(len(self.urls) - 1, len(self.payloads) - 1)
        payload = self.payloads[index]
        if isinstance(payload, Exception):
            raise payload
        return payload


@pytest.fixture
def no_sleep():
    return lambda _seconds: None


def test_fetch_series_retries_a_truncated_wave(no_sleep):
    truncated = [_payload([12.9])] * 2
    http = _FakeHttp(truncated + [_payload([15.0] * 250)])

    series = yahoo.fetch_series("^VIX9D", 5, get=http, sleep=no_sleep,
                                attempts=2)

    assert len(series) == 250
    assert len(http.urls) == 4  # one lost wave, then a winning one


def test_fetch_series_stops_after_the_first_full_wave(no_sleep):
    http = _FakeHttp([_payload([15.0] * 250)])

    yahoo.fetch_series("^VIX9D", 5, get=http, sleep=no_sleep, attempts=3)

    assert len(http.urls) == 3


def test_fetch_series_spreads_a_wave_over_both_query_hosts(no_sleep):
    http = _FakeHttp([_payload([15.0] * 250)])

    yahoo.fetch_series("^VIX9D", 5, get=http, sleep=no_sleep, attempts=2)

    assert {url.split("/")[2] for url in http.urls} == set(yahoo.HOSTS)


def test_fetch_series_keeps_the_longest_payload_it_saw(no_sleep):
    http = _FakeHttp([_payload([12.9]), _payload([15.0] * 30),
                      _payload([12.9])])

    series = yahoo.fetch_series("^VIX9D", 5, retries=3, get=http,
                                sleep=no_sleep, attempts=1)

    assert len(series) == 30


def test_fetch_series_raises_the_last_error_when_every_attempt_fails(no_sleep):
    http = _FakeHttp([OSError("connection reset")])

    with pytest.raises(OSError, match="connection reset"):
        yahoo.fetch_series("^VIX9D", 5, retries=2, get=http, sleep=no_sleep,
                           attempts=2)


def test_fetch_series_escapes_the_caret_in_the_ticker(no_sleep):
    http = _FakeHttp([_payload([15.0] * 250)])

    yahoo.fetch_series("^VIX9D", 5, get=http, sleep=no_sleep, attempts=1)

    assert "%5EVIX9D" in http.urls[0]


# --- summarize -------------------------------------------------------------

def test_summarize_reports_stats_on_a_full_year():
    summary = yahoo.summarize(_series(250, start_value=15.0))

    assert summary["value"] == 17.49
    assert summary["bars"] == 250
    assert summary["percentile"] == 100.0
    assert summary["min_1y"] == 15.0
    assert summary["max_1y"] == 17.49
    assert summary["prev_close"] == 17.48


def test_summarize_drops_stats_on_a_truncated_series():
    summary = yahoo.summarize([("2026-08-19", 12.87)])

    assert summary["value"] == 12.87
    assert summary["bars"] == 1
    assert summary["percentile"] is None
    assert summary["min_1y"] is None
    assert summary["max_1y"] is None
    assert summary["prev_close"] is None


def test_summarize_rejects_a_non_positive_value():
    with pytest.raises(ValueError, match="non-positive"):
        yahoo.summarize(_series(200) + [("2026-08-19", 0.0)])


def test_summarize_raises_on_an_empty_series():
    with pytest.raises(ValueError, match="Empty series"):
        yahoo.summarize([])


# --- fetch_ticker ----------------------------------------------------------

def test_fetch_ticker_returns_a_point_summary():
    http = _FakeHttp([_payload([15.0] * 250)])

    summary = yahoo.fetch_ticker("^VIX", 5, get=http)

    assert summary["bars"] == 250
    assert summary["as_of"] == "2026-04-25"
