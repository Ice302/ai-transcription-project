"""Thin wrappers around the ffmpeg / ffprobe command-line tools."""
from __future__ import annotations

import functools
import json
import os
import re
import shutil
import subprocess
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from .platform_tuning import disable_power_throttling

# Grayscale thumbnail size used for scene-change detection. Small enough that an
# hour of video at 1 fps is ~8 MB, large enough to notice a slide change.
THUMB_W, THUMB_H = 64, 36
SAMPLE_RATE = 16000


class MediaError(RuntimeError):
    pass


@dataclass
class MediaInfo:
    duration: float
    has_audio: bool
    has_video: bool
    width: int = 0
    height: int = 0
    audio_channels: int = 0

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


@functools.lru_cache(maxsize=None)
def tool(name: str) -> str:
    """Path of ffmpeg / ffprobe, looking through package-manager launchers.

    Chocolatey and Scoop put small launcher programs on PATH that start the real
    program as a child process. Killing the launcher to cancel a job left the real
    ffmpeg running to the end, and the launcher's power-throttling opt-out never
    reached it, so the real executable is called directly when it can be found.
    """
    found = shutil.which(name)
    if not found or os.name != "nt":
        return found or name
    path = Path(found)
    scoop = path.with_suffix(".shim")  # Scoop: a text file with "path = C:\...\ffmpeg.exe"
    if scoop.exists():
        for line in scoop.read_text(errors="replace").splitlines():
            key, _, value = line.partition("=")
            target = value.strip().strip('"')
            if key.strip() == "path" and Path(target).is_file():
                return target
    if path.parent.name.lower() == "bin" and path.parent.parent.name.lower() == "chocolatey":
        targets = sorted((path.parent.parent / "lib").glob(f"ffmpeg*/tools/**/{name}.exe"))
        if targets:
            return str(targets[-1])
    return found


def _kill(proc: subprocess.Popen) -> None:
    if os.name == "nt":  # the whole tree, in case it is a launcher we could not see through
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True,
                       stdin=subprocess.DEVNULL)
    proc.kill()


def _run(args: list[str], input: bytes | None = None, timeout: float | None = None,
         stop: Callable[[], bool] | None = None) -> subprocess.CompletedProcess:
    """Run a tool and capture its output. ``stop`` is polled twice a second; when it
    returns True the process is killed (a cancelled job stops within a second)."""
    name = args[0]
    try:
        proc = subprocess.Popen([tool(name), *args[1:]],
                                stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        raise MediaError(f"{name} not found on PATH. Install ffmpeg.") from exc
    disable_power_throttling(proc.pid)  # the backend's own opt-out is not inherited
    deadline = None if timeout is None else time.monotonic() + timeout
    try:
        while True:
            wait = 0.5 if stop else (None if deadline is None else max(0.0, deadline - time.monotonic()))
            try:
                stdout, stderr = proc.communicate(input, timeout=wait)
                break
            except subprocess.TimeoutExpired:
                input = None  # already being written; communicate() must not get it twice
                if deadline is not None and time.monotonic() >= deadline:
                    raise MediaError(f"{name} timed out") from None
                if stop and stop():
                    raise MediaError(f"{name} was stopped") from None
    except BaseException:
        _kill(proc)
        proc.communicate()
        raise
    if proc.returncode != 0:
        message = stderr.decode("utf-8", "replace")[-800:].strip() if stderr else ""
        raise MediaError(f"{name} failed: {message}")
    return subprocess.CompletedProcess(args, proc.returncode, stdout, stderr)


def probe(path: Path) -> MediaInfo:
    out = _run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
               timeout=60)
    data = json.loads(out.stdout or b"{}")
    streams = data.get("streams", [])
    # Cover art in MP3/M4A shows up as a single-frame "video" stream; ignore it.
    video = next(
        (s for s in streams if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")),
        None,
    )
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration = float(data.get("format", {}).get("duration") or 0.0)
    return MediaInfo(
        duration=duration,
        has_audio=audio is not None,
        has_video=video is not None,
        width=int(video.get("width", 0)) if video else 0,
        height=int(video.get("height", 0)) if video else 0,
        audio_channels=int(audio.get("channels", 0) or 0) if audio else 0,
    )


def decode_audio(src: Path | bytes, channel: int | None = None) -> np.ndarray:
    """Decode any audio/video file (path or in-memory bytes) to 16 kHz mono float32.

    This is the exact input format Whisper uses. Decoding ourselves with ffmpeg avoids
    temp files for live chunks and sidesteps PyAV version incompatibilities.
    ``channel`` picks one channel of a multi-channel recording instead of a downmix
    (live meetings store "you" and "others" on separate channels).
    """
    from_bytes = isinstance(src, (bytes, bytearray))
    mix = ["-af", f"pan=mono|c0=c{channel}"] if channel is not None else ["-ac", "1"]
    out = _run(
        ["ffmpeg", "-v", "error", "-i", "pipe:0" if from_bytes else str(src), "-vn", "-sn", *mix,
         "-ar", str(SAMPLE_RATE), "-f", "f32le", "-acodec", "pcm_f32le", "pipe:1"],
        input=bytes(src) if from_bytes else None,
    )
    return np.frombuffer(out.stdout, dtype=np.float32)


def write_wav(path: Path, channels: list[np.ndarray], sample_rate: int = SAMPLE_RATE) -> Path:
    """Write float32 channels (equal length after padding) as 16-bit PCM WAV."""
    n = max((len(c) for c in channels), default=0)
    padded = [np.pad(c, (0, n - len(c))) for c in channels]
    pcm = (np.clip(np.stack(padded, axis=1), -1, 1) * 32767).astype("<i2") if n else np.zeros((0, 1), "<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(len(channels))
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    return path


def pcm16_to_wav(raw: Path, dst: Path, channels: int, sample_rate: int = SAMPLE_RATE) -> Path:
    """Wrap a raw interleaved 16-bit PCM recording in a WAV header, streaming in chunks."""
    with wave.open(str(dst), "wb") as w, raw.open("rb") as src:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        while chunk := src.read(1 << 20):
            w.writeframes(chunk)
    return dst


def transcode_audio(src: Path, dst: Path, bitrate: str = "48k") -> Path:
    """Compress audio for storage/playback (AAC in .m4a plays in every browser)."""
    _run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(src), "-vn", "-c:a", "aac", "-b:a", bitrate,
          str(dst)])
    return dst


