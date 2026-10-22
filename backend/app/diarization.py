"""Speaker diarization: who spoke when.

Uses sherpa-onnx (ONNX Runtime, CPU, no PyTorch, no Hugging Face token) with
WeSpeaker ResNet34 speaker embeddings. Two modes:

* ``fast`` (default): one voice embedding per transcribed sentence, then clustering.
  On a 10-minute class recording it took 5.4 s instead of 68 s for the sliding-window
  method, and it labelled the 2-speaker test meeting 12/12 correctly.
* ``precise``: sherpa's full pipeline (pyannote segmentation-3.0 sliding windows +
  embeddings, ~8x realtime on CPU). Can split a sentence where the speaker changes
  mid-way (``assign_speakers``).

The models (~33 MB) are downloaded on first use into ``MODELS_DIR/diarization``.
``label_by_embeddings`` and ``assign_speakers`` are pure and unit-tested.
"""
from __future__ import annotations

import logging
import os
import tarfile
import threading
from bisect import bisect_left
from pathlib import Path
from typing import Callable

import numpy as np

log = logging.getLogger(__name__)

RELEASES = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
SEGMENTATION_URL = f"{RELEASES}/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
EMBEDDING_URL = f"{RELEASES}/speaker-recongition-models/wespeaker_en_voxceleb_resnet34_LM.onnx"
SEGMENTATION_FILE = "sherpa-onnx-pyannote-segmentation-3-0/model.onnx"
EMBEDDING_FILE = "wespeaker_en_voxceleb_resnet34_LM.onnx"
SAMPLE_RATE = 16000

Turn = tuple[float, float, int]  # start, end, speaker index
Progress = Callable[[float], None]


class Diarizer:
    def __init__(self, models_dir: Path, threshold: float = 0.0, threads: int = 0, mode: str = "fast"):
        self.dir = models_dir / "diarization"
        self.mode = mode if mode in ("fast", "precise") else "fast"
        # 0.6 put two clearly different voices into one cluster when only a few long sentences
        # were available; 0.5 separates them. It can split one person heard in different
        # conditions (a teacher came out as 3 clusters), which the same-voice merge in
        # label_by_embeddings re-joins.
        self.threshold = threshold or 0.5
        self.threads = threads or min(8, max(2, (os.cpu_count() or 4) // 2))
        self.available: bool | None = None  # None = not checked yet
        self.error: str | None = None
        self._engines: dict[int, object] = {}
        self._extractor = None
        self._lock = threading.Lock()

    # -- models ----------------------------------------------------------------
    def _download(self, url: str, dest: Path) -> None:
        import httpx

        tmp = dest.with_suffix(dest.suffix + ".part")
        log.info("Downloading %s", url)
        with httpx.stream("GET", url, follow_redirects=True, timeout=120) as resp:
            resp.raise_for_status()
            with tmp.open("wb") as out:
                for chunk in resp.iter_bytes(1 << 20):
                    out.write(chunk)
        tmp.replace(dest)

    def ensure_models(self) -> bool:
        """Download models if missing. Safe to call repeatedly; returns availability."""
        with self._lock:
            if self.available is not None:
                return self.available
            try:
                import sherpa_onnx  # noqa: F401

                self.dir.mkdir(parents=True, exist_ok=True)
                if not (self.dir / EMBEDDING_FILE).exists():
                    self._download(EMBEDDING_URL, self.dir / EMBEDDING_FILE)
                if self.mode == "precise" and not (self.dir / SEGMENTATION_FILE).exists():
                    archive = self.dir / "segmentation.tar.bz2"
                    self._download(SEGMENTATION_URL, archive)
                    with tarfile.open(archive) as tar:
                        tar.extractall(self.dir, filter="data")
                    archive.unlink(missing_ok=True)
                self.available = True
            except Exception as exc:
                self.available, self.error = False, str(exc)
                log.warning("Speaker diarization unavailable: %s", exc)
            return self.available

    # -- fast: one embedding per sentence ----------------------------------------
    def _embed(self, samples: np.ndarray) -> np.ndarray:
        import sherpa_onnx

        if self._extractor is None:
            config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(self.dir / EMBEDDING_FILE),
                                                                 num_threads=self.threads)
            self._extractor = sherpa_onnx.SpeakerEmbeddingExtractor(config)
        stream = self._extractor.create_stream()
        stream.accept_waveform(SAMPLE_RATE, samples)
        stream.input_finished()
        vec = np.asarray(self._extractor.compute(stream), dtype=np.float32)
        return vec / (np.linalg.norm(vec) + 1e-9)

    def _cluster(self, vectors: np.ndarray, num_speakers: int | None) -> list[int]:
        import sherpa_onnx

        if len(vectors) < 2:
            return [0] * len(vectors)
        config = sherpa_onnx.FastClusteringConfig(num_clusters=num_speakers or -1, threshold=self.threshold)
        return list(sherpa_onnx.FastClustering(config)(vectors))

    def label_segments(self, audio: np.ndarray, segments: list[dict], num_speakers: int | None = None,
                       progress: Progress | None = None) -> tuple[list[dict], list[dict]]:
        """Attach speakers to transcript segments. Returns (segments, speakers)."""
        if not self.ensure_models():
            raise RuntimeError(f"Speaker diarization unavailable: {self.error}")
        if not segments:
            return segments, []
        if self.mode == "precise":
            return assign_speakers(segments, self.diarize(audio, num_speakers, progress))
        embeddings: dict[int, np.ndarray] = {}
        with self._lock:
            for i, seg in enumerate(segments):
                start, end = int(seg["start"] * SAMPLE_RATE), int(seg["end"] * SAMPLE_RATE)
                if end - start >= int(0.5 * SAMPLE_RATE):
                    # Cap very long sentences to their middle 10 s: plenty for a voice print.
                    if end - start > 10 * SAMPLE_RATE:
                        mid = (start + end) // 2
                        start, end = mid - 5 * SAMPLE_RATE, mid + 5 * SAMPLE_RATE
                    embeddings[i] = self._embed(audio[start:end])
                if progress and i % 25 == 0:
                    progress(i / len(segments))  # may raise to cancel the job
            return label_by_embeddings(segments, embeddings, lambda v: self._cluster(v, num_speakers),
                                       fixed_count=bool(num_speakers))

    # -- precise: sherpa's sliding-window diarization ----------------------------
    def _engine(self, num_speakers: int | None):
        import sherpa_onnx

        key = num_speakers or -1
        if key not in self._engines:
            config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
                segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
                    pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                        model=str(self.dir / SEGMENTATION_FILE)),
                    num_threads=self.threads,
                ),
                embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                    model=str(self.dir / EMBEDDING_FILE), num_threads=self.threads),
                clustering=sherpa_onnx.FastClusteringConfig(num_clusters=key, threshold=self.threshold),
                min_duration_on=0.3,
                min_duration_off=0.5,
            )
            if not config.validate():
                raise RuntimeError("Invalid diarization configuration")
            self._engines[key] = sherpa_onnx.OfflineSpeakerDiarization(config)
        return self._engines[key]

    def diarize(self, samples: np.ndarray, num_speakers: int | None = None,
                progress: Progress | None = None) -> list[Turn]:
        """Speaker turns for 16 kHz mono float32 audio (precise mode)."""
        if samples.size < SAMPLE_RATE:
            return []

        def callback(done: int, total: int) -> int:
            if progress and total:
                try:
                    progress(done / total)
                except Exception:
                    pass  # the engine can't abort mid-way; cancellation is checked after this stage
            return 0

        with self._lock:
            result = self._engine(num_speakers).process(samples, callback=callback).sort_by_start_time()
        return [(float(r.start), float(r.end), int(r.speaker)) for r in result]


