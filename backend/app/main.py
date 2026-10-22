"""TurboTranscribe API.

Run from ``backend/``:  uvicorn main:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Body, FastAPI, File, Form, HTTPException, Query, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import crossref, llm, media
from .config import BACKEND_DIR, settings
from .diarization import Diarizer
from .jobs import Job, JobManager
from .live import LiveSession
from .pipeline import Engines, JobOptions, process_media
from .platform_tuning import disable_power_throttling
from .search import SearchIndex
from .transcriber import Transcriber
from .vision import OcrPool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("turbotranscribe")

VERSION = "3.1.0"
JOB_ID_RE = re.compile(r"^[0-9a-f]{12}$")
FRAME_RE = re.compile(r"^\d{4}\.jpg$")
LOCAL_ORIGIN_RE = r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$"
LANGUAGE_RE = re.compile(r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$")


def origin_allowed(origin: str | None) -> bool:
    """Requests without an Origin (curl, scripts) are fine; browsers must come from a local page."""
    return not origin or origin in settings.cors_origins or re.match(LOCAL_ORIGIN_RE, origin) is not None


# ---------------------------------------------------------------- models
class Models:
    """Models load in a background thread so the API is reachable immediately."""

    def __init__(self):
        self.batch: Transcriber | None = None
        self.live: Transcriber | None = None
        self.ready = threading.Event()
        self.error: str | None = None
        self.stage = "Starting"
        self._live_lock = threading.Lock()
        self.ocr = OcrPool(settings.ocr_workers, settings.ocr_min_confidence, settings.ocr_threads)
        self.diarizer = (Diarizer(settings.models_dir, settings.diarization_threshold, mode=settings.diarization_mode)
                         if settings.diarization else None)

    def _make(self, model_name: str, live: bool = False) -> Transcriber:
        return Transcriber(model_name, settings.whisper_engine, settings.whisper_device,
                           settings.whisper_compute_type, settings.whisper_cpu_threads,
                           settings.whisper_beam_size, settings.language, settings.word_timestamps, live=live,
                           batch_size=settings.whisper_batch_size)

    def load(self) -> None:
        try:
            self.stage = f"Loading speech model ({settings.whisper_model})"
            log.info("%s...", self.stage)
            self.batch = self._make(settings.whisper_model)
            if settings.ocr_enabled:
                self.stage = "Loading OCR"
                self.ocr.warm_up()
            if self.diarizer:
                self.stage = "Preparing speaker identification"
                self.diarizer.ensure_models()
            self.stage = "Ready"
        except Exception as exc:
            self.error = str(exc)
            self.stage = "Failed"
            log.exception("Model loading failed")
        finally:
            self.ready.set()

    def get_batch(self) -> Transcriber:
        self.ready.wait()
        if self.batch is None:
            raise RuntimeError(f"Speech model failed to load: {self.error}")
        return self.batch

    def get_live(self) -> Transcriber:
        """A separate instance so a long batch job never stalls a live meeting."""
        with self._live_lock:
            if self.live is None:
                self.live = self._make(settings.live_whisper_model, live=True)
            return self.live


models = Models()
search_index = SearchIndex(settings.data_dir / "index.db")


def refresh_result(result: dict) -> None:
    """Recompute everything derived from segments/keyframes after processing or an edit."""
    result["text"] = " ".join(s["text"] for s in result.get("segments", [])).strip()
    result["stats"] = crossref.compute_stats(result)
    result["notes_context"] = crossref.build_notes_context(result, settings.llm_context_chars)


def _process(job: Job, src: Path, report) -> dict:
    if not models.ready.is_set():
        report("Waiting for the speech model to load", 0.0)
    diarizer = models.diarizer if models.diarizer and models.diarizer.available else None
    engines = Engines(models.get_batch(), models.ocr, diarizer)
    preset = None
    if job.kind == "live":
        frames_file = jobs.job_dir(job.id) / "live_frames.json"
        preset = json.loads(frames_file.read_text(encoding="utf-8")) if frames_file.exists() else []
    return process_media(
        src, job.filename, jobs.job_dir(job.id), engines, settings, report,
        frame_url=lambda name: f"/api/jobs/{job.id}/frames/{name}",
        options=JobOptions.from_dict(job.options), preset_keyframes=preset,
    )


jobs = JobManager(settings.data_dir / "jobs", _process, settings.job_ttl_hours, settings.keep_media,
                  on_result=lambda job, result: search_index.index(job.id, result), refresh=refresh_result)


def _startup_tasks() -> None:
    models.load()
    indexed = search_index.indexed_ids()
    for job in jobs.list():
        if job.status == "done" and job.id not in indexed:
            result = jobs.result(job.id)
            if result:
                search_index.index(job.id, result)
    recovered = jobs.recover_live_recordings()
    if recovered:
        log.info("Recovered %d interrupted live recording(s)", len(recovered))


async def _cleanup_loop() -> None:
    while True:
        removed = jobs.cleanup_expired()
        if removed:
            log.info("Removed %d expired job(s)", removed)
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(_: FastAPI):
    disable_power_throttling()
    if not media.ffmpeg_available():
        log.warning("ffmpeg/ffprobe not found on PATH - uploads will fail until it is installed.")
    threading.Thread(target=_startup_tasks, name="startup", daemon=True).start()
    cleanup = asyncio.create_task(_cleanup_loop())
    yield
    cleanup.cancel()
    jobs.shutdown()
    search_index.close()


class SecurityMiddleware:
    """Pure ASGI (keeps streaming responses unbuffered).

    - Rejects state-changing requests from non-local web pages (CSRF): browsers always
      send Origin on cross-site POSTs, and only local pages may drive this server.
    - Adds standard security headers; the served UI also gets a strict CSP.
    """

    CSP = ("default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; "
           "connect-src 'self' ws: wss:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; "
           "script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        path = scope.get("path", "")
        if scope["method"] in ("POST", "PATCH", "PUT", "DELETE") and not origin_allowed(headers.get("origin")):
            await send({"type": "http.response.start", "status": 403,
                        "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": b'{"detail":"Cross-site request blocked"}'})
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                extra = [(b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"no-referrer")]
                if not path.startswith("/api/"):
                    extra += [(b"content-security-policy", self.CSP.encode()), (b"x-frame-options", b"DENY")]
                message["headers"] = list(message.get("headers", [])) + extra
            await send(message)

        await self.app(scope, receive, send_with_headers)


app = FastAPI(title="TurboTranscribe", version=VERSION, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=LOCAL_ORIGIN_RE,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)
app.add_middleware(SecurityMiddleware)
api = APIRouter(prefix="/api")


# ---------------------------------------------------------------- health
@api.get("/health")
def health() -> dict:
    t = models.batch
    diarizer = models.diarizer
    return {
        "status": "ok" if models.ready.is_set() and t else ("error" if models.error else "loading"),
        "stage": models.stage,
        "error": models.error,
        "version": VERSION,
        "engine": t.engine if t else None,
        "model": t.model_name if t else settings.whisper_model,
        "live_model": models.live.model_name if models.live else settings.live_whisper_model,
        "device": t.device if t else None,
        "ffmpeg": media.ffmpeg_available(),
        "video_processing": settings.video_enabled,
        "ocr": models.ocr.available if settings.ocr_enabled else False,
        "diarization": bool(diarizer and diarizer.available),
        "diarization_error": diarizer.error if diarizer else None,
        "llm_configured": settings.llm_configured,
        "llm_model": settings.llm_model,
        "vision_enabled": settings.vision_enabled,
        "local_only": settings.local_only,
        "keep_media": settings.keep_media,
        "storage_bytes": jobs.storage_bytes(),
        "jobs": len(jobs.list()),
    }


# ---------------------------------------------------------------- jobs
def _job_or_404(job_id: str) -> Job:
    job = jobs.get(job_id) if JOB_ID_RE.match(job_id) else None
    if job is None:
        raise HTTPException(404, "Not found")
    return job


def _options(language: str, glossary: str, diarize: bool, num_speakers: int | None, describe_visuals: bool,
             title: str) -> dict:
    language = language.strip()
    if language and not LANGUAGE_RE.match(language):
        raise HTTPException(422, "Language must be a code such as 'en' or 'pt-BR'")
    if num_speakers is not None and not 1 <= num_speakers <= 20:
        raise HTTPException(422, "Number of speakers must be between 1 and 20")
    return {"language": language or None, "glossary": glossary[:5000], "diarize": diarize,
            "num_speakers": num_speakers, "describe_visuals": describe_visuals, "title": title.strip()[:200]}


@api.post("/jobs", status_code=202)
async def create_job(
    file: UploadFile = File(...),
    language: str = Form(""),
    glossary: str = Form(""),
    diarize: bool = Form(True),
    num_speakers: int | None = Form(None),
    describe_visuals: bool = Form(False),
    title: str = Form(""),
) -> dict:
    options = _options(language, glossary, diarize, num_speakers, describe_visuals, title)
    filename = Path(file.filename or "upload").name
    suffix = Path(filename).suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
        suffix = ".bin"
    job, work = jobs.new_job(filename, options=options, title=options["title"])
    dest = work / f"input{suffix}"
    limit, size = settings.max_upload_mb * 1024 * 1024, 0
    try:
        with dest.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, f"File exceeds the {settings.max_upload_mb} MB limit")
                out.write(chunk)
        # Reject non-media up front instead of queueing a job that will fail.
        try:
            info = await run_in_threadpool(media.probe, dest)
        except media.MediaError:
            raise HTTPException(415, "This file is not an audio or video file ffmpeg can read")
        if not info.has_audio and not info.has_video:
            raise HTTPException(415, "No audio or video stream found in this file")
        if info.duration > settings.max_media_minutes * 60:
            raise HTTPException(413, f"Recording is longer than {settings.max_media_minutes:.0f} minutes")
    except BaseException:
        jobs.delete(job.id)
        raise
    finally:
        await file.close()
    job.media = info.as_dict()
    jobs.submit(job, dest)
    return job.summary()


@api.get("/jobs")
def list_jobs() -> list[dict]:
    return [j.summary() for j in jobs.list()]


@api.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = _job_or_404(job_id)
    body = job.summary()
    if job.status == "done":
        result = jobs.result(job_id)
        if result is not None:
            result["has_media"] = job.media_file is not None
            body["result"] = result
    return body


class JobPatch(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    speakers: dict[str, str] | None = None  # {"S1": "Priya"}


@api.patch("/jobs/{job_id}")
def update_job(job_id: str, patch: JobPatch) -> dict:
    job = _job_or_404(job_id)
    if patch.title is not None:
        job.title = patch.title.strip() or job.title
        job.options["title"] = job.title
    if job.status != "done":
        jobs._save_meta(job)
        return job.summary()

    def change(result: dict) -> None:
        if patch.title is not None:
            result["title"] = job.title
        for spk in result.get("speakers", []):
            name = (patch.speakers or {}).get(spk["id"])
            if name is not None:
                spk["name"] = name.strip()[:60] or spk["name"]

    return jobs.edit(job_id, change)


class SegmentPatch(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    speaker: str | None = None


@api.patch("/jobs/{job_id}/segments/{segment_id}")
def update_segment(job_id: str, segment_id: int, patch: SegmentPatch) -> dict:
    _job_or_404(job_id)

    def change(result: dict) -> None:
        seg = next((s for s in result["segments"] if s["id"] == segment_id), None)
        if seg is None:
            raise HTTPException(404, "Segment not found")
        if patch.text.strip() != seg["text"]:
            seg["text"], seg["words"], seg["edited"] = patch.text.strip(), None, True
        if patch.speaker is not None:
            if patch.speaker and patch.speaker not in {s["id"] for s in result.get("speakers", [])}:
                raise HTTPException(422, "Unknown speaker")
            seg["speaker"] = patch.speaker or None

    try:
        return jobs.edit(job_id, change)
    except KeyError:
        raise HTTPException(409, "This item has no transcript yet")


class CorrectionAction(BaseModel):
    action: Literal["accept", "dismiss", "reset"]


def _apply_correction(result: dict, correction: dict) -> bool:
    seg = next((s for s in result["segments"] if s["id"] == correction["segment_id"]), None)
    return bool(seg) and crossref.apply_correction(seg, correction["heard"], correction["seen"])


@api.post("/jobs/{job_id}/corrections/{correction_id}")
def act_on_correction(job_id: str, correction_id: int, body: CorrectionAction) -> dict:
    _job_or_404(job_id)

    def change(result: dict) -> None:
        corr = next((c for c in result.get("corrections", []) if c.get("id") == correction_id), None)
        if corr is None:
            raise HTTPException(404, "Correction not found")
        if body.action == "accept" and corr["status"] != "accepted":
            corr["status"] = "accepted" if _apply_correction(result, corr) else "stale"
        elif body.action == "dismiss":
            corr["status"] = "dismissed"
        elif body.action == "reset" and corr["status"] == "dismissed":
            corr["status"] = "pending"

    try:
        return jobs.edit(job_id, change)
    except KeyError:
        raise HTTPException(409, "This item has no transcript yet")


@api.post("/jobs/{job_id}/corrections")
def accept_corrections(job_id: str, confidence: Literal["high", "all"] = Body("high", embed=True)) -> dict:
    """Accept every pending suggestion (only the high-confidence ones by default)."""
    _job_or_404(job_id)

    def change(result: dict) -> None:
        for corr in result.get("corrections", []):
            if corr.get("status") == "pending" and (confidence == "all" or corr.get("confidence") == "high"):
                corr["status"] = "accepted" if _apply_correction(result, corr) else "stale"

    try:
        return jobs.edit(job_id, change)
    except KeyError:
        raise HTTPException(409, "This item has no transcript yet")


@api.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    job = _job_or_404(job_id)
    if not jobs.cancel(job_id):
        raise HTTPException(409, "Only queued or running jobs can be cancelled")
    return job.summary()


class ReprocessRequest(BaseModel):
    language: str = ""
    glossary: str = Field(default="", max_length=5000)
    diarize: bool = True
    num_speakers: int | None = None
    describe_visuals: bool = False


@api.post("/jobs/{job_id}/reprocess", status_code=202)
def reprocess_job(job_id: str, body: ReprocessRequest) -> dict:
    job = _job_or_404(job_id)
    options = _options(body.language, body.glossary, body.diarize, body.num_speakers, body.describe_visuals,
                       job.title)
    try:
        return jobs.reprocess(job_id, options).summary()
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@api.delete("/jobs/{job_id}")
def delete_job(job_id: str) -> dict:
    job = _job_or_404(job_id)
    if job.status == "recording":
        raise HTTPException(409, "Stop the live meeting before deleting it")
    jobs.delete(job_id)
    search_index.remove(job_id)
    return {"deleted": job_id}


@api.get("/jobs/{job_id}/media")
def get_media(job_id: str) -> FileResponse:
    _job_or_404(job_id)
    path = jobs.media_path(job_id)
    if path is None:
        raise HTTPException(404, "Media was not kept for this item")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=3600"})


@api.get("/jobs/{job_id}/frames/{name}")
def get_frame(job_id: str, name: str) -> FileResponse:
    _job_or_404(job_id)
    path = jobs.job_dir(job_id) / "frames" / name
    if not FRAME_RE.match(name) or not path.is_file():
        raise HTTPException(404, "Frame not found")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


# ---------------------------------------------------------------- search
@api.get("/search")
def search(q: str = Query(min_length=1, max_length=200)) -> list[dict]:
    groups: dict[str, dict] = {}
    for hit in search_index.search(q):
        job = jobs.get(hit["job_id"])
        if job is None:
            continue
        group = groups.setdefault(job.id, {"job_id": job.id, "title": job.title, "kind": job.kind,
                                           "created_at": job.created_at, "hits": []})
        group["hits"].append(hit)
    return list(groups.values())


# ---------------------------------------------------------------- chat
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=20_000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=60)
    job_ids: list[str] = Field(default_factory=list, max_length=20)
    context: str = Field(default="", max_length=2_000_000)
    stream: bool = False


def _chat_context(req: ChatRequest) -> str:
    parts = []
    for job_id in req.job_ids:
        result = jobs.result(job_id) if JOB_ID_RE.match(job_id) else None
        if result:
            parts.append(result.get("notes_context") or "")
    if req.context:
        parts.append(req.context)
    context = "\n\n".join(p for p in parts if p)
    if not context:
        raise HTTPException(400, "Nothing to analyze yet: transcribe a file or start a meeting first.")
    return context


@api.post("/chat")
async def chat(req: ChatRequest):
    if not settings.llm_configured:
        reason = ("Local-only mode is on." if settings.local_only
                  else "OPENROUTER_API_KEY is not set. Add it to backend/.env and restart the backend.")
        raise HTTPException(503, reason)
    context = await run_in_threadpool(_chat_context, req)
    messages = [m.model_dump() for m in req.messages]
    if not req.stream:
        try:
            reply = await llm.chat(messages, context)
        except llm.LLMError as exc:
            raise HTTPException(502, str(exc)) from exc
        except Exception as exc:
            log.exception("Chat failed")
            raise HTTPException(502, f"LLM request failed: {exc}") from exc
        return {"reply": reply, "model": settings.llm_model}

    async def events():
        try:
            async for delta in llm.chat_stream(messages, context):
                yield f"data: {json.dumps({'delta': delta})}\n\n"
            yield f"data: {json.dumps({'done': True, 'model': settings.llm_model})}\n\n"
        except Exception as exc:
            if not isinstance(exc, llm.LLMError):
                log.exception("Chat stream failed")
            yield f"data: {json.dumps({'error': str(exc) or exc.__class__.__name__})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- live
@api.websocket("/ws/live")
async def live(ws: WebSocket) -> None:
    if not origin_allowed(ws.headers.get("origin")):
        await ws.close(code=1008)
        return
    try:
        if not models.ready.is_set():
            await run_in_threadpool(models.ready.wait)
        transcriber = await run_in_threadpool(models.get_live)
    except Exception as exc:
        await ws.accept()
        await ws.send_json({"type": "error", "message": f"Speech model unavailable: {exc}"})
        await ws.close()
        return
    await LiveSession(ws, transcriber, models.ocr, settings, jobs).run()


app.include_router(api)

# Serve the production frontend build (npm run build) from the same port, if present.
_dist = BACKEND_DIR.parent / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
