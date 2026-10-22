"""Batch pipeline: media file -> transcript cross-referenced with on-screen content.

Stages (video):                         Stages (audio only):
  1. probe                                1. probe
  2. decode 16 kHz audio                  2. decode 16 kHz audio
  3. detect scene changes                 3. transcribe (user glossary)
  4. extract keyframes (duplicates skip)  4. diarize speakers
  5. OCR in parallel (+ slide titles)     5. build notes context
  6. optional AI captions
  7. transcribe, biased with on-screen vocabulary
  8. diarize speakers
  9. cross-reference speech <-> visuals

Long videos (10 minutes or more) run steps 3-6 on the CPU in a background thread
while the GPU transcribes: a sample of 16 frames spread over the video is read first,
so the speech model still gets the slides' vocabulary as spelling hints.

Live meetings reuse this pipeline after they end: the recorded audio (one channel per
side when "you" and "others" were captured separately) and the screen frames already
read during the meeting are passed in, so only steps 7-9 run.
"""
from __future__ import annotations

import logging
import shutil
import threading
import time
from bisect import bisect_left, bisect_right
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from . import crossref, llm, media
from .config import Settings
from .diarization import Diarizer, talk_times
from .transcriber import Transcriber
from .vision import OcrLine, OcrPool, OcrResult, detect_title, find_duplicates, select_keyframes

log = logging.getLogger(__name__)

Report = Callable[[str, float], None]  # (stage message, overall progress 0..1); may raise to cancel
Progress = Callable[[str, str, float], None]  # (stage, message, fraction of that stage)
RESULT_VERSION = 3
OVERLAP_MIN_SECONDS = 600  # shorter videos are read first, then transcribed
GLOSSARY_SAMPLES = 16  # frames read up front for the speech model's spelling hints
VISUAL_STAGES = ("scenes", "keyframes", "ocr", "captions")


@dataclass
class JobOptions:
    language: str | None = None          # None = auto-detect
    glossary: str = ""                   # user terms, comma or newline separated
    diarize: bool = True
    num_speakers: int | None = None      # known speaker count improves diarization
    describe_visuals: bool = False       # AI captions for keyframes (needs VISION_MODEL)
    title: str = ""
    channel_labels: list[str] = field(default_factory=list)  # e.g. ["You", "Others"]

    @classmethod
    def from_dict(cls, data: dict | None) -> "JobOptions":
        known = {k: v for k, v in (data or {}).items() if k in cls.__dataclass_fields__}
        return cls(**known)


@dataclass
class Engines:
    transcriber: Transcriber
    ocr: OcrPool
    diarizer: Diarizer | None


class Stages:
    """Maps per-stage progress onto one 0..1 bar using relative stage weights.

    Stages run in the declared order, except ``background`` ones, which run alongside
    the others (slides are read on the CPU while the GPU transcribes). The background
    thread only calls ``update``; the bar is reported from the pipeline thread, with
    what the background is doing appended to the message.
    """

    def __init__(self, report: Report, weights: dict[str, float], background: tuple[str, ...] = ()):
        self.report = report
        self.weights = weights
        self.total = sum(weights.values()) or 1.0
        self.background = set(background)
        self.fraction = dict.fromkeys(weights, 0.0)
        self.note = ""
        self._lock = threading.Lock()

    def update(self, stage: str, fraction: float, note: str = "") -> None:
        with self._lock:
            self.fraction[stage] = max(0.0, min(fraction, 1.0))
            self.note = note

    def finish_background(self) -> None:
        with self._lock:
            for name in self.background & set(self.weights):
                self.fraction[name] = 1.0
            self.note = ""

    def __call__(self, stage: str, label: str, fraction: float = 0.0) -> None:
        with self._lock:
            if stage in self.weights and stage not in self.background:
                before = True  # earlier stages are done, later ones not started
                for name in self.weights:
                    if name == stage:
                        before = False
                    elif name not in self.background:
                        self.fraction[name] = 1.0 if before else 0.0
            if stage in self.weights:
                self.fraction[stage] = max(0.0, min(fraction, 1.0))
            overall = sum(self.weights[n] * f for n, f in self.fraction.items()) / self.total
            note = self.note
        self.report(f"{label} · {note}" if note and note != label else label, min(0.99, overall))


class VisualsStopped(Exception):
    """The background reading of the video was stopped (the job was cancelled or failed)."""


