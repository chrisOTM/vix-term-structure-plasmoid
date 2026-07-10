#!/usr/bin/env python3
"""Day-over-day trend classification for the VIX term-structure plasmoid.

The trend compares the latest close against the previous trading day's close.
Unlike an intraday refresh-based trend, this stays meaningful whenever the
plasmoid is viewed — including outside US market hours, when the VIX cash
index does not move. Stdlib only, so it stays unit-testable offline.
"""


def classify_dod(last, prev, deadband_pct: float) -> tuple:
    """Classify day-over-day change of ``last`` vs ``prev``.

    Returns ``(direction, pct)`` where direction is "up"/"down"/"flat", or
    ``(None, None)`` when there is no valid basis (missing values or a
    non-positive reference). A change of exactly ``±deadband_pct`` is flat.
    """
    if last is None or prev is None or prev <= 0:
        return (None, None)

    pct = (last - prev) / prev * 100.0
    if pct > deadband_pct:
        direction = "up"
    elif pct < -deadband_pct:
        direction = "down"
    else:
        direction = "flat"

    return (direction, round(pct, 2))
