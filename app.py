"""WhisperUI: a menu bar app that records meetings from the mic and transcribes them locally
with mlx-whisper. Run from Terminal with ./run.sh, or at login via ./install.sh."""

import contextlib
import json
import logging
import logging.handlers
import os
import queue
import signal

import rumps

import formats
import jobs
import macos
import paths
import recorder
from jobs import PENDING, RECORDING, Job, JobStore
from transcriber import DEFAULT_MODEL, MODELS, Worker, new_file_job

LANGUAGES = [("Slovak", "sk"), ("Czech", "cs"), ("English", "en"), ("Auto", None)]
DEFAULT_SETTINGS = {"language": "sk", "model": DEFAULT_MODEL, "mic": None}

log = logging.getLogger("whisper-ui")


def load_settings() -> dict:
    try:
        with open(paths.SETTINGS, encoding="utf-8") as f:
            return {**DEFAULT_SETTINGS, **json.load(f)}
    except (OSError, ValueError):
        return dict(DEFAULT_SETTINGS)


@rumps.notifications
def on_notification_click(notification):
    path = (notification.data or {}).get("path")
    if path:
        macos.open_path(path)


class WhisperApp(rumps.App):
    def __init__(self):
        super().__init__("WhisperUI", icon=paths.ICON, template=True, quit_button=None)
        self.settings = load_settings()
        self.store = JobStore(paths.JOBS)
        self.events: queue.Queue = queue.Queue()  # (kind, job, detail) from other threads -> _tick
        self.worker = Worker(self.store, paths.TRANSCRIPTS, lambda *event: self.events.put(event))
        self.recorder: recorder.Recorder | None = None
        self.rec_job: Job | None = None
        self._red_icon = False

        self.rec_item = rumps.MenuItem("Start recording", callback=self.toggle_recording)
        self.status_item = rumps.MenuItem("Transcribing…")  # no callback: shown disabled
        self.status_item.hidden = True
        self.mic_menu = rumps.MenuItem("Microphone")
        self._fill_mic_menu()
        self.menu = [
            self.rec_item,
            self.status_item,
            rumps.MenuItem("Transcribe file…", callback=self.transcribe_file),
            None,
            self._radio(rumps.MenuItem("Language"), LANGUAGES, "language"),
            self._radio(rumps.MenuItem("Model"), [(name, name) for name in MODELS], "model"),
            self.mic_menu,
            None,
            rumps.MenuItem("Open transcripts folder", callback=lambda _: macos.open_path(paths.TRANSCRIPTS)),
            rumps.MenuItem("Quit", callback=lambda _: self.quit()),
        ]

        recovered = jobs.recover(self.store)
        for job in recovered:
            self.worker.submit(job)
        if recovered:
            self.events.put(("recovered", None, len(recovered)))

        # Python runs these on the main thread at the next timer tick (<= 0.5 s).
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(sig, lambda *_: self.quit())
        self._timer = rumps.Timer(self._tick, 0.5)
        self._timer.start()

    # -- settings submenus ------------------------------------------------------------

    def _radio(self, menu, options, key):
        for label, value in options:
            item = rumps.MenuItem(label, callback=lambda _, v=value: self._choose(menu, key, v))
            item.value = value
            item.state = self.settings[key] == value
            menu.add(item)
        return menu

    def _choose(self, menu, key, value):
        self.settings[key] = value
        jobs.atomic_write(paths.SETTINGS, json.dumps(self.settings, indent=2, ensure_ascii=False))
        for item in menu.values():
            if hasattr(item, "value"):
                item.state = item.value == value

    def _fill_mic_menu(self):
        if len(self.mic_menu):  # rumps creates the submenu lazily; clear() needs it to exist
            self.mic_menu.clear()
        devices = recorder.input_devices()
        self._radio(self.mic_menu, [("System default", None)] + [(d, d) for d in devices], "mic")
        self.mic_menu.add(rumps.separator)
        self.mic_menu.add(rumps.MenuItem("Refresh devices", callback=self.refresh_mics))

    def refresh_mics(self, _):
        if self.recorder:
            rumps.alert("Stop recording first", "The device list can't be refreshed while recording.")
            return
        recorder.refresh_devices()
        self._fill_mic_menu()

    # -- recording ----------------------------------------------------------------------

    def toggle_recording(self, _=None):
        if self.recorder:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        status = macos.mic_status()
        if status == "undetermined":
            macos.request_mic(lambda granted: self.events.put(("mic", None, bool(granted))))
            return
        if status == "denied":
            self._mic_denied_alert()
            return
        job_id = jobs.unique_id([paths.JOBS, paths.RECORDINGS, paths.TRANSCRIPTS])
        audio = os.path.join(paths.RECORDINGS, f"{job_id}.wav")
        job = Job(job_id, audio, self.settings["language"], self.settings["model"], state=RECORDING)
        self.store.save(job)  # before any audio exists, so a kill from here on is recoverable
        try:
            self.recorder = recorder.Recorder(
                audio, self.settings["mic"], on_silence=lambda: self.events.put(("silence", job, None))
            )
        except Exception as e:
            log.exception("Could not start recording")
            self.store.delete(job_id)
            with contextlib.suppress(FileNotFoundError):
                os.remove(audio)
            rumps.alert("Could not start recording", str(e))
            return
        self.rec_job = job
        self._refresh()

    def stop_recording(self, transcribe: bool = True):
        rec, job = self.recorder, self.rec_job
        self.recorder = self.rec_job = None
        try:
            rec.stop()
        except Exception:
            log.exception("Error while stopping the recording")
        if rec.writer.data_size == 0:
            self.store.delete(job.id)
            with contextlib.suppress(FileNotFoundError):
                os.remove(job.audio)
        else:
            job.state = PENDING
            self.store.save(job)
            if transcribe:
                self.worker.submit(job)
        self._refresh()

    def _mic_denied_alert(self):
        if rumps.alert(
            "Microphone access is off",
            "macOS records silence without it. Allow the app that started WhisperUI "
            "(Terminal, or WhisperUI at login) under Privacy & Security → Microphone.",
            ok="Open Settings",
            cancel="Cancel",
        ):
            macos.open_mic_settings()

    # -- transcription ------------------------------------------------------------------

    def transcribe_file(self, _):
        path = macos.choose_audio_file()
        if path:
            self.worker.submit(new_file_job(self.store, path, self.settings["language"], self.settings["model"]))
            self._refresh()

    def quit(self):
        if self.recorder:
            self.stop_recording(transcribe=False)  # job stays pending; transcribed on next launch
        log.info("Quitting")
        rumps.quit_application()

    # -- main-thread UI updates ---------------------------------------------------------

    def _tick(self, _):
        while True:
            try:
                self._handle(*self.events.get_nowait())
            except queue.Empty:
                break
        if self.recorder and not self.recorder.active:
            log.warning("Input stream stopped unexpectedly")
            self.stop_recording()
            self._notify("Recording stopped", "The microphone went away. What was recorded is being transcribed.")
        self._refresh()

    def _handle(self, kind, job, detail):
        if kind == "done":
            with open(detail, encoding="utf-8") as f:
                text = " ".join(line.split("] ", 1)[-1] for line in f.read().splitlines())
            self._notify("Transcription done", text[:200] or "No speech detected", path=detail)
        elif kind == "failed":
            self._notify("Transcription failed", f"{job.id}: {detail}")
        elif kind == "mic":
            if detail:
                self.start_recording()
            else:
                self._mic_denied_alert()
        elif kind == "silence":
            self._notify(
                "Microphone is silent",
                "No sound in the first seconds. Check the selected mic and its permission. Recording continues.",
            )
        elif kind == "recovered":
            self._notify("Resuming interrupted work", f"{detail} job(s) queued for transcription")

    def _notify(self, title, message, path=None):
        rumps.notification(title, "", message, data={"path": path} if path else None)

    def _refresh(self):
        if self.recorder:
            self.rec_item.title = f"Stop recording ({formats.hms(self.recorder.writer.duration)})"
        else:
            self.rec_item.title = "Start recording"
        busy = self.worker.current is not None
        self.status_item.hidden = not busy
        if busy:
            queued = self.worker.queued
            self.status_item.title = f"Transcribing… {self.worker.progress:.0%}" + (
                f" (+{queued} queued)" if queued else ""
            )
        self._set_recording_icon(self.recorder is not None)

    def _set_recording_icon(self, recording: bool):
        # contentTintColor doesn't render on status bar buttons, so swap in a red copy instead
        if recording != self._red_icon:
            self.template = not recording  # must be set before icon, which applies it
            self.icon = paths.ICON_RECORDING if recording else paths.ICON
            self._red_icon = recording


def setup_logging():
    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(paths.LOGS, "app.log"), maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[file_handler, logging.StreamHandler()],
    )


if __name__ == "__main__":
    setup_logging()
    WhisperApp().run()
