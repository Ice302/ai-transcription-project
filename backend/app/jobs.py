"""In-process job queue with on-disk results.

Uploads return immediately with a job id; a single worker thread processes jobs in
order (Whisper saturates the CPU/GPU, so running jobs in parallel would only slow each
one down). The frontend polls ``GET /api/jobs/{id}`` for real progress.

Each job lives in ``data/jobs/<id>/``: ``job.json`` (summary), ``result.json``,
``frames/`` (keyframes) and, when KEEP_MEDIA is on, ``media.*`` for playback.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from . import media as media_tools

log = logging.getLogger(__name__)


class JobCancelled(Exception):
    pass


@dataclass
class Job:
    id: str
    filename: str
    kind: str = "file"  # file | live
    title: str = ""
    status: str = "queued"  # recording | queued | running | done | error | cancelled
    stage: str = "Queued"
    progress: float = 0.0
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    options: dict = field(default_factory=dict)
    media: dict = field(default_factory=dict)  # probe info: duration, has_video, ...
    media_file: str | None = None  # stored copy for playback, relative to the job dir
    stats: dict = field(default_factory=dict)
    size_bytes: int = 0
    cancel_requested: bool = False

    def summary(self) -> dict:
        data = asdict(self)
        data.pop("cancel_requested")
        data["has_media"] = self.media_file is not None
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Job":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


Processor = Callable[[Job, Path, Callable[[str, float], None]], dict]
ResultHook = Callable[[Job, dict], None]


def _write_json_atomic(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


class JobManager:
    def __init__(self, root: Path, processor: Processor, ttl_hours: float = 0, keep_media: bool = True,
                 on_result: ResultHook | None = None, refresh: Callable[[dict], None] | None = None):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.processor = processor
        self.ttl = ttl_hours * 3600
        self.keep_media = keep_media
        self.on_result = on_result  # e.g. search indexing
        self.refresh = refresh  # recompute derived fields (stats, notes context) after edits
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._edit_locks: dict[str, threading.Lock] = {}
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="job")
        self._load_existing()

    # -- persistence ---------------------------------------------------------
    def job_dir(self, job_id: str) -> Path:
        return self.root / job_id

    def _save_meta(self, job: Job) -> None:
        if self.job_dir(job.id).exists():
            _write_json_atomic(self.job_dir(job.id) / "job.json", asdict(job))

    def _load_existing(self) -> None:
        for meta in self.root.glob("*/job.json"):
            try:
                job = Job.from_dict(json.loads(meta.read_text(encoding="utf-8")))
            except Exception:
                log.warning("Skipping unreadable job metadata %s", meta)
                continue
            if job.status in ("recording", "queued", "running"):  # interrupted by a restart
                job.status, job.error, job.stage = "error", "Server restarted before the job finished.", "Interrupted"
                self._save_meta(job)
            self._jobs[job.id] = job

    def cleanup_expired(self) -> int:
        if self.ttl <= 0:
            return 0
        cutoff = time.time() - self.ttl
        expired = [j.id for j in list(self._jobs.values())
                   if j.status in ("done", "error", "cancelled") and (j.finished_at or j.created_at) < cutoff]
        for job_id in expired:
            self.delete(job_id)
        return len(expired)

    def recover_live_recordings(self) -> list[str]:
        """Re-queue live meetings whose recording survived a crash or restart (live.pcm on disk)."""
        recovered = []
        for job in self.list():
            raw = self.job_dir(job.id) / "live.pcm"
            if job.kind != "live" or job.status != "error" or not raw.exists() or raw.stat().st_size < 64000:
                continue
            channels = 2 if len(job.options.get("channel_labels") or []) == 2 else 1
            try:
                wav = media_tools.pcm16_to_wav(raw, self.job_dir(job.id) / "input.wav", channels)
                raw.unlink(missing_ok=True)
            except Exception as exc:
                log.warning("Could not recover live recording %s: %s", job.id, exc)
                continue
            job.status, job.stage, job.error, job.progress = "queued", "Queued (recovered)", None, 0.0
            self._save_meta(job)
            self.submit(job, wav)
            recovered.append(job.id)
        return recovered

    def storage_bytes(self) -> int:
        return sum(j.size_bytes for j in self._jobs.values())

    # -- public API ----------------------------------------------------------
    def new_job(self, filename: str, kind: str = "file", options: dict | None = None,
                title: str = "") -> tuple[Job, Path]:
        job = Job(id=uuid.uuid4().hex[:12], filename=filename, kind=kind, options=options or {},
                  title=title or Path(filename).stem)
        work = self.job_dir(job.id)
        work.mkdir(parents=True)
        with self._lock:
            self._jobs[job.id] = job
        self._save_meta(job)
        return job, work

    def submit(self, job: Job, src: Path) -> None:
        self._executor.submit(self._run, job, src)

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def result(self, job_id: str) -> dict | None:
        path = self.job_dir(job_id) / "result.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def media_path(self, job_id: str) -> Path | None:
        job = self.get(job_id)
        if not job or not job.media_file:
            return None
        path = self.job_dir(job_id) / job.media_file
        return path if path.is_file() else None

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if not job or job.status not in ("queued", "running"):
            return False
        job.cancel_requested = True
        if job.status == "queued":
            job.status, job.stage, job.finished_at = "cancelled", "Cancelled", time.time()
        self._save_meta(job)
        return True

    def reprocess(self, job_id: str, options: dict) -> Job:
        """Run the pipeline again on the stored media with new options (language, glossary...)."""
        job = self.get(job_id)
        src = self.media_path(job_id)
        if not job or src is None:
            raise ValueError("The original media was not kept, so this item can't be reprocessed.")
        if job.status in ("queued", "running"):
            raise ValueError("This item is already being processed.")
        job.options = {**job.options, **options}
        job.status, job.stage, job.progress, job.error = "queued", "Queued", 0.0, None
        job.cancel_requested, job.started_at, job.finished_at = False, None, None
        self._save_meta(job)
        self.submit(job, src)
        return job

    def edit(self, job_id: str, change: Callable[[dict], object]) -> dict:
        """Apply ``change`` to the stored result under a per-job lock, then save and reindex."""
        with self._lock:
            lock = self._edit_locks.setdefault(job_id, threading.Lock())
        with lock:
            result = self.result(job_id)
            if result is None:
                raise KeyError(job_id)
            change(result)
            if self.refresh:
                self.refresh(result)
            _write_json_atomic(self.job_dir(job_id) / "result.json", result)
            job = self.get(job_id)
            if job:
                job.title, job.stats = result.get("title", job.title), result.get("stats", job.stats)
                self._save_meta(job)
                if self.on_result:
                    self.on_result(job, result)
            return result

    def delete(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.pop(job_id, None)
        if job and job.status in ("queued", "running"):
            job.cancel_requested = True
        shutil.rmtree(self.job_dir(job_id), ignore_errors=True)
        return job is not None

    def shutdown(self) -> None:
        for job in self._jobs.values():
            if job.status in ("queued", "running"):
                job.cancel_requested = True
        self._executor.shutdown(wait=False, cancel_futures=True)

    # -- worker --------------------------------------------------------------
    def _store_media(self, job: Job, src: Path) -> None:
        """Keep the input for playback (or delete it). Live recordings are compressed first."""
        work = self.job_dir(job.id)
        if job.media_file and src == work / job.media_file:
            return  # reprocessing the stored copy
        if not self.keep_media:
            src.unlink(missing_ok=True)
            return
        try:
            if src.suffix.lower() == ".wav" and job.kind == "live":
                dst = media_tools.transcode_audio(src, work / "media.m4a")
                src.unlink(missing_ok=True)
            else:
                dst = src.replace(work / f"media{src.suffix.lower()}")
            job.media_file = dst.name
        except Exception as exc:
            log.warning("Could not keep media for %s: %s", job.id, exc)
            src.unlink(missing_ok=True)

    def _run(self, job: Job, src: Path) -> None:
        if job.id not in self._jobs or job.cancel_requested:  # deleted or cancelled while queued
            return
        job.status, job.stage, job.started_at = "running", "Starting", time.time()
        last_save = 0.0

        def report(stage: str, progress: float) -> None:
            nonlocal last_save
            if job.cancel_requested:
                raise JobCancelled()
            job.stage, job.progress = stage, round(max(job.progress, min(progress, 1.0)), 4)
            if time.time() - last_save > 2:
                last_save = time.time()
                self._save_meta(job)

        result = None
        try:
            result = self.processor(job, src, report)
        except JobCancelled:
            job.status, job.stage = "cancelled", "Cancelled"
        except Exception as exc:
            log.exception("Job %s failed", job.id)
            job.status, job.stage, job.error = "error", "Failed", str(exc) or exc.__class__.__name__
        job.finished_at = time.time()
        if job.id not in self._jobs:  # deleted while running
            shutil.rmtree(self.job_dir(job.id), ignore_errors=True)
            return
        self._store_media(job, src)  # failed runs keep their input too, so they can be retried

        if result is not None:
            result["id"], result["kind"], result["created_at"] = job.id, job.kind, job.created_at
            result["title"] = job.title or result.get("title", "")
            result["has_media"] = job.media_file is not None
            if self.refresh:
                self.refresh(result)
            _write_json_atomic(self.job_dir(job.id) / "result.json", result)
            job.status, job.stage, job.progress = "done", "Complete", 1.0
            job.media, job.stats = result.get("media", {}), result.get("stats", {})
            if self.on_result:
                try:
                    self.on_result(job, result)
                except Exception:
                    log.exception("Result hook failed for %s", job.id)
        job.size_bytes = _dir_size(self.job_dir(job.id))
        self._save_meta(job)
