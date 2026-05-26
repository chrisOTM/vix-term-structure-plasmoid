# Architecture

## Overview

```
KDE Plasma Shell
   │
   │ loads package/
   ▼
PlasmoidItem (main.qml)          ← QML: UI, state, timer, JSON parsing
   │
   │ Plasma5Support.DataSource (executable engine)
   │ python3 package/contents/code/fetch_vix.py --timeout 10
   ▼
fetch_vix.py                      ← Python: data fetching, validation, JSON output
   │
   │ yfinance.download()
   ▼
Yahoo Finance public endpoints    ← External: ^VIX9D, ^VIX, ^VIX3M, ^VIX6M, ^VIX1Y
   │
   │ stdout: JSON only
   │ stderr: debug / errors
   ▼
handleFetcherOutput() in main.qml ← parse, update state, keep last-good values
   │
   ▼
ChartView.qml (Canvas)            ← renders line chart
StatusBar.qml                     ← renders status / last-update / interval
```

## Package structure

```
package/
├── metadata.json                 Plasma 6 package descriptor
└── contents/
    ├── ui/
    │   ├── main.qml              PlasmoidItem root; all state and logic
    │   ├── ChartView.qml         Canvas-based line chart component
    │   ├── StatusBar.qml         Status / update / interval row
    │   └── configGeneral.qml     Settings page (QQC2 + Kirigami only)
    ├── config/
    │   ├── config.qml            Registers configGeneral.qml as a ConfigCategory
    │   └── main.xml              KCfg schema (refreshIntervalMinutes, showValuesOnChart, showTable)
    └── code/
        └── fetch_vix.py          Python fetcher; stdout = JSON, stderr = logs
```

## Component responsibilities

### main.qml

- Root `PlasmoidItem` with `compactRepresentation` and `fullRepresentation`
- Owns all widget state: `points`, `lastSuccessfulPoints`, `status`, `curveState`, `errorMessage`, `lastUpdate`, `lastSuccessfulUpdate`, `isRefreshing`
- Manages `refreshTimer` (active only when `root.visible`)
- Triggers immediate fetch on `Component.onCompleted` and on `onExpandedChanged`
- Reacts to configuration changes without requiring Plasma restart
- Shell-quotes the Python script path via `quoteShell()` to handle spaces

### ChartView.qml

- Pure Canvas rendering: no external chart library needed
- Accepts `points` (array) and `showValues` (bool)
- Auto-scales Y axis with 10 % padding; minimum range 1.0
- Uses `Kirigami.Theme.*` colors — no hardcoded colors
- Uses `PlasmaCore.Units` for all sizes and spacing
- Repaints via `requestPaint()` on data or size changes

### StatusBar.qml

- Displays status string (OK / Partial / Error / Loading / Refreshing)
- Status color from `Kirigami.Theme.*` (positive / neutral / negative / disabled)
- Shows last successful update timestamp and refresh interval

### fetch_vix.py

- Called as subprocess: `python3 fetch_vix.py --timeout 10`
- Handles `yfinance` MultiIndex column output
- Handles missing `Close` columns, empty DataFrames, non-finite values
- Each ticker is fetched independently — one failure → `partial` status
- Exit code always 0; stdout always valid JSON

## Data flow

```
Component.onCompleted
    └─ fetchData()
            └─ executable.connectSource("python3 '...' --timeout 10")
                    └─ [subprocess executes fetch_vix.py]
                            └─ stdout JSON → onNewData
                                    └─ handleFetcherOutput()
                                            ├─ update points / status
                                            └─ keep lastSuccessfulPoints on failure
```

## Configuration model

`contents/config/main.xml` defines the KCfg schema. Each `<entry>` maps to a `cfg_<name>` property alias in `configGeneral.qml`. Plasma handles persistence and the Apply/Discard flow.

| Entry                  | Type | Default | Min |
|------------------------|------|---------|-----|
| refreshIntervalMinutes | Int  | 15      | 1   |
| showValuesOnChart      | Bool | true    | —   |
| showTable              | Bool | true    | —   |

## Known constraints and risks

| Risk | Mitigation |
|------|------------|
| `Plasma5Support` is a compatibility module and may be removed | Documented in README; v0.2+ should use D-Bus helper |
| `yfinance` / Yahoo API changes | Error state + last-good values retained; documented |
| Python not installed | Handled in fetch_vix.py import guard; error JSON emitted |
| Subprocess path with spaces | `quoteShell()` in main.qml |
| Timer firing when widget hidden | `running: root.visible` |
