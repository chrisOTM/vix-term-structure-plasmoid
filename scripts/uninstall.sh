#!/usr/bin/env bash
set -euo pipefail

PLUGIN_ID="com.chrisotm.vixtermstructure"

echo "Uninstalling VIX Term Structure plasmoid ($PLUGIN_ID)..."
kpackagetool6 --type Plasma/Applet --remove "$PLUGIN_ID"
echo "Done."
