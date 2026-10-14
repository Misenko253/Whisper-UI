# WhisperUI

A macOS menu bar app (Apple Silicon) that records meetings from the mic and transcribes them
locally with [mlx-whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper).

## Setup

```bash
./setup.sh      # checks brew ffmpeg, creates .venv (Python 3.12), builds build/WhisperUI.app
./run.sh        # start from Terminal
./install.sh    # or: start at login (LaunchAgent local.whisper-ui); ./uninstall.sh removes it
```

The first transcription with a model downloads it from Hugging Face
(large-v3 ≈ 3 GB, large-v3-turbo ≈ 1.6 GB).

## Use

Menu: Start/Stop recording · Transcribe file… · Language (Slovak default, Czech, English, Auto) ·
Model · Microphone · Open transcripts folder · Quit. The icon turns red while recording.

- Recordings: `recordings/<datetime>.wav` (16 kHz mono)
- Transcripts: `transcripts/<datetime>.txt` (`[hh:mm:ss] text`) and `.srt`
- A notification appears when a transcript is done; click it to open the `.txt`.
- Headless: `.venv/bin/python -m transcriber file.m4a --language sk`
- Logs: `logs/app.log` (and `logs/launchd.log` when started at login)

## Microphone permission

macOS doesn't fail when the mic is blocked, it records silence. So the app checks permission
before recording and warns if the first seconds are silent.

- From Terminal, the prompt is for **Terminal**.
- At login, the prompt is for **WhisperUI**, the small launcher app in `build/`. Homebrew's
  Python can't ask for the mic itself (its Info.plist has no mic usage text).

If you denied it: System Settings → Privacy & Security → Microphone.

## Nothing gets lost

- Audio is written to the WAV as it arrives, and its header is updated every second. A
  `kill -9` loses at most the last second.
- Every recording or file to transcribe is a job file in `jobs/`. It's removed only after the
  transcript is written. On the next start, the app repairs interrupted recordings and
  re-runs unfinished jobs. A transcription cut off partway restarts from the beginning.
- Quit or logout while recording closes the file cleanly. The transcription then runs on the
  next start.
- Failed jobs stay in `jobs/` with the error and aren't retried automatically.

## Tests

```bash
.venv/bin/pytest
```

## License

[PolyForm Internal Use 1.0.0](LICENSE.md): free to use for the internal business operations
of you and your company. Distributing it is not allowed.
