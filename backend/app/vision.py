"""Keyframe selection and on-screen text extraction (OCR)."""
from __future__ import annotations

import logging
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

log = logging.getLogger(__name__)


def frame_change(a: np.ndarray, b: np.ndarray, pixel_delta: int = 24) -> float:
    """Fraction of pixels (0-1) whose brightness changed by more than ``pixel_delta``.

    Mean absolute difference is a poor signal for slides: new text on the same
    background moves the mean by ~1% while 3-5% of pixels change sharply. Counting
    sharply-changed pixels separates "new slide" from compression noise.
    """
    return float((np.abs(a.astype(np.int16) - b.astype(np.int16)) > pixel_delta).mean())


def select_keyframes(
    timestamps: np.ndarray,
    frames: np.ndarray,
    threshold: float = 0.02,
    min_gap: float = 2.0,
    max_gap: float = 60.0,
    max_keyframes: int = 150,
) -> list[int]:
    """Pick indices of frames where the picture meaningfully changed.

    A frame is kept when at least ``threshold`` of its pixels changed versus the
    *last kept* frame and ``min_gap`` seconds passed, or when ``max_gap`` seconds
    passed with no change (so long static shots still get a fresh sample).
    Comparing against the last kept frame, rather than the previous frame, also
    catches slow builds such as bullet points appearing one by one.
    """
    n = len(frames)
    if n == 0:
        return []
    keep = [0]
    scores = [1.0]
    ref = frames[0]
    for i in range(1, n):
        dt = timestamps[i] - timestamps[keep[-1]]
        if dt < min_gap:
            continue
        change = frame_change(frames[i], ref)
        if change >= threshold or dt >= max_gap:
            keep.append(i)
            scores.append(change)
            ref = frames[i]
    if len(keep) > max_keyframes:
        # Too many changes (e.g. a moving camera): keep the biggest changes, always keep the first frame.
        ranked = sorted(range(1, len(keep)), key=lambda j: scores[j], reverse=True)[: max_keyframes - 1]
        keep = [keep[0]] + sorted(keep[j] for j in ranked)
    return keep


def find_duplicates(thumbs: list[np.ndarray], threshold: float = 0.004) -> list[int | None]:
    """For each keyframe, the index of an earlier, visually identical keyframe (or None).

    Catches the periodic samples of a static shot and a presenter flipping back to
    an earlier slide, so their OCR can be reused instead of recomputed.
    """
    out: list[int | None] = []
    for i, thumb in enumerate(thumbs):
        dup = None
        for j in range(i - 1, -1, -1):
            if out[j] is None and frame_change(thumb, thumbs[j]) <= threshold:
                dup = j
                break
        out.append(dup)
    return out


@dataclass
class OcrLine:
    text: str
    score: float
    x: float
    y: float
    height: float


@dataclass
class OcrResult:
    lines: list[OcrLine] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    @property
    def title(self) -> str:
        return detect_title(self.lines)


def is_wordy(text: str) -> bool:
    """Mostly letters, like a heading - not an equation ("2x²-x-3=0"), a code or an icon."""
    compact = text.replace(" ", "")
    letters = sum(c.isalpha() for c in compact)
    return letters >= 3 and letters / max(1, len(compact)) >= 0.6 and len(text) <= 90


