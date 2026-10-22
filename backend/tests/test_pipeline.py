import dataclasses
import subprocess
import threading
import time

import numpy as np
import pytest

from app import media, pipeline
from app.config import settings
from app.media import write_wav
from app.pipeline import Engines, JobOptions, Stages, VisualsStopped, merge_channels, process_media, read_video
from app.vision import OcrLine, OcrResult


def seg(id_, start, end, text):
    return {"id": id_, "start": start, "end": end, "text": text}


def test_merge_channels_labels_and_removes_echo():
    you = [seg(0, 0.0, 2.0, "Hi team, quick update from me."),
           seg(1, 5.1, 7.0, "We moved forty services so far.")]  # mic picked up the speaker: echo
    others = [seg(0, 5.0, 7.0, "We moved 40 services so far."), seg(1, 8.0, 9.0, "Questions?")]
    merged, speakers = merge_channels([("You", you, None), ("Others", others, None)])
    assert [(s["speaker"], s["text"]) for s in merged] == [
        ("S1", "Hi team, quick update from me."), ("S2", "We moved 40 services so far."), ("S2", "Questions?")]
    assert [s["id"] for s in merged] == [0, 1, 2]
    assert speakers == [{"id": "S1", "name": "You"}, {"id": "S2", "name": "Others"}]


def test_merge_channels_keeps_diarized_sub_speakers():
    others = [{**seg(0, 1, 2, "First."), "speaker": "S1"}, {**seg(1, 3, 4, "Second."), "speaker": "S2"}]
    subs = [{"id": "S1", "name": "Speaker 1"}, {"id": "S2", "name": "Speaker 2"}]
    merged, speakers = merge_channels([("You", [], None), ("Others", others, subs)])
    assert [s["speaker"] for s in merged] == ["S2", "S3"]
    assert [s["name"] for s in speakers] == ["Others 1", "Others 2"]  # "You" never spoke, so it is dropped


def test_stages_map_progress_onto_one_bar():
    calls = []
    stage = Stages(lambda label, p: calls.append((label, round(p, 3))), {"a": 1, "b": 0, "c": 3})
    stage("a", "A", 0.5)
    stage("c", "C", 1.0)
    stage("b", "B", 1.0)
    assert calls == [("A", 0.125), ("C", 0.99), ("B", 0.25)]


class FakeTranscriber:
    engine, model_name, device = "fake", "fake-model", "cpu"

    def __init__(self):
        self.glossary = None

    def is_common_word(self, word):
        return word in {"Slide"}

    def transcribe(self, audio, glossary=None, language=None, progress=None, **_):
        self.glossary = glossary
        if progress:
            progress(1.0)
        return {"language": language or "en", "language_probability": 0.99, "duration": len(audio) / 16000,
                "segments": [
                    {"id": 0, "start": 1.0, "end": 3.0, "text": "Welcome to the Kubernetes review.",
                     "words": [[1.0, 1.5, " Welcome", 0.9], [1.5, 3.0, " review.", 0.9]]},
                    {"id": 1, "start": 6.5, "end": 8.0, "text": "Costs for cuber netties dropped.",
                     "words": [[6.5, 7.0, " Costs", 0.9], [7.0, 7.3, " cuber", 0.3], [7.3, 7.6, " netties", 0.5],
                               [7.6, 8.0, " dropped.", 0.9]]},
                ]}


class FakeOcr:
    def __init__(self):
        self.calls = 0

    def read_many(self, images, progress=None):
        self.calls += len(images)
        texts = {0: ("Kubernetes Review", "Agenda"), 1: ("Kubernetes Costs", "Snowflake ARR"), 2: ("Thanks", "Q&A")}
        out = []
        for i, _ in enumerate(images):
            title, body = texts[i]
            out.append(OcrResult([OcrLine(title, 0.99, 10, 10, 60), OcrLine(body, 0.99, 10, 100, 30)]))
            if progress:
                progress(i + 1)
        return out


def _make_video(path, ffmpeg_dir):
    """Slides A (0-6 s), B (6-10 s), C (10-13 s), A again (13-16 s), with a sine tone."""
    w, h, fps = 160, 90, 5
    a = np.zeros((h, w, 3), np.uint8)
    a[10:40, 10:150] = 255
    b = np.zeros_like(a)
    b[50:80, 20:140] = (255, 255, 0)
    c = np.full_like(a, 90)
    frames = [a] * 30 + [b] * 20 + [c] * 15 + [a] * 15
    audio = ffmpeg_dir / "tone.wav"
    t = np.arange(16 * 16000) / 16000
    write_wav(audio, [0.2 * np.sin(2 * np.pi * 220 * t).astype(np.float32)])
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                    "-r", str(fps), "-i", "pipe:0", "-i", str(audio), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(path)], input=b"".join(f.tobytes() for f in frames), check=True)


