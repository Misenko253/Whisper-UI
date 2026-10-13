#!/bin/bash
# Start WhisperUI. From Terminal, macOS asks for mic permission on Terminal's behalf;
# at login it's started via WhisperUI.app (see install.sh).
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:$PATH"  # mlx-whisper shells out to ffmpeg; launchd's PATH lacks brew
exec .venv/bin/python app.py "$@"