def keyframe_interval(src: Path, seconds: int = 60) -> float | None:
    """Median gap between the encoder's keyframes over the first minute (None if unknown)."""
    try:
        out = _run(["ffprobe", "-v", "error", "-skip_frame", "nokey", "-select_streams", "v:0",
                    "-read_intervals", f"%+{seconds}", "-show_entries", "frame=pts_time", "-of", "csv=p=0", str(src)],
                   timeout=60)
        times = sorted(float(x) for x in re.findall(r"\d+\.\d+", out.stdout.decode()))
        gaps = [b - a for a, b in zip(times, times[1:]) if b > a]
        return float(np.median(gaps)) if gaps else None
    except (MediaError, ValueError):
        return None


def sample_gray_frames(src: Path, fps: float, keyframes_only: bool = False,
                       stop: Callable[[], bool] | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Return (timestamps, frames) where frames is uint8 [n, THUMB_H, THUMB_W].

    One ffmpeg pass decodes the whole video at ``fps`` into tiny grayscale
    thumbnails, which is all scene-change detection needs. ``keyframes_only``
    decodes just the encoder's keyframes (each sample then shows the latest one):
    4.6x faster on a 1080p60 recording, and encoders add keyframes at hard cuts such
    as slide changes anyway.
    """
    skip = ["-skip_frame", "nokey"] if keyframes_only else []
    out = _run([
        "ffmpeg", "-nostdin", "-v", "error", *skip, "-i", str(src), "-an", "-sn",
        "-vf", f"fps={fps},scale={THUMB_W}:{THUMB_H}:flags=area,format=gray",
        "-f", "rawvideo", "-pix_fmt", "gray", "-",
    ], stop=stop)
    frame_size = THUMB_W * THUMB_H
    count = len(out.stdout) // frame_size
    frames = np.frombuffer(out.stdout[: count * frame_size], dtype=np.uint8).reshape(count, THUMB_H, THUMB_W)
    timestamps = np.arange(count, dtype=np.float64) / fps
    return timestamps, frames


def extract_frame(src: Path, t: float, dst: Path, max_width: int = 1280) -> Path:
    """Save a single JPEG frame at time ``t`` (fast input seeking)."""
    _run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{max(t, 0):.3f}", "-i", str(src),
          "-frames:v", "1", "-vf", f"scale='min({max_width},iw)':-2", "-q:v", "3", str(dst)], timeout=120)
    return dst