def test_process_video_end_to_end(tmp_path, ffmpeg):
    video = tmp_path / "talk.mp4"
    _make_video(video, tmp_path)
    cfg = dataclasses.replace(settings, scene_max_gap=4.0, scene_min_gap=1.0, vision_model="", diarization=False)
    transcriber, ocr = FakeTranscriber(), FakeOcr()
    progress = []
    result = process_media(video, "talk.mp4", tmp_path, Engines(transcriber, ocr, None), cfg,
                           lambda label, p: progress.append(p), frame_url=lambda n: f"/frames/{n}",
                           options=JobOptions(glossary="Marcus Okafor", language="en"))

    kfs = result["keyframes"]
    # A, B, C, and the flip back to A; the periodic samples of A at 4 s were folded into scene 1.
    assert [round(k["t"]) for k in kfs] == [0, 6, 10, 13]
    assert [k["duplicate_of"] for k in kfs] == [None, None, None, 0]
    assert ocr.calls == 3  # the repeated slide reused its OCR
    assert kfs[3]["ocr_text"] == kfs[0]["ocr_text"] and kfs[3]["image"] == "/frames/0000.jpg"
    assert [k["title"] for k in kfs] == ["Kubernetes Review", "Kubernetes Costs", "Thanks", "Kubernetes Review"]
    assert (tmp_path / "frames" / "0000.jpg").exists() and not (tmp_path / "frames" / "0003.jpg").exists()

    # User glossary first, then on-screen terms; "Slide"-like common words are filtered by the tokenizer hook.
    assert transcriber.glossary.startswith("Marcus Okafor, Kubernetes")
    assert [s["scene_id"] for s in result["segments"]] == [0, 1]
    (corr,) = result["corrections"]
    assert (corr["heard"], corr["seen"], corr["confidence"]) == ("cuber netties", "Kubernetes", "high")
    assert result["stats"]["scenes"] == 4 and result["stats"]["corrections_pending"] == 1
    assert "[SCENE 2 | 00:06–00:10] Kubernetes Costs" in result["notes_context"]
    assert result["language"] == "en" and result["version"] == 3
    assert progress == sorted(progress) and progress[-1] <= 1.0


def test_background_stages_add_to_the_bar_and_the_message():
    calls = []
    stage = Stages(lambda label, p: calls.append((label, round(p, 3))), {"a": 1, "ocr": 2, "b": 1},
                   background=("ocr",))
    stage("a", "A", 1.0)
    stage.update("ocr", 0.5, "Reading on-screen text (1/2)")
    stage("b", "B", 0.0)
    stage.finish_background()
    stage("b", "B", 1.0)
    assert calls == [("A", 0.25), ("B · Reading on-screen text (1/2)", 0.5), ("B", 0.99)]


class CyclingOcr(FakeOcr):
    """Any number of frames: the three slide texts repeat (the sample reads 4 frames, the scenes 3)."""

    def read_many(self, images, progress=None):
        texts = [("Kubernetes Review", "Agenda"), ("Kubernetes Costs", "Snowflake ARR"), ("Thanks", "Q&A")]
        self.calls += len(images)
        out = []
        for i, _ in enumerate(images):
            title, body = texts[i % 3]
            out.append(OcrResult([OcrLine(title, 0.99, 10, 10, 60), OcrLine(body, 0.99, 10, 100, 30)]))
            if progress:
                progress(i + 1)
        return out


def _overlapping(monkeypatch):
    monkeypatch.setattr(pipeline, "OVERLAP_MIN_SECONDS", 0)
    monkeypatch.setattr(pipeline, "GLOSSARY_SAMPLES", 4)
    return dataclasses.replace(settings, scene_max_gap=4.0, scene_min_gap=1.0, vision_model="", diarization=False)


def test_long_videos_read_the_slides_while_transcribing(tmp_path, ffmpeg, monkeypatch):
    cfg = _overlapping(monkeypatch)
    video = tmp_path / "talk.mp4"
    _make_video(video, tmp_path)
    transcriber, ocr = FakeTranscriber(), CyclingOcr()
    progress = []
    result = process_media(video, "talk.mp4", tmp_path, Engines(transcriber, ocr, None), cfg,
                           lambda label, p: progress.append(p), frame_url=lambda n: f"/frames/{n}",
                           options=JobOptions(glossary="Marcus Okafor", language="en"))
    kfs = result["keyframes"]
    assert [round(k["t"]) for k in kfs] == [0, 6, 10, 13]
    assert [k["title"] for k in kfs] == ["Kubernetes Review", "Kubernetes Costs", "Thanks", "Kubernetes Review"]
    assert ocr.calls == 4 + 3  # the sample, then each unique scene once
    assert transcriber.glossary.startswith("Marcus Okafor, Kubernetes")  # hints from the sample
    assert not (tmp_path / "sample").exists()
    assert {"slide_sample", "scene_detection", "ocr", "transcription", "total"} <= set(result["timings"])
    assert result["corrections"][0]["seen"] == "Kubernetes"
    assert progress == sorted(progress) and progress[-1] <= 1.0


def test_cancelling_also_stops_reading_the_video(tmp_path, ffmpeg, monkeypatch):
    cfg = _overlapping(monkeypatch)
    video = tmp_path / "talk.mp4"
    _make_video(video, tmp_path)

    class Cancelled(Exception):
        pass

    def report(label, p):
        if label.startswith("Transcribing"):
            raise Cancelled()

    with pytest.raises(Cancelled):
        process_media(video, "talk.mp4", tmp_path, Engines(FakeTranscriber(), CyclingOcr(), None), cfg, report,
                      frame_url=str, options=JobOptions(language="en"))
    deadline = time.monotonic() + 5
    while any(t.name.startswith("visuals") for t in threading.enumerate()) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not any(t.name.startswith("visuals") for t in threading.enumerate())


def test_read_video_stops_on_request(tmp_path, ffmpeg):
    video = tmp_path / "talk.mp4"
    _make_video(video, tmp_path)
    with pytest.raises(VisualsStopped):
        read_video(video, media.probe(video), settings, CyclingOcr(), tmp_path / "frames", str, False,
                   lambda *args: None, stop=lambda: True)
