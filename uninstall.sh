#!/bin/bash
# Stop WhisperUI and remove its LaunchAgent. Recordings and transcripts stay where they are.
set -euo pipefail
LABEL=local.whisper-ui
launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "Uninstalled $LABEL."