def merge_channels(channels: list[tuple[str, list[dict], list[dict] | None]]) -> tuple[list[dict], list[dict]]:
    """Merge per-channel transcripts into one timeline with speakers.

    ``channels`` is [(label, segments, speakers_or_None)]. A channel without its own
    diarization is one speaker named after the label ("You"). Diarized channels keep
    their sub-speakers ("Others 1", "Others 2"). Echo removal: when the microphone
    picks up the meeting audio, the "You" channel repeats what others said; a segment
    is dropped when it overlaps a segment from another channel with similar words.
    """
    speakers: list[dict] = []
    tagged: list[tuple[int, dict]] = []
    for ch, (label, segments, sub_speakers) in enumerate(channels):
        if sub_speakers and len(sub_speakers) > 1:
            mapping = {}
            for k, sub in enumerate(sub_speakers, start=1):
                sid = f"S{len(speakers) + 1}"
                mapping[sub["id"]] = sid
                speakers.append({"id": sid, "name": f"{label} {k}"})
            for seg in segments:
                tagged.append((ch, {**seg, "speaker": mapping.get(seg.get("speaker"))}))
        else:
            sid = f"S{len(speakers) + 1}"
            speakers.append({"id": sid, "name": label})
            tagged.extend((ch, {**seg, "speaker": sid}) for seg in segments)

    def words(seg: dict) -> str:
        return " ".join(crossref.norm(w) for w in crossref.tokenize(seg["text"]))

    others = sorted((seg for ch, seg in tagged if ch != 0), key=lambda s: s["start"])
    starts = [s["start"] for s in others]
    kept: list[dict] = []
    for ch, seg in tagged:
        if ch == 0 and others:
            # Only segments that overlap in time (segments are <= 15 s long) can be echoes.
            lo, hi = bisect_left(starts, seg["start"] - 30), bisect_right(starts, seg["end"] + 0.5)
            mine = words(seg)
            if any(o["end"] > seg["start"] - 0.5 and crossref.similarity(mine, words(o)) >= 0.6
                   for o in others[lo:hi]):
                continue
        kept.append(seg)
    merged = sorted(kept, key=lambda s: (s["start"], s["end"]))
    for i, seg in enumerate(merged):
        seg["id"] = i
    used = {s["speaker"] for s in merged}
    return merged, [s for s in speakers if s["id"] in used]


def sample_screen_text(src: Path, info: media.MediaInfo, work_dir: Path, ocr: OcrPool,
                       count: int = GLOSSARY_SAMPLES, progress: Callable[[float], None] | None = None,
                       ) -> tuple[list[str], set[str]]:
    """On-screen text of ``count`` frames spread over the video, interface text removed
    (returned too).

    Enough to give the speech model the slides' vocabulary without waiting for every
    scene to be read.
    """
    sample_dir = work_dir / "sample"
    sample_dir.mkdir(exist_ok=True)
    try:
        paths = [sample_dir / f"{i:02d}.jpg" for i in range(count)]
        times = [(i + 0.5) * info.duration / count for i in range(count)]
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="frames") as pool:
            list(pool.map(lambda job: media.extract_frame(src, *job), zip(times, paths)))
        results = ocr.read_many(paths, progress=(lambda n: progress(n / count)) if progress else None)
    finally:
        shutil.rmtree(sample_dir, ignore_errors=True)
    lines = [[line.text for line in r.lines] for r in results]
    chrome = crossref.find_chrome(lines)
    return [crossref.strip_chrome("\n".join(frame), chrome) for frame in lines], chrome


