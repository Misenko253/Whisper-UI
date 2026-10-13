#!/bin/bash
# Start WhisperUI at login (and restart it after a crash) via a LaunchAgent.
set -euo pipefail
cd "$(dirname "$0")"
LABEL=local.whisper-ui
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

[ -x build/WhisperUI.app/Contents/MacOS/WhisperUI ] || { echo "Run ./setup.sh first."; exit 1; }
mkdir -p logs "$(dirname "$PLIST")"
sed "s|__APP_DIR__|$PWD|g" launcher/launchagent.plist.template > "$PLIST"
plutil -lint -s "$PLIST"
launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$PLIST"
echo "Installed $PLIST. WhisperUI is starting; quit any copy running from Terminal."
