#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR="$SCRIPT_DIR/../package"
PLUGIN_ID="com.chrisotm.vixtermstructure"

echo "Reloading plasmoid for development..."

# Upgrade (install if not present, upgrade if present)
if kpackagetool6 --type Plasma/Applet --list 2>/dev/null | grep -q "$PLUGIN_ID"; then
    kpackagetool6 --type Plasma/Applet --upgrade "$PACKAGE_DIR"
else
    kpackagetool6 --type Plasma/Applet --install "$PACKAGE_DIR"
fi

echo "Launching plasmoidviewer..."
exec plasmoidviewer -a "$PACKAGE_DIR" -l floating -f planar