def detect_title(lines: list[OcrLine], min_ratio: float = 1.25) -> str:
    """The slide title: the tallest wordy text (up to 3 lines) if it clearly stands out,
    otherwise a first line written as a heading (ALL CAPS, 2+ words)."""
    wordy = [ln for ln in lines if is_wordy(ln.text)]
    if not wordy:
        return ""
    tallest = max(ln.height for ln in wordy)
    title_lines = sorted((ln for ln in wordy if ln.height >= 0.85 * tallest), key=lambda ln: (ln.y, ln.x))
    body = sorted(ln.height for ln in lines if ln.height < 0.85 * tallest)
    if body and len(title_lines) <= 3 and tallest >= min_ratio * body[len(body) // 2]:
        return " ".join(ln.text for ln in title_lines)[:120]
    if len(lines) == 1:
        return lines[0].text  # a lone short line (wordy, see above) is the title
    first = wordy[0]
    if len(first.text.split()) >= 2 and first.text.upper() == first.text:
        return first.text[:120]
    return ""  # uniform text (a document, code, chat): no title


class OcrEngine:
    """Lazily-loaded, thread-safe wrapper around RapidOCR (ONNX, CPU, no system deps)."""

    def __init__(self, min_confidence: float = 0.6, threads: int = 4):
        self.min_confidence = min_confidence
        self.threads = threads
        self._engine = None
        self._lock = threading.Lock()
        self.available: bool | None = None

    def _load(self):
        if self._engine is None and self.available is not False:
            try:
                from rapidocr import RapidOCR

                # Tuned on a 16-core laptop: the defaults (all cores, no size cap, angle
                # classifier on) took 1-20 s per 720p frame with wild variance from thread
                # oversubscription; these settings give a steady ~0.4 s with identical text.
                self._engine = RapidOCR(params={
                    "Global.log_level": "warning",
                    "Global.use_cls": False,  # slides/screens are upright
                    "Det.limit_type": "max",
                    "Det.limit_side_len": 960,
                    "EngineConfig.onnxruntime.intra_op_num_threads": self.threads,
                    "EngineConfig.onnxruntime.inter_op_num_threads": 1,
                })
                self.available = True
            except Exception as exc:  # pragma: no cover - depends on install
                log.warning("OCR unavailable: %s", exc)
                self.available = False
        return self._engine

    def warm_up(self) -> bool:
        with self._lock:
            return self._load() is not None

    def read_lines(self, image: Path | bytes) -> OcrResult:
        with self._lock:
            engine = self._load()
            if engine is None:
                return OcrResult()
            result = engine(str(image) if isinstance(image, Path) else image)
        txts = getattr(result, "txts", None) or ()
        scores = getattr(result, "scores", None) or ()
        boxes = getattr(result, "boxes", None)
        lines = []
        for i, (text, score) in enumerate(zip(txts, scores)):
            if float(score) < self.min_confidence or not text.strip():
                continue
            if boxes is not None and len(boxes) == len(txts):
                box = np.asarray(boxes[i], dtype=np.float32)
                x, y = float(box[:, 0].min()), float(box[:, 1].min())
                height = float(box[:, 1].max() - box[:, 1].min())
            else:
                x, y, height = 0.0, float(i), 0.0
            lines.append(OcrLine(text.strip(), float(score), x, y, height))
        # Reading order: top-to-bottom, then left-to-right (rows bucketed to ~20 px).
        lines.sort(key=lambda ln: (round(ln.y / 20), ln.x))
        return OcrResult(lines)

    def read(self, image: Path | bytes) -> str:
        return self.read_lines(image).text


class OcrPool:
    """Several OCR engines used in parallel.

    One engine with 4 threads was the sweet spot per frame (more threads made it
    slower); running two such engines side by side keeps more cores busy on long
    videos without that oversubscription.
    """

    def __init__(self, workers: int = 2, min_confidence: float = 0.6, threads: int = 4):
        self.engines = [OcrEngine(min_confidence, threads) for _ in range(max(1, workers))]
        self._free: queue.Queue[OcrEngine] = queue.Queue()
        for engine in self.engines:
            self._free.put(engine)

    @property
    def available(self) -> bool | None:
        return self.engines[0].available

    def warm_up(self) -> bool:
        return self.engines[0].warm_up()

    def read_lines(self, image: Path | bytes) -> OcrResult:
        engine = self._free.get()
        try:
            return engine.read_lines(image)
        finally:
            self._free.put(engine)

    def read(self, image: Path | bytes) -> str:
        return self.read_lines(image).text

    def read_many(self, images: list[Path], progress: Callable[[int], None] | None = None) -> list[OcrResult]:
        results: list[OcrResult | None] = [None] * len(images)
        done = 0
        lock = threading.Lock()

        def work(i: int) -> None:
            nonlocal done
            results[i] = self.read_lines(images[i])
            with lock:
                done += 1
                if progress:
                    progress(done)

        pool = ThreadPoolExecutor(max_workers=len(self.engines), thread_name_prefix="ocr")
        try:
            for future in [pool.submit(work, i) for i in range(len(images))]:
                future.result()  # re-raise errors (including cancellation from progress)
        except BaseException:
            pool.shutdown(wait=True, cancel_futures=True)  # don't OCR the rest after a cancel
            raise
        pool.shutdown(wait=True)
        return [r or OcrResult() for r in results]
