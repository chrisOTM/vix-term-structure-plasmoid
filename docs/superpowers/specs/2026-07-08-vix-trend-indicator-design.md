# VIX Spot Trend Indicator — Design

Date: 2026-07-08
Status: Approved (pending spec review)

## Goal

Show, per VIX maturity (9D, 30D, 3M, 6M, 1Y), whether the spot value is
**rising, falling, or flat** since recent refreshes, as a colored arrow next
to the current value.

Direction is derived from the widget's own refresh cadence: **each data refresh
is one data point**. The trend window therefore scales with the configured
refresh interval — shorter interval → more, tighter points; longer interval →
a longer wall-clock window.

Color semantics (risk reading, consistent with existing red percentile
extremes):

- `▲` red — VIX rising (risk up)
- `▼` green — VIX falling
- `⟶` grey — flat

This stays a visual tool only — not a trading signal.

## Approach

Chosen: **state-file (history) approach**, no extra network cost.

The current value per ticker is already fetched every refresh (`point.value`).
We persist a small rolling history and compare the latest value against the
value K refreshes back. No intraday download is added.

Rejected alternatives:

- **Intraday-slope** (fetch a `period=1d, interval=15m` series and read its
  slope): feasible (all 5 tickers serve intraday bars) but its window is fixed
  in wall-clock and does not track the refresh cadence the user wants; also
  costs one extra network call per refresh.
- **Daily close-over-close**: too coarse, cannot show intraday direction.

## Trend computation

Reference point is **configurable**: compare the latest value against the value
from **K refreshes ago** (K = `trendLookbackRefreshes`, default 3, min 1).

```
last  = history[-1].value
ref   = history[-1-K].value      # K points back
pct   = (last - ref) / ref * 100
dir   = "up"   if pct >  deadband
        "down" if pct < -deadband
        "flat" otherwise
```

- `deadband` = 0.5 % (fixed default).
- `trend_window_min` = real minutes between `ref.ts` and `last.ts` (measured
  from stored timestamps, not assumed from the interval).

### Edge cases (must be handled)

- **Warm-up:** fewer than `K+1` stored points → `trend = null`, no arrow.
- **Overnight / stale reference:** if the gap between `last.ts` and `ref.ts`
  exceeds `3 × refreshIntervalMinutes`, treat as stale → `trend = null`. Avoids
  a false overnight jump when the market was closed between refreshes.
- **Market closed:** successive closes are equal → `pct ≈ 0` → `flat`.
- **Missing ticker in a refresh:** if a ticker has no value this refresh, do not
  append a point for it; its previous history is retained.

## Components

### 1. Python — `package/contents/code/fetch_vix.py`

State file: `${XDG_CACHE_HOME:-~/.cache}/vix-term-structure/history.json`.

Structure:

```json
{ "^VIX9D": [ {"ts": "2026-07-08T15:00:00+02:00", "value": 15.6}, ... ], ... }
```

- `load_history(path) -> dict` — tolerant of missing/corrupt file (returns `{}`).
- `append_and_trim(history, points, cap=32) -> dict` — append current values,
  keep at most `cap` most-recent points per ticker.
- `save_history(path, history)` — atomic write (temp file + `os.replace`);
  failures are non-fatal (logged to stderr, trend just unavailable next time).
- `compute_trend(series, k, deadband, max_gap_min) -> (dir, pct, window_min)` —
  applies the formula and edge-case rules above.
- `main()` wires it in: after building `points`, load history, append, save,
  then attach `trend`, `trend_pct`, `trend_window_min` to each point.
  A failure anywhere in the trend block sets `trend = null` for all points and
  leaves the existing daily/percentile output untouched (fully graceful).

New CLI args (all with defaults, no breaking change):

- `--trend-lookback` (int, default 3) — K.
- `--trend-deadband-pct` (float, default 0.5).
- `--refresh-interval-min` (float, default 15) — used only for the staleness
  guard (`3 ×`).
- `--state-file` (str, default the XDG path above) — overridable for tests.

Point JSON gains: `"trend"` (`"up"|"down"|"flat"|null`), `"trend_pct"`
(float|null), `"trend_window_min"` (int|null).

### 2. QML — `package/contents/ui/ChartView.qml`

- Helpers `trendGlyph(dir)` → `▲/▼/⟶` and `trendColor(dir)` →
  `Kirigami.Theme.negativeTextColor` (up) / `positiveTextColor` (down) /
  `disabledTextColor` (flat).
- When `showValues` and `point.trend != null`, draw the glyph immediately to the
  right of the value label at each point, in the trend color. Value label stays
  in `textColor`. Skip drawing when `trend == null`.

### 3. QML — `package/contents/ui/main.qml` (value table)

- In the table rows (shown when `showTable`), render the same glyph next to each
  value using the same color mapping, gated on `showTrendArrows` and
  `trend != null`.

### 4. Config — `main.xml` + `configGeneral.qml`

- `main.xml`: new entries
  - `showTrendArrows` (Bool, default `true`).
  - `trendLookbackRefreshes` (Int, default `3`, min `1`).
- `configGeneral.qml`: a checkbox for `showTrendArrows` and a spinbox for
  `trendLookbackRefreshes` (label e.g. "Trend über N Aktualisierungen"),
  following the existing `show*` control patterns.
- `main.qml` `fetchData()` passes `--trend-lookback <K>` and
  `--refresh-interval-min <interval>` to the script (K from configuration,
  interval from `root.refreshIntervalMinutes`). Arrow rendering is gated on
  `showTrendArrows`.

### 5. i18n (DE/EN)

- Tooltip / accessible text per point, e.g.
  `i18n("Trend (last ~%1 min): %2%", window_min, pct)`.
- New config labels translated in both languages, matching existing style.

## Testing

- **Python unit tests** (pure, no network): feed synthetic `history` + current
  `points` into the trend functions and assert `up/down/flat/null` for:
  rising, falling, within-deadband (flat), warm-up (<K+1 points), stale gap
  (> 3× interval), missing ticker. Use `--state-file` pointing at a temp file
  for the load/append/save round-trip.
- **Manual QML check**: run `scripts/dev-reload.sh`, verify arrows appear next to
  values in chart and table, colors correct in light/dark theme, and that
  toggling `showTrendArrows` / changing K behaves.

## Out of scope (YAGNI)

- Multi-arrow strength (single ▲/▼ only).
- Configurable deadband / interval-of-intraday (fixed defaults).
- Historical trend charting or sparklines.
