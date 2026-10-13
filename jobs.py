"""Jobs on disk: one JSON file per recording/transcription, so no work is lost if the
process dies. A job file is deleted only after its transcript is fully written."""

import glob
import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime

import wavio

RECORDING, PENDING, FAILED = "recording", "pending", "failed"

log = logging.getLogger(__name__)


@dataclass
class Job:
    id: str
    audio: str
    language: str | None
    model: str
    state: str = PENDING
    error: str | None = None


def atomic_write(path, text: str) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def unique_id(dirs, now: datetime | None = None) -> str:
    """Timestamp id not yet used by any file (any extension) in `dirs`."""
    base = (now or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
    job_id, n = base, 2
    while any(glob.glob(os.path.join(d, glob.escape(job_id) + ".*")) for d in dirs):
        job_id, n = f"{base}-{n}", n + 1
    return job_id


class JobStore:
    def __init__(self, directory):
        self.dir = str(directory)
        os.makedirs(self.dir, exist_ok=True)

    def _path(self, job_id: str) -> str:
        return os.path.join(self.dir, f"{job_id}.json")

    def save(self, job: Job) -> None:
        atomic_write(self._path(job.id), json.dumps(asdict(job), indent=2, ensure_ascii=False))

    def delete(self, job_id: str) -> None:
        try:
            os.remove(self._path(job_id))
        except FileNotFoundError:
            pass

    def all(self) -> list[Job]:
        jobs = []
        for path in sorted(glob.glob(os.path.join(self.dir, "*.json"))):
            try:
                with open(path, encoding="utf-8") as f:
                    jobs.append(Job(**json.load(f)))
            except (OSError, ValueError, TypeError):
                log.exception("Skipping unreadable job file %s", path)
        return jobs


def recover(store: JobStore) -> list[Job]:
    """After a restart: repair recordings cut off by a kill, return every job still to transcribe."""
    pending = []
    for job in store.all():
        if job.state == RECORDING:
            if not os.path.exists(job.audio) or os.path.getsize(job.audio) <= wavio.HEADER_SIZE:
                log.info("Dropping job %s: no audio was recorded", job.id)
                store.delete(job.id)
                continue
            wavio.repair(job.audio)
            job.state = PENDING
            store.save(job)
            log.info("Recovered interrupted recording %s", job.id)
        if job.state == PENDING:
            pending.append(job)
    return pending
