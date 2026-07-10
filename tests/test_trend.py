import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "package", "contents", "code"))

import trend  # noqa: E402


# --- classify_dod (day-over-day trend) -------------------------------------

def test_dod_up():
    d, pct = trend.classify_dod(17.0, 16.0, deadband_pct=0.5)
    assert d == "up"
    assert pct == 6.25


def test_dod_down():
    d, pct = trend.classify_dod(16.0, 17.0, deadband_pct=0.5)
    assert d == "down"
    assert pct == -5.88


def test_dod_flat_within_deadband():
    d, pct = trend.classify_dod(16.05, 16.00, deadband_pct=0.5)
    assert d == "flat"
    assert pct == 0.31


def test_dod_exact_deadband_is_flat():
    # A change exactly at +deadband classifies as flat (strict > / <).
    d, _ = trend.classify_dod(100.5, 100.0, deadband_pct=0.5)
    assert d == "flat"


def test_dod_none_inputs():
    assert trend.classify_dod(None, 16.0, deadband_pct=0.5) == (None, None)
    assert trend.classify_dod(16.0, None, deadband_pct=0.5) == (None, None)


def test_dod_zero_reference():
    assert trend.classify_dod(16.0, 0.0, deadband_pct=0.5) == (None, None)


def test_dod_negative_reference():
    # Non-positive reference is not a valid basis for a percent change.
    assert trend.classify_dod(16.0, -1.0, deadband_pct=0.5) == (None, None)
