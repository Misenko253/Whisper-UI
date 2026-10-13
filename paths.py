"""Where everything lives: next to the code, independent of the current directory."""

import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
RECORDINGS = os.path.join(APP_DIR, "recordings")
TRANSCRIPTS = os.path.join(APP_DIR, "transcripts")
JOBS = os.path.join(APP_DIR, "jobs")
LOGS = os.path.join(APP_DIR, "logs")
SETTINGS = os.path.join(APP_DIR, "settings.json")
ICON = os.path.join(APP_DIR, "assets", "icon.svg")  # template: macOS adapts it to light/dark
ICON_RECORDING = os.path.join(APP_DIR, "assets", "icon-recording.svg")  # fixed red

for _d in (RECORDINGS, TRANSCRIPTS, JOBS, LOGS):
    os.makedirs(_d, exist_ok=True)
