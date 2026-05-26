# VIX Term Structure Plasmoid

A KDE Plasma 6 widget that displays the VIX cash term structure curve directly on your desktop, updated periodically from Yahoo Finance.

## What it shows

The widget fetches and displays the latest values for five VIX futures maturities:

| Ticker   | Label | Maturity  |
|----------|-------|-----------|
| `^VIX9D` | 9D    | 9 days    |
| `^VIX`   | 30D   | 30 days   |
| `^VIX3M` | 3M    | 3 months  |
| `^VIX6M` | 6M    | 6 months  |
| `^VIX1Y` | 1Y    | 1 year    |

It plots a line chart of the term structure and classifies the curve as Contango, Backwardation, Flat, or Unknown based on a simple heuristic (see below). This is a visual tool only — **not a trading signal**.

<img width="599" height="349" alt="image" src="https://github.com/user-attachments/assets/ca183a2a-f029-4e3d-8828-9889633bde2e" />

## Requirements

- KDE Plasma 6
- Python 3.9+
- `yfinance` and `pandas` Python packages

## Installation

### 1. Install Python dependencies

System packages (recommended):
```bash
pip install --user yfinance pandas
```

Or in a virtual environment:
```bash
python3 -m venv ~/.local/share/vix-term-structure-plasmoid/venv
source ~/.local/share/vix-term-structure-plasmoid/venv/bin/activate
pip install yfinance pandas
```

If using a venv, edit `package/contents/code/fetch_vix.py` to use the venv Python, or create a wrapper script.

### 2. Install the plasmoid

```bash
scripts/install.sh
```

Or manually:
```bash
kpackagetool6 --type Plasma/Applet --install package
```

### 3. Add to desktop or panel

Right-click the desktop → Add Widgets → search "VIX Term Structure".

## Development / upgrade

```bash
scripts/upgrade.sh
```

Or launch directly for testing:
```bash
scripts/dev-reload.sh
# or
plasmoidviewer -a package -l floating -f planar
```

## Uninstall

```bash
scripts/uninstall.sh
```

Or:
```bash
kpackagetool6 --type Plasma/Applet --remove com.chrisotm.vixtermstructure
```

## Configuration

Open the widget settings to configure:

| Setting                  | Default | Range  | Description                        |
|--------------------------|---------|--------|------------------------------------|
| Refresh interval (min)   | 15      | 1–1440 | How often to fetch new data        |
| Show values on chart     | true    | —      | Display value labels on each point |
| Show table               | true    | —      | Show the value table below chart   |

## Curve classification

The curve state is a **heuristic indicator only**, not a trading signal:

- **Backwardation** — `9D > 30D` or `30D > 3M` (short-term stress)
- **Flat** — `|30D − 3M| < 0.5`
- **Contango** — otherwise (normal upward slope)
- **Unknown** — insufficient data to classify

## Known limitations

- Data is only available during market hours and recent sessions. Values shown are the most recent available close.
- The widget will show the last known values when a refresh fails, with an error indicator.
- If `yfinance` or Python is not installed, the widget shows an error message.
- Refresh timer pauses when the widget is not visible, resuming with an immediate refresh when it becomes visible again.

## Data disclaimer

> Data is provided through `yfinance` and Yahoo Finance public endpoints.
> `yfinance` is not affiliated with, endorsed by, or vetted by Yahoo.
> This tool is for **informational and educational use only**.
> Refer to Yahoo Finance Terms of Service before any production or commercial use.
> VIX data is published by CBOE; this widget fetches it indirectly via Yahoo Finance.

## Technical risk: Plasma5Support

This plasmoid uses `org.kde.plasma.plasma5support` (`Plasma5Support.DataSource` with the `executable` engine) to run the local Python fetcher script from QML. This is a Plasma 6 **compatibility module** and may need replacement in a future Plasma version. If the widget stops working after a Plasma upgrade, check whether `Plasma5Support` is still available.

A future version (v0.2+) should replace this with a local D-Bus helper or native extension for long-term stability.

## License

MIT