def read_video(src: Path, info: media.MediaInfo, cfg: Settings, ocr: OcrPool, frames_dir: Path,
               frame_url: Callable[[str], str], captions: bool, progress: Progress,
               stop: Callable[[], bool] = lambda: False,
               ) -> tuple[list[crossref.Keyframe], list[list[str]], set[str], dict[str, float]]:
    """Scenes -> keyframes -> OCR (interface text removed, slide titles) -> optional captions.

    Returns (keyframes, each frame's OCR lines, interface-text keys, timings). ``stop``
    is checked between steps and while ffmpeg runs; it raises ``VisualsStopped``.
    """
    timings: dict[str, float] = {}
    clock = time.perf_counter()

    def lap(name: str) -> None:
        nonlocal clock
        now = time.perf_counter()
        timings[name] = round(now - clock, 2)
        clock = now

    def check() -> None:
        if stop():
            raise VisualsStopped()

    # Long recordings: decode only the encoder's keyframes (4.6x faster on a 1080p60
    # class recording); scene boundaries are then accurate to one keyframe interval.
    fast = info.duration > 20 * 60 and (media.keyframe_interval(src) or 99) <= 6
    progress("scenes", "Detecting scene changes" + (" (fast scan)" if fast else ""), 0.0)
    try:
        timestamps, thumbs = media.sample_gray_frames(src, cfg.video_sample_fps, keyframes_only=fast, stop=stop)
    except media.MediaError:
        check()  # stopped on purpose
        raise
    indices = select_keyframes(timestamps, thumbs, cfg.scene_threshold, cfg.scene_min_gap,
                               cfg.scene_max_gap, cfg.max_keyframes)
    dups = find_duplicates([thumbs[i] for i in indices])
    # A periodic sample identical to the previous keyframe is not a new scene.
    picked = [(i, d) for n, (i, d) in enumerate(zip(indices, dups)) if not (d is not None and d == n - 1)]
    lap("scene_detection")
    frames_dir.mkdir(exist_ok=True)
    position = {orig: n for n, (orig, _) in enumerate(picked)}
    keyframes: list[crossref.Keyframe] = []
    unique: list[crossref.Keyframe] = []
    for n, (idx, dup) in enumerate(picked):
        dup_of = position.get(indices[dup]) if dup is not None else None
        name = f"{n:04d}.jpg" if dup_of is None else f"{dup_of:04d}.jpg"
        kf = crossref.Keyframe(id=n, t=float(timestamps[idx]), duplicate_of=dup_of, image=frame_url(name))
        keyframes.append(kf)
        if dup_of is None:
            unique.append(kf)

    # Extract the frames 4 at a time (each one is a separate ffmpeg seek).
    pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="frames")
    try:
        futures = [pool.submit(media.extract_frame, src, min(kf.t + 0.5, max(info.duration - 0.1, 0)),
                               frames_dir / f"{kf.id:04d}.jpg") for kf in unique]
        for done, future in enumerate(as_completed(futures), start=1):
            future.result()
            check()
            progress("keyframes", f"Extracting keyframes ({done}/{len(unique)})", done / len(unique))
    finally:
        pool.shutdown(wait=True, cancel_futures=True)  # a cancel skips the remaining seeks
    lap("keyframe_extraction")

    screen_lines: list[list[str]] = []
    chrome: set[str] = set()
    if cfg.ocr_enabled and unique:
        def ocr_progress(count: int) -> None:
            check()
            progress("ocr", f"Reading on-screen text ({count}/{len(unique)})", count / len(unique))

        results = ocr.read_many([frames_dir / f"{kf.id:04d}.jpg" for kf in unique], progress=ocr_progress)
        # Video-call and app chrome ("Mute", "Share", participant names) is on almost
        # every frame; keep it out of titles, bullets, the glossary and the AI context.
        screen_lines = [[line.text for line in r.lines] for r in results]
        chrome = crossref.find_chrome(screen_lines)
        for kf, res in zip(unique, results):
            clean = OcrResult([line for line in res.lines if not crossref.is_noise_line(line.text)
                               and not crossref.is_chrome(line.text, chrome)])
            kf.ocr_text, kf.title = clean.text, clean.title
        for kf in keyframes:
            if kf.duplicate_of is not None:
                kf.ocr_text, kf.title = keyframes[kf.duplicate_of].ocr_text, keyframes[kf.duplicate_of].title
        lap("ocr")

    if captions and unique:
        # Caption the frames with the least text first (charts, demos), capped for cost.
        chosen = sorted(unique, key=lambda k: len(k.ocr_text))[: cfg.vision_max_frames]
        for n, kf in enumerate(chosen):
            check()
            progress("captions", f"Describing visuals ({n + 1}/{len(chosen)})", n / len(chosen))
            try:
                kf.caption = llm.caption_image(frames_dir / f"{kf.id:04d}.jpg", kf.ocr_text)
            except Exception as exc:
                log.warning("Captioning frame %s failed: %s", kf.id, exc)
        lap("captions")
    return keyframes, screen_lines, chrome, timings