# ---------------------------------------------------------------- pure helpers
def _numbered(segments: list[dict], labels: dict[int, int | None]) -> tuple[list[dict], list[dict]]:
    """Speaker ids S1, S2, ... in order of first appearance."""
    order: dict[int, str] = {}
    out = []
    for i, seg in enumerate(segments):
        label = labels.get(i)
        if label is not None and label not in order:
            order[label] = f"S{len(order) + 1}"
        out.append({**seg, "id": i, "speaker": order.get(label) if label is not None else None})
    return out, [{"id": sid, "name": f"Speaker {sid[1:]}"} for sid in order.values()]


def label_by_embeddings(segments: list[dict], embeddings: dict[int, np.ndarray],
                        cluster: Callable[[np.ndarray], list[int]], min_cluster_seconds: float = 2.0,
                        min_speaker_seconds: float = 8.0, min_speaker_share: float = 0.02,
                        same_voice: float = 0.8, fixed_count: bool = False) -> tuple[list[dict], list[dict]]:
    """Cluster sentence voice prints into speakers.

    Only sentences of ``min_cluster_seconds`` or more define voices (a 0.7 s "Okay"
    gives a noisy print). Unless the speaker count was given, voices whose average
    prints are nearly identical (cosine >= ``same_voice``) are one person, and voices
    with very little talk time are merged into the nearest real one. Every sentence
    then takes its nearest voice; sentences too short to embed inherit their neighbour's.

    ``same_voice``: a teacher's 2.5-hour class came out as two "speakers" whose average
    prints were 0.91 alike (her sentences: 0.94 to her own average), while two
    genuinely different voices measured 0.53.
    """
    duration = {i: s["end"] - s["start"] for i, s in enumerate(segments)}
    candidates = [i for i in embeddings if duration[i] >= min_cluster_seconds] or list(embeddings)
    if not candidates:
        return [{**s, "id": i, "speaker": None} for i, s in enumerate(segments)], []
    labels = cluster(np.stack([embeddings[i] for i in candidates]))

    def centroids_of(assignment: dict[int, int]) -> dict[int, np.ndarray]:
        out = {}
        for label in set(assignment.values()):
            mean = np.mean([embeddings[i] for i, lab in assignment.items() if lab == label], axis=0)
            out[label] = mean / (np.linalg.norm(mean) + 1e-9)
        return out

    assignment = dict(zip(candidates, labels))
    if not fixed_count:
        while True:  # one voice heard in two conditions (turned away, closer to the mic)
            centroids = centroids_of(assignment)
            pairs = [(float(centroids[a] @ centroids[b]), a, b) for a in centroids for b in centroids if a < b]
            best = max(pairs, default=None)
            if best is None or best[0] < same_voice:
                break
            assignment = {i: best[1] if lab == best[2] else lab for i, lab in assignment.items()}
        talk: dict[int, float] = {}
        for i, label in assignment.items():
            talk[label] = talk.get(label, 0.0) + duration[i]
        total = sum(talk.values())
        keep = {lab for lab, t in talk.items() if t >= max(min_speaker_seconds, min_speaker_share * total)}
        if keep and keep != set(talk):
            kept_centroids = {lab: c for lab, c in centroids_of(assignment).items() if lab in keep}
            for i, label in list(assignment.items()):
                if label not in keep:
                    assignment[i] = max(kept_centroids, key=lambda lab: float(embeddings[i] @ kept_centroids[lab]))
    centroids = centroids_of(assignment)
    voiced = {i: max(centroids, key=lambda lab: float(embeddings[i] @ centroids[lab]))
              for i in range(len(segments)) if i in embeddings}
    order = sorted(voiced)
    final: dict[int, int | None] = dict(voiced)
    for i in range(len(segments)):
        if i in final:
            continue
        # Too short to embed ("Great."): take the speaker of the closer sentence in time. A short
        # word usually opens the next turn or closes the previous one.
        k = bisect_left(order, i)
        prev, nxt = (order[k - 1] if k else None), (order[k] if k < len(order) else None)
        if prev is None or nxt is None:
            final[i] = voiced[prev if nxt is None else nxt] if order else None
        else:
            before = segments[i]["start"] - segments[prev]["end"]
            after = segments[nxt]["start"] - segments[i]["end"]
            final[i] = voiced[prev] if before <= after else voiced[nxt]
    return _numbered(segments, final)


