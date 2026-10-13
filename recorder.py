"""Mic capture: the PortAudio callback only queues raw blocks; a writer thread appends them
to a crash-safe WAV, so slow disk I/O never drops audio."""

import logging
import queue
import threading

import numpy as np
import sounddevice as sd

from wavio import WavWriter

TARGET_RATE = 16000  # what Whisper uses; CoreAudio resamples for us
SILENCE_CHECK_SECONDS = 3

log = logging.getLogger(__name__)


def input_devices() -> list[str]:
    return [d["name"] for d in sd.query_devices() if d["max_input_channels"] > 0]


def refresh_devices() -> None:
    """PortAudio caches the device list at init; re-init to see plugged/unplugged mics."""
    sd._terminate()
    sd._initialize()


def _device_index(name: str | None) -> int | None:
    if name is not None:
        for i, d in enumerate(sd.query_devices()):
            if d["name"] == name and d["max_input_channels"] > 0:
                return i
        log.warning("Microphone %r not found, using the system default", name)
    return None


class Recorder:
    def __init__(self, path, device_name: str | None = None, on_silence=None):
        self._queue: queue.Queue[bytes | None] = queue.Queue()
        self._on_silence = on_silence
        self._heard_sound = False
        self._frames_checked = 0
        device = _device_index(device_name)
        try:
            sd.check_input_settings(device, channels=1, dtype="int16", samplerate=TARGET_RATE)
            rate = TARGET_RATE
        except sd.PortAudioError:
            rate = None  # device default; ffmpeg resamples when transcribing
        self.stream = sd.InputStream(
            device=device, channels=1, dtype="int16", samplerate=rate, callback=self._callback
        )
        self.writer = WavWriter(path, int(self.stream.samplerate))
        self._thread = threading.Thread(target=self._drain, name="wav-writer", daemon=True)
        self._thread.start()
        self.stream.start()
        log.info("Recording to %s at %d Hz from %s", path, self.stream.samplerate, device_name or "default mic")

    @property
    def active(self) -> bool:
        return self.stream.active

    def _callback(self, indata, frames, time_info, status):
        if status:
            log.warning("Audio input status: %s", status)
        self._queue.put(bytes(indata))

    def _drain(self):
        while (chunk := self._queue.get()) is not None:
            self.writer.write(chunk)
            self._check_silence(chunk)

    def _check_silence(self, chunk: bytes):
        if self._heard_sound or self._frames_checked is None:
            return
        self._heard_sound = bool(np.frombuffer(chunk, np.int16).any())
        self._frames_checked += len(chunk) // 2
        if not self._heard_sound and self._frames_checked >= SILENCE_CHECK_SECONDS * self.writer.sample_rate:
            self._frames_checked = None  # warn once
            if self._on_silence:
                self._on_silence()

    def stop(self) -> None:
        try:
            self.stream.stop()
            self.stream.close()
        finally:
            self._queue.put(None)
            self._thread.join()
            self.writer.close()
        log.info("Recording stopped after %.1f s", self.writer.duration)
