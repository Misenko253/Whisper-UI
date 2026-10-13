"""Crash-safe WAV files.

WavWriter keeps the header's size fields current while recording (rewritten and fsynced
about once a second), so a killed process leaves a playable file missing at most the last
second. repair() fixes a header left stale by a kill, using the actual file size.
"""

import os
import struct
import time

HEADER_SIZE = 44


def _header(data_size: int, sample_rate: int, channels: int, sampwidth: int) -> bytes:
    block_align = channels * sampwidth
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_size, b"WAVE",
        b"fmt ", 16, 1, channels, sample_rate, sample_rate * block_align, block_align, sampwidth * 8,
        b"data", data_size,
    )


class WavWriter:
    def __init__(self, path, sample_rate: int, channels: int = 1, sampwidth: int = 2, sync_interval: float = 1.0):
        self.sample_rate, self.channels, self.sampwidth = sample_rate, channels, sampwidth
        self.sync_interval = sync_interval
        self.data_size = 0
        self._f = open(path, "wb")
        self._f.write(_header(0, sample_rate, channels, sampwidth))
        self.sync()

    @property
    def duration(self) -> float:
        return self.data_size / (self.sample_rate * self.channels * self.sampwidth)

    def write(self, pcm: bytes) -> None:
        self._f.write(pcm)
        self.data_size += len(pcm)
        if time.monotonic() - self._last_sync >= self.sync_interval:
            self.sync()

    def sync(self) -> None:
        self._f.seek(0)
        self._f.write(_header(self.data_size, self.sample_rate, self.channels, self.sampwidth))
        self._f.seek(0, os.SEEK_END)
        self._f.flush()
        os.fsync(self._f.fileno())
        self._last_sync = time.monotonic()

    def close(self) -> None:
        if not self._f.closed:
            self.sync()
            self._f.close()


def repair(path) -> bool:
    """Make the header match the audio actually on disk. Returns True if the file changed."""
    size = os.path.getsize(path)
    if size < HEADER_SIZE:
        return False
    with open(path, "r+b") as f:
        head = f.read(HEADER_SIZE)
        if head[0:4] != b"RIFF" or head[8:12] != b"WAVE" or head[36:40] != b"data":
            return False
        block_align = struct.unpack_from("<H", head, 32)[0] or 1
        data_size = size - HEADER_SIZE
        data_size -= data_size % block_align  # drop a torn partial frame
        if struct.unpack_from("<I", head, 40)[0] == data_size and size == HEADER_SIZE + data_size:
            return False
        f.seek(4)
        f.write(struct.pack("<I", 36 + data_size))
        f.seek(40)
        f.write(struct.pack("<I", data_size))
        f.truncate(HEADER_SIZE + data_size)
        f.flush()
        os.fsync(f.fileno())
    return True
