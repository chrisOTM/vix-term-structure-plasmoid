# VIX Spot Trend Indicator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a colored trend arrow (▲ red rising / ▼ green falling / → grey flat) next to each VIX maturity value, derived from the widget's own refresh history.

**Architecture:** A dependency-free Python module `trend.py` persists a rolling per-ticker history (one point per refresh) in a JSON state file, and computes direction by comparing the latest value against the value K refreshes back. `fetch_vix.py` calls it and attaches `trend`/`trend_pct`/`trend_window_min` to each point. QML (`ChartView.qml`, `main.qml`) renders the arrow; config exposes an on/off toggle and K.

**Tech Stack:** Python 3.9+ (stdlib only for trend logic), pytest for tests, KDE Plasma 6 QML (QtQuick Canvas + Kirigami).

## Global Constraints

- Python floor: 3.9+ (`zoneinfo` used elsewhere in `fetch_vix.py`). Trend logic uses **stdlib only** — no pandas/yfinance imports in `trend.py`.
- No breaking change to existing JSON output; new CLI args must all have defaults.
- Trend defaults (verbatim): lookback K default `3` (min `1`), deadband `0.5` %, staleness guard `3 × refreshIntervalMinutes`, history cap `32` points/ticker.
- Color mapping: up → `Kirigami.Theme.negativeTextColor`, down → `Kirigami.Theme.positiveTextColor`, flat → `Kirigami.Theme.disabledTextColor`.
- Glyphs: up `▲`, down `▼`, flat `→`.
- State file default: `${XDG_CACHE_HOME:-~/.cache}/vix-term-structure/history.json`.
- All user-facing strings via `i18n(...)`, DE/EN (project is bilingual).
- Follow existing patterns; commit frequently.

---

### Task 1: Trend core module (`trend.py`) — pure functions + tests

**Files:**
- Create: `package/contents/code/trend.py`
- Test: `tests/test_trend.py`

**Interfaces:**
- Consumes: nothing (stdlib only).
- Produces:
  - `default_state_path() -> str`
  - `load_history(path: str) -> dict`  (returns `{}` on missing/corrupt)
  - `append_and_trim(history: dict, points: list, ts: str, cap: int = 32) -> dict`
  - `save_history(path: str, history: dict) -> None`  (atomic, non-fatal on error)
  - `compute_trend(series: list, k: int, deadband_pct: float, max_gap_min: float) -> tuple`
    returning `(direction, pct, window_min)` where `direction ∈ {"up","down","flat",None}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_trend.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_trend.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'trend'`

- [ ] **Step 3: Write `trend.py`**

Create `package/contents/code/trend.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_trend.py -q`
Expected: PASS (all tests green)

- [ ] **Step 5: Commit**

```bash
git add package/contents/code/trend.py tests/test_trend.py
git commit -m "feat: add stdlib trend-detection core module with tests"
```

---

### Task 2: Orchestrator `enrich_points_with_trend` + wire into `fetch_vix.py`

**Files:**
- Modify: `package/contents/code/trend.py` (add orchestrator)
- Modify: `package/contents/code/fetch_vix.py` (import, CLI args, call)
- Test: `tests/test_trend.py` (add orchestrator tests)

**Interfaces:**
- Consumes: `load_history`, `append_and_trim`, `save_history`, `compute_trend`, `default_state_path` (Task 1).
- Produces:
  - `enrich_points_with_trend(points, state_path, k, deadband_pct, refresh_interval_min, now_ts, cap=32) -> list`
    — mutates each point in `points`, adding keys `trend` (`"up"|"down"|"flat"|None`), `trend_pct` (`float|None`), `trend_window_min` (`int|None`); returns the same list. Never raises.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_trend.py`:

```python
def test_enrich_warmup_then_up(tmp_path):
    path = str(tmp_path / "h.json")
    pts1 = [{"ticker": "^VIX", "label": "30D", "value": 16.0}]
    trend.enrich_points_with_trend(pts1, path, k=1, deadband_pct=0.5,
                                   refresh_interval_min=15,
                                   now_ts="2026-07-08T15:00:00+02:00")
    assert pts1[0]["trend"] is None  # warm-up, only 1 point stored

    pts2 = [{"ticker": "^VIX", "label": "30D", "value": 17.0}]
    trend.enrich_points_with_trend(pts2, path, k=1, deadband_pct=0.5,
                                   refresh_interval_min=15,
                                   now_ts="2026-07-08T15:15:00+02:00")
    assert pts2[0]["trend"] == "up"
    assert pts2[0]["trend_pct"] == 6.25
    assert pts2[0]["trend_window_min"] == 15


