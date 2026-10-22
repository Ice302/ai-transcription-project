"""Speech-to-text engines.

``faster-whisper`` (CTranslate2, int8 on CPU) is preferred: measured 2.1x faster than
``openai-whisper`` on CPU and 5.1x on an RTX 4050 (docs/PERFORMANCE.md), uses less
memory, has a built-in VAD that suppresses the classic "Thank you." hallucinations on
silence, and streams segments so we can report real progress. ``openai-whisper`` is
kept as a fallback.

Vocabulary biasing: the on-screen glossary is passed as ``hotwords`` (faster-whisper)
or as a *carried* initial prompt (openai-whisper). Both re-send the glossary with every
30-second window. A plain ``initial_prompt`` only reaches the first window or two
before the decoder's own output pushes it out of the prompt, which silently disabled
the glossary for most of a long recording.
"""
from __future__ import annotations

import functools
import logging
import os
import re
import subprocess
import threading
from pathlib import Path
from typing import Callable

import numpy as np

from .media import SAMPLE_RATE, decode_audio

log = logging.getLogger(__name__)

ProgressFn = Callable[[float], None]
Word = tuple[float, float, str, float]  # start, end, text (with leading space), probability

SENTENCE_END = (".", "?", "!", "。", "？", "！")
LOW_CONFIDENCE = 0.5


def _add_cuda_dll_dirs() -> None:
    """On Windows, make pip-installed NVIDIA runtimes (nvidia-cublas-cu12, nvidia-cudnn-cu12) loadable."""
    if os.name != "nt":
        return
    try:
        import nvidia  # namespace package created by the nvidia-* wheels
    except ImportError:
        return
    for base in getattr(nvidia, "__path__", []):
        for bin_dir in Path(base).glob("*/bin"):
            os.add_dll_directory(str(bin_dir))
            os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"


def _detect_device(requested: str) -> str:
    if requested != "auto":
        return requested
    try:
        import ctranslate2

        return "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    except Exception:
        return "cpu"


@functools.lru_cache(maxsize=1)
def gpu_memory_gb() -> float:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL)
        return max(float(v) for v in out.stdout.split()) / 1024
    except Exception:
        return 0.0


def resolve_model(name: str, device: str, live: bool = False) -> str:
    """Turn ``auto`` into a concrete model for the device.

    large-v3-turbo is far more accurate than base and still much faster than realtime
    on a 6 GB laptop GPU (docs/PERFORMANCE.md); on CPU it would be too slow. Live mode
    gets a smaller, faster model for the running preview: every meeting is re-done
    with the main model afterwards, and a second turbo instance would not fit next to
    the first in 6 GB of VRAM.
    """
    if name != "auto":
        return name
    if device == "cuda":
        vram = gpu_memory_gb()
        if live:
            return "small" if vram >= 3 else "base"
        if vram >= 5:
            return "large-v3-turbo"
        return "small" if vram >= 3 else "base"
    return "base"


def merge_punctuation(words: list[Word]) -> list[Word]:
    """Attach punctuation-only tokens to the previous word (leading ones are dropped).

    Whisper sometimes emits "," or "." as separate words. Left alone they produce
    lines like ", so," and break repeat detection ("so , so , so" is not "so so so").
    """
    out: list[Word] = []
    for start, end, text, prob in words:
        if not re.search(r"\w", text):
            if out:
                s, _, t, p = out[-1]
                out[-1] = (s, max(end, out[-1][1]), t + text.strip(), p)
            continue
        out.append((start, end, text, prob))
    return out


def aggregate_language_votes(votes: list[list[tuple[str, float]]]) -> tuple[str | None, float, list[tuple[str, float]]]:
    """Average per-window language probabilities -> (best language, its share, ranked candidates)."""
    totals: dict[str, float] = {}
    for probs in votes:
        for lang, p in probs:
            totals[lang] = totals.get(lang, 0.0) + float(p)
    if not totals:
        return None, 0.0, []
    ranked = sorted(((lang, round(p / len(votes), 3)) for lang, p in totals.items()), key=lambda x: -x[1])
    return ranked[0][0], ranked[0][1], ranked[:5]


