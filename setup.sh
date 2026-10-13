#!/bin/bash
# One-time setup: check ffmpeg, create the venv, install deps, build WhisperUI.app.
set -euo pipefail
cd "$(dirname "$0")"

if brew list --versions ffmpeg >/dev/null 2>&1; then
    echo "ffmpeg: $(brew list --versions ffmpeg)"
else
    echo "ffmpeg is not installed via Homebrew, installing it…"
    brew install ffmpeg
fi

PYTHON=${PYTHON:-/opt/homebrew/bin/python3.12}
[ -d .venv ] || "$PYTHON" -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

# WhisperUI.app lets the LaunchAgent get mic permission (see launcher/main.c).
APP=build/WhisperUI.app
mkdir -p "$APP/Contents/MacOS"
cp launcher/Info.plist "$APP/Contents/Info.plist"
clang -O2 -Wall -o "$APP/Contents/MacOS/WhisperUI" launcher/main.c
codesign --force --sign - "$APP"

echo "Setup done. Start it with ./run.sh, or ./install.sh to start it at login."