def speaker_at(start: float, end: float, turns: list[Turn], max_distance: float = 1.0) -> int | None:
    """Speaker with the most overlap with [start, end]; else the nearest turn within ``max_distance``."""
    best, best_overlap = None, 0.0
    for t0, t1, spk in turns:
        overlap = min(end, t1) - max(start, t0)
        if overlap > best_overlap:
            best, best_overlap = spk, overlap
    if best is not None:
        return best
    nearest, distance = None, max_distance
    for t0, t1, spk in turns:
        d = max(t0 - end, start - t1)
        if d <= distance:
            nearest, distance = spk, d
    return nearest


def _smooth(labels: list[int | None]) -> list[int | None]:
    """Fill unknown words from neighbours and absorb 1-word speaker flickers."""
    out = list(labels)
    for i in range(len(out)):  # forward fill
        if out[i] is None and i > 0:
            out[i] = out[i - 1]
    for i in range(len(out) - 2, -1, -1):  # backward fill the start
        if out[i] is None:
            out[i] = out[i + 1]
    for i in range(1, len(out) - 1):  # A B A -> A A A
        if out[i] != out[i - 1] and out[i - 1] == out[i + 1]:
            out[i] = out[i - 1]
    return out


def assign_speakers(segments: list[dict], turns: list[Turn]) -> tuple[list[dict], list[dict]]:
    """Attach speaker ids to segments from diarization turns, splitting at speaker changes (precise mode)."""
    if not turns:
        return segments, []
    raw: list[tuple[dict, int | None]] = []
    for seg in segments:
        words = seg.get("words") or []
        if len(words) < 2:
            raw.append((seg, speaker_at(seg["start"], seg["end"], turns)))
            continue
        labels = _smooth([speaker_at(w[0], w[1], turns) for w in words])
        run_start = 0
        for i in range(1, len(words) + 1):
            if i == len(words) or labels[i] != labels[run_start]:
                part = words[run_start:i]
                text = "".join(w[2] for w in part).strip()
                if text:
                    raw.append(({**seg, "start": part[0][0], "end": part[-1][1], "text": text, "words": part},
                                labels[run_start]))
                run_start = i
    return _numbered([seg for seg, _ in raw], {i: spk for i, (_, spk) in enumerate(raw)})


def talk_times(segments: list[dict]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for seg in segments:
        if seg.get("speaker"):
            totals[seg["speaker"]] = round(totals.get(seg["speaker"], 0.0) + seg["end"] - seg["start"], 2)
    return totals