def speech_windows(audio: np.ndarray, count: int = 8, seconds: int = 30) -> list[tuple[float, np.ndarray]]:
    """Up to ``count`` windows spread over the whole recording, preferring ones full of speech.

    Returns (speech ratio, samples) pairs in time order. Detecting the language from
    the first 30 s alone failed on a 2.5 h Taglish class that opened with an English
    greeting: everything was then decoded as English and came out as ", so,".
    """
    win = seconds * SAMPLE_RATE
    if audio.size <= win:
        return [(1.0, audio)]
    candidates = min(count * 3, audio.size // win)
    starts = np.linspace(0, audio.size - win, num=candidates).astype(int)
    try:
        from faster_whisper.vad import VadOptions, get_speech_timestamps

        options = VadOptions(min_silence_duration_ms=500)

        def score(chunk: np.ndarray) -> float:
            return sum(t["end"] - t["start"] for t in get_speech_timestamps(chunk, options)) / chunk.size
    except Exception:  # no VAD available: fall back to loudness
        def score(chunk: np.ndarray) -> float:
            return float(np.sqrt(np.mean(chunk[::8] ** 2)))
    scored = [(score(audio[s:s + win]), s) for s in starts]
    best = sorted(scored, key=lambda x: -x[0])[:count]
    return [(ratio, audio[s:s + win]) for ratio, s in sorted(best, key=lambda x: x[1]) if ratio > 0] or \
        [(0.0, audio[starts[0]:starts[0] + win])]


def collapse_repeats(words: list[Word], max_phrase: int = 6) -> list[Word]:
    """Remove decoder loops: a phrase repeated 3+ times in a row (a single word 4+ times) is kept once.

    ("Thank you. Thank you. Thank you." or "the the the the" are classic Whisper
    hallucinations on noise; "very very very" in real speech is left alone.)
    """
    norm = [re.sub(r"[^\w]", "", w[2].lower()) for w in words]
    out: list[Word] = []
    i = 0
    while i < len(words):
        collapsed = False
        for n in range(1, max_phrase + 1):
            phrase = norm[i:i + n]
            if len(phrase) < n:
                break
            if not all(phrase):
                continue
            k = 1
            while norm[i + k * n:i + (k + 1) * n] == phrase:
                k += 1
            if k >= (4 if n == 1 else 3):
                out.extend(words[i:i + n])
                i += k * n
                collapsed = True
                break
        if not collapsed:
            out.append(words[i])
            i += 1
    return out


def resegment(words: list[Word], max_words: int = 40, max_gap: float = 0.8, max_duration: float = 15.0) -> list[dict]:
    """Split word-timed output into sentence-sized segments.

    Whisper often emits a single segment spanning 20-30 s, which is too coarse to
    line up with slide changes or speaker turns. Cutting at sentence ends, pauses
    and a length cap gives segments that each belong clearly to one scene.
    """
    segments: list[dict] = []
    current: list[Word] = []

    def flush():
        if current:
            text = "".join(w[2] for w in current).strip().lstrip(",.;:!?… ")
            if re.search(r"\w", text):
                segments.append({
                    "id": len(segments), "start": round(current[0][0], 2), "end": round(current[-1][1], 2),
                    "text": text,
                    "words": [[round(s, 2), round(e, 2), t, round(float(p), 2)] for s, e, t, p in current],
                })
            current.clear()

    for i, word in enumerate(words):
        if current and (word[0] - current[-1][1] > max_gap or word[1] - current[0][0] > max_duration):
            flush()
        current.append(word)
        if word[2].strip().endswith(SENTENCE_END) or len(current) >= max_words or i + 1 == len(words):
            flush()
    return segments


class Transcriber:
    def __init__(self, model_name: str = "auto", engine: str = "auto", device: str = "auto",
                 compute_type: str = "auto", cpu_threads: int = 0, beam_size: int = 5,
                 language: str | None = None, word_timestamps: bool = True, live: bool = False,
                 batch_size: int = 0):
        self.requested_model = model_name
        self.live = live
        self.device = _detect_device(device)
        self.model_name = resolve_model(model_name, self.device, live)
        self.beam_size = beam_size
        self.language = language
        self.word_timestamps = word_timestamps
        self.batch_size_setting = batch_size
        self._batched = None
        # One model instance is not safe to call from several threads at once.
        self._lock = threading.Lock()
        self.engine = ""
        self._model = None

        if engine in ("auto", "faster"):
            try:
                self._model = self._load_faster(compute_type, cpu_threads)
                self.engine = "faster-whisper"
            except Exception as exc:
                if engine == "faster":
                    raise
                log.warning("faster-whisper unavailable (%s); falling back to openai-whisper", exc)

        if self._model is None:
            import torch
            import whisper

            if self.device == "cuda" and not torch.cuda.is_available():
                self.device = "cpu"
                self.model_name = resolve_model(self.requested_model, "cpu", self.live)
            self._model = whisper.load_model(self.model_name, device=self.device)
            self.engine = "openai-whisper"
        log.info("Loaded %s model '%s' on %s", self.engine, self.model_name, self.device)

    def _load_faster(self, compute_type: str, cpu_threads: int):
        if self.device == "cuda":
            _add_cuda_dll_dirs()
        from faster_whisper import WhisperModel

        threads = cpu_threads or max(1, (os.cpu_count() or 4) - 1)
        devices = [self.device] + (["cpu"] if self.device != "cpu" else [])
        for device in devices:
            name = resolve_model(self.requested_model, device, self.live)
            ctype = compute_type if compute_type != "auto" else ("float16" if device == "cuda" else "int8")
            try:
                model = WhisperModel(name, device=device, compute_type=ctype, cpu_threads=threads)
                # A GPU can be detected while cuBLAS/cuDNN are missing; that only fails at
                # inference time, so run a tiny warm-up to prove the device actually works.
                segments, _ = model.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), beam_size=1)
                list(segments)
                self.device, self.model_name = device, name
                return model
            except Exception as exc:
                if device == devices[-1]:
                    raise
                log.warning("Whisper on %s failed (%s); falling back to CPU. "
                            "See docs/SETUP.md#gpu-acceleration to enable the GPU.", device, exc)

    @functools.lru_cache(maxsize=4096)
    def token_count(self, word: str) -> int | None:
        """Number of Whisper tokens for " word" - 1 means the model already knows it well."""
        try:
            if self.engine == "faster-whisper":
                return len(self._model.hf_tokenizer.encode(" " + word, add_special_tokens=False).ids)
            from whisper.tokenizer import get_tokenizer

            return len(get_tokenizer(self._model.is_multilingual).encode(" " + word))
        except Exception:
            return None

    def is_common_word(self, word: str) -> bool:
        """Plain words Whisper spells correctly anyway; glossaries should skip them.

        Judged on the lowercase form: the tokenizer splits capitalized common words
        (" Migration" is 2 tokens, " migration" is 1) and can keep a capitalized
        product name whole (" Kubernetes" is 1 token, " kubernetes" is 2).
        """
        if not word.isalpha() or (word.isupper() and len(word) > 1):
            return False  # keep acronyms, codes, numbers
        return self.token_count(word.lower()) == 1

    def _language_probs(self, window: np.ndarray) -> list[tuple[str, float]]:
        if self.engine == "faster-whisper":
            _, _, probs = self._model.detect_language(audio=window)
            return [(lang, float(p)) for lang, p in probs[:10]]
        import whisper

        mel = whisper.log_mel_spectrogram(whisper.pad_or_trim(window), n_mels=self._model.dims.n_mels)
        _, probs = self._model.detect_language(mel.to(self._model.device))
        return sorted(probs.items(), key=lambda x: -x[1])[:10]

    def _sample_score(self, sample: np.ndarray, language: str) -> float:
        """Sum of word confidences when transcribing ``sample`` in ``language`` (garbage scores low)."""
        if self.engine == "faster-whisper":
            seg_iter, _ = self._model.transcribe(sample, language=language, beam_size=1, vad_filter=True,
                                                 word_timestamps=True, condition_on_previous_text=False)
            return round(sum(w.probability for s in seg_iter for w in (s.words or [])), 2)
        result = self._model.transcribe(sample, language=language, fp16=self.device == "cuda", word_timestamps=True)
        return round(sum(w.get("probability", 0) for s in result["segments"] for w in s.get("words", [])), 2)

    def detect_language(self, audio: np.ndarray) -> dict:
        """Dominant language of a whole recording, robust to an opening in another language.

        Votes over speech-rich windows from across the file. When the vote is not
        clear-cut (mixed-language speech such as Taglish), a speech sample is
        transcribed in the top two languages and the one producing more confidently
        recognised words wins.
        """
        windows = speech_windows(audio)
        with self._lock:
            votes = [self._language_probs(w) for _, w in windows]
            language, probability, candidates = aggregate_language_votes(votes)
            result = {"language": language, "probability": probability, "candidates": candidates,
                      "windows": len(windows), "method": "vote"}
            if language and probability < 0.85 and len(candidates) > 1 and candidates[1][1] >= 0.08:
                dense = sorted(windows, key=lambda x: -x[0])[:2]
                sample = np.concatenate([w for _, w in dense])
                scores = {lang: self._sample_score(sample, lang) for lang, _ in candidates[:2]}
                best = max(scores, key=scores.get)
                result.update(method="trial", trial_scores=scores, language=best,
                              probability=dict(candidates).get(best, probability))
        log.info("Language: %s (%s)", result["language"], result)
        return result

    def transcribe(self, audio: Path | str | bytes | np.ndarray, *, glossary: str | None = None,
                   prompt: str | None = None, language: str | None = None, beam_size: int | None = None,
                   progress: ProgressFn | None = None, vad: bool = True,
                   word_timestamps: bool | None = None) -> dict:
        """Transcribe a file path, encoded bytes (e.g. a webm chunk) or 16 kHz float32 samples.

        ``glossary`` biases spelling for the whole file; ``prompt`` is preceding context
        (e.g. the last sentences in live mode). ``progress`` may raise to cancel.
        """
        beam = beam_size or self.beam_size
        lang = language or self.language
        if not isinstance(audio, np.ndarray):
            audio = decode_audio(audio if isinstance(audio, bytes) else Path(audio))
        if audio.size == 0:
            return {"language": lang, "language_probability": None, "duration": 0.0, "text": "", "segments": []}
        words = self.word_timestamps if word_timestamps is None else word_timestamps
        with self._lock:
            if self.engine == "faster-whisper":
                result = self._transcribe_faster(audio, glossary, prompt, lang, beam, progress, vad, words)
            else:
                result = self._transcribe_openai(audio, glossary, prompt, lang, beam, progress, words)
        result["text"] = " ".join(s["text"] for s in result["segments"]).strip()
        return result

    @property
    def batch_size(self) -> int:
        """Batched decoding on GPUs: 8 below 8 GB of VRAM (3.6 GB peak with large-v3-turbo), else 16."""
        if self.batch_size_setting:
            return self.batch_size_setting
        if self.device != "cuda" or self.live:
            return 1
        return 16 if gpu_memory_gb() >= 8 else 8

    def _decode_faster(self, audio, glossary, prompt, lang, beam, vad, word_timestamps, batch_size):
        if batch_size > 1:
            from faster_whisper import BatchedInferencePipeline

            if self._batched is None:
                self._batched = BatchedInferencePipeline(model=self._model)
            return self._batched.transcribe(
                audio, language=lang, beam_size=beam, batch_size=batch_size, hotwords=glossary or None,
                vad_parameters={"min_silence_duration_ms": 500}, word_timestamps=word_timestamps,
            )
        return self._model.transcribe(
            audio,
            beam_size=beam,
            language=lang,
            hotwords=glossary or None,
            initial_prompt=prompt or None,
            vad_filter=vad,
            vad_parameters={"min_silence_duration_ms": 500},
            condition_on_previous_text=True,
            word_timestamps=word_timestamps,
        )

    def _transcribe_faster(self, audio, glossary, prompt, lang, beam, progress, vad, word_timestamps) -> dict:
        # Batching splits long audio into ~30 s speech chunks decoded in parallel on the GPU
        # (3.3x faster on a 10-minute class sample, 95% identical words). Short clips and
        # live windows decode sequentially so they keep the preceding-text prompt.
        batch = self.batch_size if audio.size > 120 * SAMPLE_RATE and not prompt else 1
        while True:
            try:
                return self._collect_faster(*self._decode_faster(audio, glossary, prompt, lang, beam, vad,
                                                                 word_timestamps, batch), progress, word_timestamps)
            except RuntimeError as exc:
                if batch > 1 and "memory" in str(exc).lower():
                    log.warning("GPU out of memory at batch size %d; retrying with %d", batch, batch // 2)
                    batch //= 2
                    continue
                raise

    def _collect_faster(self, seg_iter, info, progress, word_timestamps) -> dict:
        segments, words = [], []
        for seg in seg_iter:
            if word_timestamps and seg.words:
                words.extend((w.start, w.end, w.word, w.probability) for w in seg.words)
            else:
                segments.append({"id": len(segments), "start": round(seg.start, 2), "end": round(seg.end, 2),
                                 "text": seg.text.strip()})
            if progress and info.duration:
                progress(min(seg.end / info.duration, 1.0))
        if words:
            segments = resegment(collapse_repeats(merge_punctuation(words)))
        return {"language": info.language, "language_probability": round(info.language_probability, 3),
                "duration": info.duration, "segments": segments}

    def _transcribe_openai(self, audio, glossary, prompt, lang, beam, progress, word_timestamps) -> dict:
        result = self._model.transcribe(
            audio, fp16=self.device == "cuda", language=lang,
            initial_prompt=" ".join(p for p in (glossary, prompt) if p) or None,
            carry_initial_prompt=bool(glossary), beam_size=beam if beam > 1 else None, verbose=None,
            word_timestamps=word_timestamps,
        )
        if progress:
            progress(1.0)
        raw = result.get("segments", [])
        words = [(w["start"], w["end"], w["word"], w.get("probability", 1.0)) for s in raw for w in s.get("words", [])]
        segments = resegment(collapse_repeats(merge_punctuation(words))) if words else [
            {"id": i, "start": round(s["start"], 2), "end": round(s["end"], 2), "text": s["text"].strip()}
            for i, s in enumerate(raw)
        ]
        return {"language": result.get("language"), "language_probability": None,
                "duration": len(audio) / SAMPLE_RATE, "segments": segments}
