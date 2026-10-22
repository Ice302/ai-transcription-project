"""Live meeting session over WebSocket: continuous audio stream + optional screen frames.

Client -> server (JSON text frames):
    {"type": "start", "channels": 1|2, "labels": ["You", "Others"], "glossary": str,
     "language": str|null, "title": str, "save": bool}           optional, before any audio
    {"type": "audio", "data": <base64 bytes of ONE continuous MediaRecorder stream>}
    {"type": "frame", "t": <seconds since start>, "data": <base64 jpeg>}
    {"type": "stop"}            -> flush, queue the high-accuracy pass, reply "saved" + "done"
Server -> client:
    {"type": "ready", "engine", "model", "ocr", "job_id"}
    {"type": "speech", "id": int, "t", "end", "text", "speaker": str|null}    final text
    {"type": "partial", "t", "text", "speaker", "lag"}       unstable tail, replaced later
    {"type": "retract", "id": int}            a "You" line turned out to be echo of "Others"
    {"type": "visual", "t", "text", "title", "terms", "image"}
    {"type": "correction", "t", "heard", "seen", "similarity"}
    {"type": "error", "message"}
    {"type": "saved", "job_id"}               the recording is queued for the final pass
    {"type": "done"}

Why a stream instead of fixed 5 s chunks: chunking cut words in half at every
boundary ("Migrate" -> "My." + "Great") and gave Whisper no context. Instead the
browser sends one continuous recording, a persistent ffmpeg process decodes it to
PCM, and Whisper repeatedly re-reads a sliding window of *uncommitted* audio. Only
sentences that end comfortably before the window edge are committed; the tail is
re-transcribed with more context on the next pass (a simplified version of the
"local agreement" policy from whisper_streaming).

Two-channel mode: the browser puts the microphone on the left channel and the
shared tab on the right, so "You" and "Others" are transcribed separately.

Durability: the session is a library job from the first second. Decoded audio is
appended to ``live.pcm`` and screen frames to ``frames/`` as they arrive; when the
meeting ends (or the browser disconnects) the recording is queued for a full
high-accuracy pass with speaker identification.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import subprocess
import threading
import time
from collections import Counter, deque
from pathlib import Path

import numpy as np
from fastapi import WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from . import crossref, media
from .config import Settings
from .jobs import JobManager
from .media import SAMPLE_RATE
from .platform_tuning import disable_power_throttling
from .transcriber import SENTENCE_END, Transcriber
from .vision import OcrPool

log = logging.getLogger(__name__)

STEP_SECONDS = 1.5          # how often the window is re-transcribed
MIN_NEW_AUDIO = 1.0         # ...but only if at least this much new audio arrived
STABLE_MARGIN = 1.2         # segments ending closer than this to the window edge stay "partial"
UNPUNCTUATED_MARGIN = 3.0   # a segment without a sentence end needs a longer pause after it
MAX_WINDOW = 25.0           # force a commit if no stable boundary appears for this long
MAX_MESSAGE_BYTES = 8 * 1024 * 1024


def split_stable(segments: list[dict], window_len: float, final: bool) -> int:
    """Number of leading segments that are safe to commit.

    A segment is stable when it ends at least STABLE_MARGIN before the window edge
    and either ends a sentence or is followed by a long pause. Pause-only splits
    near the edge produced one-word fragments ("Their", "Action") in testing.
    """
    if final:
        return len(segments)
    n = 0
    for seg in segments:
        margin = window_len - seg["end"]
        ends_sentence = seg["text"].rstrip().endswith(SENTENCE_END)
        if margin >= STABLE_MARGIN and (ends_sentence or margin >= UNPUNCTUATED_MARGIN):
            n += 1
        else:
            break
    if n == 0 and segments and window_len >= MAX_WINDOW - 0.5:
        n = max(1, len(segments) - 1)  # window is full: commit all but the newest segment
    return n


def strip_overlap(previous: str, text: str, max_words: int = 3) -> str:
    """Drop words at the start of ``text`` that repeat the end of the previous line.

    Re-reading audio from a cut point can repeat the last word ("Action" / "Action items").
    """
    prev = [crossref.norm(w) for w in previous.split()][-max_words:]
    words = text.split()
    for n in range(min(max_words, len(prev), len(words) - 1), 0, -1):
        if [crossref.norm(w) for w in words[:n]] == prev[-n:] and all(prev[-n:]):
            return " ".join(words[n:])
    return text


class AudioStream:
    """Feeds an encoded stream (webm/ogg/mp4) to ffmpeg; keeps recent PCM in memory, all of it on disk."""

    def __init__(self, channels: int = 1, record_to: Path | None = None):
        self.channels = channels
        self.proc = subprocess.Popen(
            [media.tool("ffmpeg"), "-v", "error", "-probesize", "8192", "-analyzeduration", "0", "-i", "pipe:0",
             "-vn", "-ac", str(channels), "-ar", str(SAMPLE_RATE), "-f", "f32le", "pipe:1"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        disable_power_throttling(self.proc.pid)
        self._buf = bytearray()
        self._base = 0      # frames dropped from the front of _buf
        self._frames = 0    # frames decoded so far
        self._lock = threading.Lock()
        self._record = record_to.open("wb") if record_to else None
        self._reader = threading.Thread(target=self._read, daemon=True, name="live-pcm")
        self._reader.start()

    @property
    def frame_bytes(self) -> int:
        return 4 * self.channels

    def _read(self) -> None:
        pending = b""
        try:
            while chunk := self.proc.stdout.read1(65536):
                data = pending + chunk
                usable = len(data) - len(data) % self.frame_bytes
                block, pending = data[:usable], data[usable:]
                with self._lock:
                    self._buf += block
                    self._frames += usable // self.frame_bytes
                if self._record:
                    pcm = np.frombuffer(block, dtype=np.float32)
                    self._record.write((np.clip(pcm, -1, 1) * 32767).astype("<i2").tobytes())
        finally:
            if self._record:
                self._record.close()

    def feed(self, data: bytes) -> None:
        try:
            self.proc.stdin.write(data)
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            pass

    @property
    def n_samples(self) -> int:
        return self._frames

    def samples(self, start: int, end: int, channel: int = 0) -> np.ndarray:
        with self._lock:
            s, e = max(start, self._base), min(end, self._frames)
            if e <= s:
                return np.zeros(0, dtype=np.float32)
            raw = bytes(self._buf[(s - self._base) * self.frame_bytes:(e - self._base) * self.frame_bytes])
        pcm = np.frombuffer(raw, dtype=np.float32)
        return pcm.reshape(-1, self.channels)[:, channel].copy() if self.channels > 1 else pcm

    def trim(self, before: int) -> None:
        """Forget audio before frame ``before`` (it is committed and already on disk)."""
        with self._lock:
            drop = before - self._base
            if drop > 0:
                del self._buf[:drop * self.frame_bytes]
                self._base = before

    def finish(self, timeout: float = 15.0) -> None:
        """Close stdin and wait until ffmpeg has emitted all remaining audio."""
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        self._reader.join(timeout)

    def kill(self) -> None:
        if self.proc.poll() is None:
            self.proc.kill()


class Channel:
    def __init__(self, index: int, label: str | None):
        self.index = index
        self.label = label
        self.committed = 0
        self.last_run_total = 0
        self.recent: deque[str] = deque(maxlen=6)
        self.history: deque[dict] = deque(maxlen=20)  # recent committed lines, for echo checks


class LiveSession:
    def __init__(self, ws: WebSocket, transcriber: Transcriber, ocr: OcrPool, cfg: Settings, jobs: JobManager):
        self.ws = ws
        self.transcriber = transcriber
        self.ocr = ocr
        self.cfg = cfg
        self.jobs = jobs
        self.ocr_enabled = cfg.ocr_enabled
        self.audio: AudioStream | None = None
        self.channels: list[Channel] = []
        self.options = {"channels": 1, "labels": [], "glossary": "", "language": None, "title": "", "save": True}
        self.job = None
        self.work: Path | None = None
        self.frames: list[dict] = []
        self.frame_q: asyncio.Queue = asyncio.Queue(maxsize=1)
        self.screen_terms: Counter[str] = Counter()
        self.current_screen_terms: list[str] = []
        self.last_screen_text = ""
        self.next_id = 0
        self.started = time.time()
        self._asr_lock = asyncio.Lock()
        self._finalized = False
        self.language_votes: Counter[str] = Counter()

    async def send(self, payload: dict) -> None:
        try:
            await self.ws.send_json(payload)
        except Exception:
            pass  # socket already closed; the receive loop will notice

    # -- setup -------------------------------------------------------------------
    def _configure(self, msg: dict) -> None:
        channels = 2 if msg.get("channels") == 2 else 1
        labels = [str(x)[:40] for x in (msg.get("labels") or [])][:channels]
        if channels == 2 and len(labels) < 2:
            labels = ["You", "Others"]
        self.options.update({
            "channels": channels, "labels": labels,
            "glossary": str(msg.get("glossary") or "")[:5000],
            "language": (str(msg["language"])[:8] or None) if msg.get("language") else None,
            "title": str(msg.get("title") or "")[:200],
            "save": msg.get("save", True) is not False,
        })

    def _ensure_started(self) -> None:
        if self.audio is not None:
            return
        title = self.options["title"] or time.strftime("Live meeting %Y-%m-%d %H:%M")
        job_options = {"language": self.options["language"], "glossary": self.options["glossary"],
                       "title": title, "channel_labels": self.options["labels"] if self.options["channels"] == 2 else []}
        self.job, self.work = self.jobs.new_job(f"{title}.m4a", kind="live", options=job_options, title=title)
        self.job.status, self.job.stage = "recording", "Recording"
        (self.work / "frames").mkdir(exist_ok=True)
        self.audio = AudioStream(self.options["channels"], record_to=self.work / "live.pcm")
        labels = self.options["labels"] or [None]
        self.channels = [Channel(i, labels[i] if i < len(labels) else None) for i in range(self.options["channels"])]

    def _language(self) -> str | None:
        """The chosen language, or - once 4 windows have been heard - the one most of them
        were detected as. Re-detecting every window lets mixed-language speech flip
        between languages mid-meeting."""
        if self.options["language"]:
            return self.options["language"]
        total = sum(self.language_votes.values())
        if total >= 4:
            language, votes = self.language_votes.most_common(1)[0]
            if votes / total >= 0.6:
                return language
        return None

    def _glossary(self) -> str | None:
        user = crossref.parse_user_glossary(self.options["glossary"])
        return crossref.build_glossary(user + [t for t, _ in self.screen_terms.most_common(40)], 400)

    # -- speech ------------------------------------------------------------------
    def _is_echo(self, ch: Channel, seg: dict, t: float, end: float) -> bool:
        if len(self.channels) < 2 or ch.index != 0:
            return False
        mine = crossref.norm(seg["text"])
        return any(o["end"] > t - 2 and o["t"] < end + 2 and crossref.similarity(mine, o["norm"]) >= 0.6
                   for o in self.channels[1].history)

    async def _commit(self, ch: Channel, seg: dict, offset: float) -> None:
        t, end = round(offset + seg["start"], 2), round(offset + seg["end"], 2)
        text = strip_overlap(ch.recent[-1] if ch.recent else "", seg["text"])
        if not text.strip() or self._is_echo(ch, {"text": text}, t, end):
            return
        event_id = self.next_id
        self.next_id += 1
        ch.recent.append(text)
        ch.history.append({"id": event_id, "t": t, "end": end, "norm": crossref.norm(text)})
        await self.send({"type": "speech", "id": event_id, "t": t, "end": end, "text": text, "speaker": ch.label})
        if len(self.channels) == 2 and ch.index == 1:
            # The "You" line may have been committed first; retract it if it echoes this one.
            mine = crossref.norm(text)
            for o in list(self.channels[0].history):
                if o["end"] > t - 2 and o["t"] < end + 2 and crossref.similarity(mine, o["norm"]) >= 0.6:
                    self.channels[0].history.remove(o)
                    await self.send({"type": "retract", "id": o["id"]})
        segment = crossref.Segment(id=0, start=t, end=end, text=text)
        for c in crossref.find_corrections(segment, self.current_screen_terms):
            await self.send({"type": "correction", "t": c["t"], "heard": c["heard"], "seen": c["seen"],
                             "similarity": c["similarity"]})

    async def _transcribe_channel(self, ch: Channel, final: bool) -> None:
        total = self.audio.n_samples
        if not final and total - ch.last_run_total < MIN_NEW_AUDIO * SAMPLE_RATE:
            return
        ch.last_run_total = total
        window = self.audio.samples(ch.committed, min(total, ch.committed + int(MAX_WINDOW * SAMPLE_RATE)), ch.index)
        if window.size < SAMPLE_RATE // 4:
            return
        offset, window_len = ch.committed / SAMPLE_RATE, window.size / SAMPLE_RATE
        try:
            result = await run_in_threadpool(
                self.transcriber.transcribe, window, glossary=self._glossary(),
                prompt=" ".join(ch.recent)[-300:] or None, language=self._language(),
                beam_size=1, word_timestamps=True,
            )
        except Exception as exc:
            log.warning("Live transcription failed: %s", exc)
            await self.send({"type": "error", "message": f"Transcription failed: {exc}"})
            return
        segments = [s for s in result["segments"] if s["text"]]
        if not self.options["language"] and segments and result.get("language"):
            self.language_votes[result["language"]] += 1
        n = split_stable(segments, window_len, final)
        for seg in segments[:n]:
            await self._commit(ch, seg, offset)
        if n:
            # Cut in the silence between the last committed and the next segment, not inside a word.
            cut = segments[n - 1]["end"] if n == len(segments) else (segments[n - 1]["end"] + segments[n]["start"]) / 2
            ch.committed += int(cut * SAMPLE_RATE)
        elif not segments and window_len > STABLE_MARGIN + 1:
            # Only silence/noise so far: skip it so the window doesn't grow forever.
            ch.committed += int((window_len - STABLE_MARGIN) * SAMPLE_RATE)
        pending = segments[n:]
        await self.send({"type": "partial", "speaker": ch.label,
                         "t": round(offset + (pending[0]["start"] if pending else window_len), 2),
                         "text": " ".join(s["text"] for s in pending),
                         "lag": round((total - ch.committed) / SAMPLE_RATE, 1)})

    async def transcribe_pending(self, final: bool = False) -> None:
        if self.audio is None:
            return
        async with self._asr_lock:
            for ch in self.channels:
                await self._transcribe_channel(ch, final)
            self.audio.trim(min(ch.committed for ch in self.channels) - SAMPLE_RATE)

    async def audio_worker(self) -> None:
        while True:
            await asyncio.sleep(STEP_SECONDS)
            await self.transcribe_pending()
            if self.job:
                self.job.stage = f"Recording {crossref.fmt_ts(time.time() - self.started)}"
            if time.time() - self.started > self.cfg.max_media_minutes * 60:
                await self.send({"type": "error", "message": "Maximum recording length reached; stopping."})
                await self.stop()
                return

    # -- screen ------------------------------------------------------------------
    async def frame_worker(self) -> None:
        while True:
            t, data = await self.frame_q.get()
            try:
                res = await run_in_threadpool(self.ocr.read_lines, data)
            except Exception as exc:
                log.warning("Live OCR failed: %s", exc)
                continue
            text = res.text
            # Skip if the readable content didn't change (cursor moved, video playing, etc.).
            if not text or crossref.similarity(text, self.last_screen_text) > 0.9:
                continue
            self.last_screen_text = text
            terms = crossref.extract_vocabulary([text], limit=25, is_common=self.transcriber.is_common_word)
            self.current_screen_terms = terms
            self.screen_terms.update(terms)
            name = f"{len(self.frames):04d}.jpg"
            if self.work:
                await run_in_threadpool((self.work / "frames" / name).write_bytes, data)
            self.frames.append({"t": round(t, 2), "image": name, "ocr_text": text, "title": res.title})
            await self.send({"type": "visual", "t": round(t, 2), "text": text, "title": res.title, "terms": terms,
                             "image": f"/api/jobs/{self.job.id}/frames/{name}" if self.job else None})

    # -- lifecycle -----------------------------------------------------------------
    async def finalize(self) -> str | None:
        """Flush audio and queue the high-accuracy pass (or discard if save=false)."""
        if self._finalized or self.audio is None:
            return None
        self._finalized = True
        await run_in_threadpool(self.audio.finish)
        job, work = self.job, self.work
        duration = self.audio.n_samples / SAMPLE_RATE
        if not self.options["save"] or duration < 1.0:
            self.jobs.delete(job.id)
            return None
        (work / "live_frames.json").write_text(json.dumps(self.frames), encoding="utf-8")
        wav = await run_in_threadpool(media.pcm16_to_wav, work / "live.pcm", work / "input.wav",
                                      self.options["channels"])
        (work / "live.pcm").unlink(missing_ok=True)
        job.status, job.stage, job.progress = "queued", "Queued", 0.0
        self.jobs.submit(job, wav)
        return job.id

    async def stop(self) -> None:
        for w in getattr(self, "_workers", [])[:1]:
            if w is not asyncio.current_task():  # the max-length check calls stop() from the worker itself
                w.cancel()
        if self.audio is not None:
            await run_in_threadpool(self.audio.finish)
            await self.transcribe_pending(final=True)
        job_id = await self.finalize()
        if job_id:
            await self.send({"type": "saved", "job_id": job_id})
        await self.send({"type": "done"})

    def _decode(self, msg: dict) -> tuple[bytes, float] | None:
        raw = msg.get("data", "")
        if not isinstance(raw, str) or len(raw) > MAX_MESSAGE_BYTES * 4 // 3:
            return None
        try:
            return base64.b64decode(raw, validate=True), float(msg.get("t", 0))
        except (binascii.Error, ValueError, TypeError):
            return None

    async def run(self) -> None:
        await self.ws.accept()
        self._workers = [asyncio.create_task(self.audio_worker())]
        if self.ocr_enabled:
            self._workers.append(asyncio.create_task(self.frame_worker()))
        ready_sent = False
        try:
            while True:
                msg = await self.ws.receive_json()
                kind = msg.get("type")
                if kind == "start" and self.audio is None:
                    self._configure(msg)
                if kind in ("start", "audio", "frame") and not ready_sent:
                    self._ensure_started()
                    ready_sent = True
                    await self.send({"type": "ready", "engine": self.transcriber.engine,
                                     "model": self.transcriber.model_name, "ocr": self.ocr_enabled,
                                     "job_id": self.job.id, "channels": self.options["channels"]})
                if kind == "stop":
                    await self.stop()
                    continue
                if kind not in ("audio", "frame"):
                    continue
                decoded = self._decode(msg)
                if decoded is None:
                    await self.send({"type": "error", "message": "Malformed or oversized message"})
                    continue
                data, t = decoded
                if kind == "audio" and data:
                    await run_in_threadpool(self.audio.feed, data)
                elif kind == "frame" and data and self.ocr_enabled:
                    if self.frame_q.full():
                        self.frame_q.get_nowait()  # keep only the newest frame
                    self.frame_q.put_nowait((t, data))
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            for w in self._workers:
                w.cancel()
            # A closed tab or dropped connection must not lose the meeting.
            try:
                await self.finalize()
            except Exception:
                log.exception("Could not save live recording")
            if self.audio is not None:
                self.audio.kill()