def process_media(
    src: Path,
    filename: str,
    work_dir: Path,
    engines: Engines,
    cfg: Settings,
    report: Report,
    frame_url: Callable[[str], str],
    options: JobOptions | None = None,
    preset_keyframes: list[dict] | None = None,
) -> dict:
    options = options or JobOptions()
    transcriber = engines.transcriber
    timings: dict[str, float] = {}
    started = clock = time.perf_counter()

    def lap(name: str | None) -> None:
        nonlocal clock
        now = time.perf_counter()
        if name:
            timings[name] = round(now - clock, 2)
        clock = now

    report("Inspecting file", 0.0)
    info = media.probe(src)
    lap("probe")
    if not info.has_audio and not info.has_video:
        raise media.MediaError("No audio or video stream found in this file.")
    is_video = info.has_video and cfg.video_enabled and preset_keyframes is None
    # Long videos: read the slides on the CPU while the GPU transcribes.
    overlap = is_video and info.has_audio and info.duration >= OVERLAP_MIN_SECONDS
    diarize = bool(options.diarize and cfg.diarization and engines.diarizer and info.has_audio)
    captions = bool(options.describe_visuals and cfg.vision_enabled)
    detect = info.has_audio and not options.language
    stage = Stages(report, {
        "decode": 2,
        "sample": 3 if overlap and cfg.ocr_enabled else 0,
        "scenes": 4 if is_video else 0,
        "keyframes": 3 if is_video else 0,
        "ocr": 25 if is_video and cfg.ocr_enabled else 0,
        "captions": 6 if captions else 0,
        "language": 2 if detect else 0,
        "transcribe": 45,
        "diarize": 8 if diarize else 0,
        "wait": 0,
        "xref": 1,
    }, background=VISUAL_STAGES if overlap else ())

    # -- audio -----------------------------------------------------------------
    channel_audio: list[np.ndarray] = []
    if info.has_audio:
        stage("decode", "Decoding audio")
        if len(options.channel_labels) > 1 and info.audio_channels >= len(options.channel_labels):
            channel_audio = [media.decode_audio(src, channel=i) for i in range(len(options.channel_labels))]
        else:
            channel_audio = [media.decode_audio(src)]
        lap("decode_audio")

    # -- visuals ---------------------------------------------------------------
    keyframes: list[crossref.Keyframe] = []
    chrome: set[str] = set()
    screen_lines: list[list[str]] = []  # every frame's OCR lines, to find the interface text
    hint_texts: list[str] | None = None  # on-screen text the spelling hints come from
    hint_chrome: set[str] = set()
    visuals = None  # (future, stop event) while the video is read in the background
    frames_dir = work_dir / "frames"
    if preset_keyframes:
        frames = sorted(preset_keyframes, key=lambda k: k["t"])
        screen_lines = [k.get("ocr_text", "").splitlines() for k in frames]
        chrome = crossref.find_chrome(screen_lines)
        for i, k in enumerate(frames):
            text = crossref.strip_chrome(k.get("ocr_text", ""), chrome)
            title = k.get("title", "")
            if not title or crossref.is_chrome(title, chrome):
                title = detect_title([OcrLine(line, 1.0, 0, n, 0) for n, line in enumerate(text.splitlines())])
            keyframes.append(crossref.Keyframe(id=i, t=float(k["t"]), image=frame_url(k["image"]),
                                               ocr_text=text, title=title))
    elif overlap:
        if cfg.ocr_enabled:
            hint_texts, hint_chrome = sample_screen_text(
                src, info, work_dir, engines.ocr, GLOSSARY_SAMPLES,
                lambda f: stage("sample", "Reading a sample of the slides", f))
            lap("slide_sample")
        stop = threading.Event()
        runner = ThreadPoolExecutor(max_workers=1, thread_name_prefix="visuals")
        future = runner.submit(read_video, src, info, cfg, engines.ocr, frames_dir, frame_url, captions,
                               lambda name, label, f: stage.update(name, f, label), stop.is_set)
        runner.shutdown(wait=False)  # the thread finishes the work; the future is joined below
        future.add_done_callback(lambda _: stage.finish_background())
        visuals = (future, stop)
    elif is_video:
        keyframes, screen_lines, chrome, visual_timings = read_video(
            src, info, cfg, engines.ocr, frames_dir, frame_url, captions, stage)
        timings.update(visual_timings)
        lap(None)

    try:
        # -- vocabulary -> glossary --------------------------------------------
        user_terms = crossref.parse_user_glossary(options.glossary)
        if hint_texts is None:
            hint_texts, hint_chrome = [k.ocr_text for k in keyframes if k.duplicate_of is None], chrome
        hints = crossref.extract_vocabulary(hint_texts, cfg.vocabulary_size, is_common=transcriber.is_common_word,
                                            exclude=crossref.chrome_words(hint_chrome))
        glossary = crossref.build_glossary(user_terms + hints)

        # -- language ----------------------------------------------------------
        # Whisper alone decides from the first 30 s; a Taglish class that opened with an
        # English greeting was then decoded as English for 2.5 hours (", so," on every line).
        language = options.language
        detection = {"language": language, "probability": 1.0, "method": "chosen"} if language else None
        if detect and channel_audio:
            stage("language", "Detecting the language")
            loudest = max(channel_audio, key=lambda a: float(np.mean(a[::50] ** 2)) if a.size else 0.0)
            detection = transcriber.detect_language(loudest)
            language = detection["language"]
            lap("language_detection")

        # -- speech ------------------------------------------------------------
        channel_results: list[tuple[str, list[dict], list[dict] | None]] = []
        labels = options.channel_labels if len(channel_audio) > 1 else [""]
        for ch, audio in enumerate(channel_audio):
            part = (ch, len(channel_audio))
            label = f"Transcribing {labels[ch]}" if labels[ch] else "Transcribing speech"
            stage("transcribe", label, ch / part[1])
            asr = transcriber.transcribe(
                audio, glossary=glossary, language=language,
                progress=lambda p, part=part, label=label: stage("transcribe", label, (part[0] + p) / part[1]),
            )
            language = language or asr["language"]
            channel_results.append((labels[ch], asr["segments"], None))
        lap("transcription")

        # Speakers: one voice print per sentence, clustered. A channel known to be one
        # person ("You") is skipped.
        for ch, (label, segments, _) in enumerate(channel_results):
            if not (diarize and segments and label != "You"):
                continue
            part = (ch, len(channel_results))
            stage("diarize", "Identifying speakers", ch / part[1])
            try:
                segments, sub_speakers = engines.diarizer.label_segments(
                    channel_audio[ch], segments,
                    num_speakers=options.num_speakers if len(channel_audio) == 1 else None,
                    progress=lambda p, part=part: stage("diarize", "Identifying speakers", (part[0] + p) / part[1]),
                )
                channel_results[ch] = (label, segments, sub_speakers)
            except Exception as exc:
                if exc.__class__.__name__ == "JobCancelled":
                    raise
                log.warning("Speaker identification failed, continuing without speakers: %s", exc)
        if diarize:
            lap("speakers")

        if visuals:
            while True:
                try:
                    keyframes, screen_lines, chrome, visual_timings = visuals[0].result(timeout=0.5)
                    break
                except FuturesTimeout:
                    stage("wait", stage.note or "Reading on-screen text")
            timings.update(visual_timings)
            lap("waiting_for_slides")
    except BaseException:
        if visuals:  # stop reading the video too, then let the error (or the cancel) through
            visuals[1].set()
            try:
                visuals[0].result(timeout=60)
            except BaseException:
                pass
        raise

    if len(channel_results) > 1:
        segments, speakers = merge_channels(channel_results)
    elif channel_results:
        segments, speakers = channel_results[0][1], channel_results[0][2] or []
    else:
        segments, speakers = [], []
    totals = talk_times(segments)
    for spk in speakers:
        spk["talk_time"] = totals.get(spk["id"], 0.0)

    # -- cross-reference -------------------------------------------------------
    stage("xref", "Cross-referencing audio and video")
    interface_words = crossref.chrome_words(chrome)
    vocabulary = crossref.extract_vocabulary([k.ocr_text for k in keyframes if k.duplicate_of is None],
                                             cfg.vocabulary_size, is_common=transcriber.is_common_word,
                                             exclude=interface_words)
    seg_objs = [crossref.Segment(id=s["id"], start=s["start"], end=s["end"], text=s["text"],
                                 speaker=s.get("speaker"), words=s.get("words")) for s in segments]
    xref = crossref.cross_reference(seg_objs, keyframes, info.duration, is_common=transcriber.is_common_word,
                                    extra_terms=user_terms, exclude=interface_words)
    lap("cross_reference")
    timings["total"] = round(time.perf_counter() - started, 2)

    result = {
        "version": RESULT_VERSION,
        "filename": filename,
        "title": options.title or Path(filename).stem,
        "options": asdict(options),
        "media": info.as_dict(),
        "language": language,
        "language_probability": (detection or {}).get("probability"),
        "language_detection": detection,
        "screen_chrome": crossref.chrome_labels(screen_lines, chrome),
        "engine": transcriber.engine,
        "model": transcriber.model_name,
        "device": transcriber.device,
        "segments": [{**asdict(s), "edited": False} for s in seg_objs],
        "speakers": speakers,
        "keyframes": [asdict(k) for k in xref["scenes"]],
        "vocabulary": vocabulary,
        "glossary": glossary,
        "corrections": xref["corrections"],
        "timings": timings,
    }
    result["text"] = " ".join(s["text"] for s in result["segments"]).strip()
    result["stats"] = crossref.compute_stats(result)
    result["notes_context"] = crossref.build_notes_context(result, cfg.llm_context_chars)
    return result