def test_enrich_never_raises_on_bad_path():
    pts = [{"ticker": "^VIX", "value": 16.0}]
    # Unwritable/invalid directory path must not raise; trend stays None.
    trend.enrich_points_with_trend(pts, "/proc/nonexistent/h.json", k=1,
                                   deadband_pct=0.5, refresh_interval_min=15,
                                   now_ts="2026-07-08T15:00:00+02:00")
    assert pts[0]["trend"] is None
    assert pts[0]["trend_pct"] is None
    assert pts[0]["trend_window_min"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_trend.py -q`
Expected: FAIL — `AttributeError: module 'trend' has no attribute 'enrich_points_with_trend'`

- [ ] **Step 3: Add the orchestrator to `trend.py`**

Append to `package/contents/code/trend.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_trend.py -q`
Expected: PASS

- [ ] **Step 5: Wire into `fetch_vix.py` — import + CLI args**

In `package/contents/code/fetch_vix.py`, add the import near the top (after the stdlib imports, before/after the yfinance try-block — `trend` has no heavy deps so import it unconditionally at the top):

```python
import trend
```

In `parse_args()` add the new arguments (keep existing ones):

```python
    parser.add_argument("--trend-lookback",      type=int,   default=3)
    parser.add_argument("--trend-deadband-pct",  type=float, default=0.5)
    parser.add_argument("--refresh-interval-min", type=float, default=15)
    parser.add_argument("--state-file",          default=trend.default_state_path())
```

- [ ] **Step 6: Wire into `fetch_vix.py` — call enrichment in `main()`**

In `main()`, after the status is determined and **before** `print(json.dumps(build_result(...)))`, insert:

```python
    if points:
        trend.enrich_points_with_trend(
            points,
            args.state_file,
            args.trend_lookback,
            args.trend_deadband_pct,
            args.refresh_interval_min,
            now_iso(),
        )
```

- [ ] **Step 7: Verify the script still runs and emits trend fields**

Run (two calls, isolated state file, uses network):
```bash
T=$(mktemp -d)
python3 package/contents/code/fetch_vix.py --state-file "$T/h.json" --trend-lookback 1 | python3 -c "import sys,json;d=json.load(sys.stdin);print('run1 trend:',[p.get('trend') for p in d['points']])"
python3 package/contents/code/fetch_vix.py --state-file "$T/h.json" --trend-lookback 1 | python3 -c "import sys,json;d=json.load(sys.stdin);print('run2 keys:',sorted(set(k for p in d['points'] for k in ('trend','trend_pct','trend_window_min') if k in p)))"
```
Expected: run1 prints `run1 trend: [None, None, None, None, None]` (warm-up); run2 prints `run2 keys: ['trend', 'trend_pct', 'trend_window_min']`.

- [ ] **Step 8: Run full python test suite**

Run: `python3 -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add package/contents/code/trend.py package/contents/code/fetch_vix.py tests/test_trend.py
git commit -m "feat: enrich fetch output with per-ticker refresh-based trend"
```

---

### Task 3: Config schema + config dialog controls

**Files:**
- Modify: `package/contents/config/main.xml`
- Modify: `package/contents/ui/configGeneral.qml`

**Interfaces:**
- Consumes: nothing.
- Produces: config keys `showTrendArrows` (Bool, default true) and `trendLookbackRefreshes` (Int, default 3, min 1), consumed by Tasks 4 & 5.

- [ ] **Step 1: Add config entries to `main.xml`**

Inside `<group name="General">`, after the `showPercentiles` entry, add:

```xml
    <entry name="showTrendArrows" type="Bool">
      <default>true</default>
    </entry>
    <entry name="trendLookbackRefreshes" type="Int">
      <default>3</default>
      <min>1</min>
    </entry>
```

- [ ] **Step 2: Add property aliases + controls to `configGeneral.qml`**

Add the aliases to the `property alias` block at the top of the `Kirigami.FormLayout`:

```qml
    property alias cfg_showTrendArrows: showTrendArrows.checked
    property alias cfg_trendLookbackRefreshes: trendLookback.value
```

After the `showPercentiles` CheckBox, add:

```qml
    QQC2.CheckBox {
        id: showTrendArrows
        text: i18n("Show trend arrows")
        checked: true
    }

    QQC2.SpinBox {
        id: trendLookback
        Kirigami.FormData.label: i18n("Trend over N refreshes:")
        from: 1
        to: 30
        value: 3
        enabled: showTrendArrows.checked
    }
```

- [ ] **Step 3: Verify XML is well-formed**

Run: `python3 -c "import xml.dom.minidom;xml.dom.minidom.parse('package/contents/config/main.xml');print('xml ok')"`
Expected: `xml ok`

- [ ] **Step 4: Commit**

```bash
git add package/contents/config/main.xml package/contents/ui/configGeneral.qml
git commit -m "feat: add trend-arrow config toggle and lookback setting"
```

---

### Task 4: Pass CLI args + render trend arrow in the value table (`main.qml`)

**Files:**
- Modify: `package/contents/ui/main.qml` (fetch command ~line 363-366; table header ~line 164-170; data delegate ~line 210-214; add root helper functions)

**Interfaces:**
- Consumes: config keys from Task 3; `point.trend` / `trend_pct` / `trend_window_min` from Task 2.
- Produces: root JS helpers `trendGlyph(dir) -> string` and `trendColor(dir) -> color`, reused by the table here and referenced conceptually by Task 5 (ChartView defines its own copy since Canvas JS is separate scope).

- [ ] **Step 1: Add helper functions to `root`**

In `main.qml`, inside the root item (near the other `function` definitions such as `formatErrors`), add:

```qml
    function trendGlyph(dir) {
        if (dir === "up")   return "▲"
        if (dir === "down") return "▼"
        if (dir === "flat") return "→"
        return ""
    }

    function trendColor(dir) {
        if (dir === "up")   return Kirigami.Theme.negativeTextColor
        if (dir === "down") return Kirigami.Theme.positiveTextColor
        return Kirigami.Theme.disabledTextColor
    }
```

- [ ] **Step 2: Pass the new CLI args in `fetchData()`**

Replace the command-building line in `fetchData()`:

```qml
        var command   = quoteShell(script) + " --timeout 10"
```

with:

```qml
        var command   = quoteShell(script) + " --timeout 10"
            + " --trend-lookback " + Math.max(1, plasmoid.configuration.trendLookbackRefreshes)
            + " --refresh-interval-min " + root.refreshIntervalMinutes
```

- [ ] **Step 3: Add a "Trend" header column**

In the table header `RowLayout`, after the `Value` header Label (the one with `text: i18n("Value")`), add:

```qml
                    PlasmaComponents3.Label {
                        text: i18n("Trend")
                        font.bold: true
                        font.pointSize: Kirigami.Theme.smallFont.pointSize
                        color: Kirigami.Theme.disabledTextColor
                        Layout.preferredWidth: Kirigami.Units.gridUnit * 2
                        visible: plasmoid.configuration.showTrendArrows !== false
                    }
```

- [ ] **Step 4: Add the trend glyph to each data row**

In the data-row `delegate: RowLayout`, after the `Value` Label (`text: modelData.value.toFixed(2)`), add:

```qml
                        PlasmaComponents3.Label {
                            text: root.trendGlyph(modelData.trend)
                            color: root.trendColor(modelData.trend)
                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                            Layout.preferredWidth: Kirigami.Units.gridUnit * 2
                            horizontalAlignment: Text.AlignHCenter
                            visible: plasmoid.configuration.showTrendArrows !== false
                                     && modelData.trend !== undefined && modelData.trend !== null

                            QQC2.ToolTip.visible: hovered.hovered
                            QQC2.ToolTip.text: modelData.trend_pct !== undefined
                                && modelData.trend_pct !== null
                                ? i18n("Trend (last ~%1 min): %2%",
                                       modelData.trend_window_min,
                                       modelData.trend_pct.toFixed(2))
                                : ""

                            HoverHandler { id: hovered }
                        }
```

- [ ] **Step 5: Reload the widget and verify the table**

Run: `bash scripts/dev-reload.sh`
Expected: widget reloads. On the **second** refresh (after the lookback window fills — force a quick check by setting refresh interval to 1 min in config), a colored arrow appears in the new **Trend** column next to each value; hovering shows the tooltip. First load after install shows no arrow (warm-up) — this is correct.

- [ ] **Step 6: Commit**

```bash
git add package/contents/ui/main.qml
git commit -m "feat: pass trend args and show trend arrows in value table"
```

---

### Task 5: Render trend arrow next to values on the chart (`ChartView.qml`)

**Files:**
- Modify: `package/contents/ui/ChartView.qml`

**Interfaces:**
- Consumes: `points[j].trend` from Task 2; new property `showTrendArrows` set by `main.qml`.
- Produces: nothing downstream.

- [ ] **Step 1: Add the `showTrendArrows` property and wire it from `main.qml`**

In `ChartView.qml`, add near the other properties:

```qml
    property bool showTrendArrows: true

    onShowTrendArrowsChanged: requestPaint()
```

In `main.qml`, on the `ChartView { ... }` instance (after `showValues: plasmoid.configuration.showValuesOnChart`), add:

```qml
                showTrendArrows: plasmoid.configuration.showTrendArrows
```

- [ ] **Step 2: Add glyph/color helpers inside the Canvas**

In `ChartView.qml`, add two JavaScript functions inside the `Canvas` (e.g. just above `onPaint`):

```qml
    function _trendGlyph(dir) {
        if (dir === "up")   return "▲"
        if (dir === "down") return "▼"
        if (dir === "flat") return "→"
        return ""
    }

    function _trendColor(dir) {
        if (dir === "up")   return Kirigami.Theme.negativeTextColor
        if (dir === "down") return Kirigami.Theme.positiveTextColor
        return Kirigami.Theme.disabledTextColor
    }
```

- [ ] **Step 3: Draw the glyph next to each value label**

In `onPaint`, inside the `for (var j ...)` loop, the value is drawn by this existing block:

```qml
            // Value near point
            if (showValues) {
                ctx.fillStyle = Kirigami.Theme.textColor
                ctx.textBaseline = "bottom"
                ctx.fillText(points[j].value.toFixed(1), px, py - dotR - Kirigami.Units.smallSpacing)
            }
```

Replace it with:

```qml
            // Value near point (+ optional trend arrow to its right)
            if (showValues) {
                var valText = points[j].value.toFixed(1)
                var valY = py - dotR - Kirigami.Units.smallSpacing
                ctx.fillStyle = Kirigami.Theme.textColor
                ctx.textAlign = "center"
                ctx.textBaseline = "bottom"
                ctx.fillText(valText, px, valY)

                var tdir = points[j].trend
                if (showTrendArrows && tdir !== undefined && tdir !== null && tdir !== "") {
                    var valHalf = ctx.measureText(valText).width / 2
                    ctx.fillStyle = _trendColor(tdir)
                    ctx.textAlign = "left"
                    ctx.fillText(_trendGlyph(tdir),
                                 px + valHalf + Kirigami.Units.smallSpacing,
                                 valY)
                }
            }
```

- [ ] **Step 4: Reload and verify the chart**

Run: `bash scripts/dev-reload.sh`
Expected: after the warm-up window fills, each chart value shows a small colored arrow to its right (▲ red rising, ▼ green falling, → grey flat), correct in both light and dark theme. Toggling **Show trend arrows** off removes them from chart and table.

- [ ] **Step 5: Commit**

```bash
git add package/contents/ui/ChartView.qml package/contents/ui/main.qml
git commit -m "feat: draw trend arrows next to chart values"
```

---

## Self-Review

- **Spec coverage:** state-file history (T1), trend formula + edge cases warm-up/stale/flat/zero (T1 tests + compute_trend), graceful fallback + CLI args + point fields (T2), config toggle + K (T3), chart arrow (T5), table arrow (T4), i18n tooltip + labels (T3/T4). All spec sections mapped.
- **Placeholders:** none — every code step is complete.
- **Type consistency:** `trend`/`trend_pct`/`trend_window_min` names identical across Python (T1/T2) and QML (T4/T5); `trendGlyph`/`trendColor` (main.qml) vs `_trendGlyph`/`_trendColor` (ChartView Canvas scope) intentionally separate copies (Canvas JS cannot see root functions) — documented in T4 interfaces.
- **Note:** `HoverHandler`/`QQC2.ToolTip` in T4 assume `QQC2` is already imported in `main.qml` (it is — used for the refresh ToolTip at line ~122). No new imports needed.

## Execution options

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks.
2. **Inline Execution** — execute here with checkpoints.
