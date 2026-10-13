"""Background transcription: one worker thread runs queued jobs through mlx-whisper.

Also runnable headless, through the same job queue the menu's "Transcribe file…" uses:
    .venv/bin/python -m transcriber some.m4a --language sk
"""

import argparse
import contextlib
import logging
import os
import queue
import sys
import threading

import formats
import jobs
import paths
from jobs import FAILED, PENDING, Job, JobStore

MODELS = {
    "whisper-large-v3-mlx": "mlx-community/whisper-large-v3-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
}
DEFAULT_MODEL = "whisper-large-v3-mlx"

log = logging.getLogger(__name__)


@contextlib.contextmanager
def _progress_hook(on_progress):
    """mlx-whisper reports progress only through a tqdm bar; swap in one that calls us back."""
    import tqdm

    original = tqdm.tqdm

    class Reporting(original):
        def update(self, n=1):
            super().update(n)
            if self.total:
                on_progress(min(1.0, self.n / self.total))

    tqdm.tqdm = Reporting
    try:
        yield
    finally:
        tqdm.tqdm = original


def transcribe_job(job: Job, out_dir: str, on_progress=lambda fraction: None) -> str:
    """Transcribe job.audio into <out_dir>/<job.id>.srt and .txt; returns the .txt path."""
    import mlx_whisper  # slow import; keep it off the app's startup path

    with _progress_hook(on_progress):
        result = mlx_whisper.transcribe(
            job.audio,
            path_or_hf_repo=MODELS[job.model],
            language=job.language,
            verbose=False,
            condition_on_previous_text=False,  # avoids repetition loops on long meetings
        )
    base = os.path.join(out_dir, job.id)
    jobs.atomic_write(base + ".srt", formats.to_srt(result["segments"]))
    jobs.atomic_write(base + ".txt", formats.to_txt(result["segments"]))  # written last: marks done
    return base + ".txt"


def new_file_job(store: JobStore, audio: str, language: str | None, model: str) -> Job:
    job_id = jobs.unique_id([paths.JOBS, paths.RECORDINGS, paths.TRANSCRIPTS])
    job = Job(job_id, os.path.abspath(audio), language, model, state=PENDING)
    store.save(job)
    return job


class Worker:
    """Runs jobs one at a time. on_event(kind, job, detail) is called from the worker thread
    with kind "done" (detail = .txt path) or "failed" (detail = error message)."""

    def __init__(self, store: JobStore, out_dir: str, on_event):
        self.store, self.out_dir, self.on_event = store, out_dir, on_event
        self.current: Job | None = None
        self.progress = 0.0
        self._queue: queue.Queue[Job] = queue.Queue()
        threading.Thread(target=self._run, name="transcriber", daemon=True).start()

    def submit(self, job: Job) -> None:
        self._queue.put(job)

    @property
    def queued(self) -> int:
        return self._queue.qsize()

    def _set_progress(self, fraction: float) -> None:
        self.progress = fraction

    def _run(self):
        while True:
            job = self._queue.get()
            self.current, self.progress = job, 0.0
            log.info("Transcribing %s (%s, %s)", job.audio, job.language or "auto", job.model)
            try:
                txt = transcribe_job(job, self.out_dir, self._set_progress)
                self.store.delete(job.id)
                log.info("Done: %s", txt)
                self.on_event("done", job, txt)
            except Exception as e:
                log.exception("Transcription of %s failed", job.audio)
                job.state, job.error = FAILED, f"{type(e).__name__}: {e}"
                self.store.save(job)
                self.on_event("failed", job, job.error)
            finally:
                self.current = None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("file")
    parser.add_argument("--language", default="sk", help="sk, cs, en, … or auto")
    parser.add_argument("--model", default=DEFAULT_MODEL, choices=MODELS)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    store = JobStore(paths.JOBS)
    events: queue.Queue = queue.Queue()
    worker = Worker(store, paths.TRANSCRIPTS, lambda *event: events.put(event))
    worker.submit(new_file_job(store, args.file, None if args.language == "auto" else args.language, args.model))
    kind, job, detail = events.get()
    if kind == "failed":
        print(f"FAILED: {detail}", file=sys.stderr)
        return 1
    print(detail)
    print(detail.removesuffix(".txt") + ".srt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
