import os
import subprocess
import time

import pytest

from app import media

pytestmark = pytest.mark.skipif(not media.ffmpeg_available(), reason="ffmpeg is not installed")


def _encode(dst, source):
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", source, "-c:v", "libx264", "-g", "50",
                    "-keyint_min", "50", "-sc_threshold", "0", str(dst)], check=True, stdin=subprocess.DEVNULL)
    return dst


@pytest.fixture(scope="module")
def cut_at_5s(tmp_path_factory):
    """12 s at 25 fps with a keyframe every 2 s; the picture turns white at 5 s (not a keyframe)."""
    return _encode(tmp_path_factory.mktemp("media") / "cut.mp4",
                   "color=c=black:s=160x90:r=25:d=12,drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='gte(t,5)'")


def test_keyframe_interval(cut_at_5s):
    assert media.keyframe_interval(cut_at_5s) == pytest.approx(2.0, abs=0.05)


def _first_white(frames):
    return next(i for i, frame in enumerate(frames) if frame.mean() > 128)


def test_keyframe_only_scan_finds_changes_at_the_next_keyframe(cut_at_5s):
    times, frames = media.sample_gray_frames(cut_at_5s, 1.0)
    assert len(frames) == 12 and frames.shape[1:] == (media.THUMB_H, media.THUMB_W)
    assert times[_first_white(frames)] == 5.0
    times, frames = media.sample_gray_frames(cut_at_5s, 1.0, keyframes_only=True)
    # Never before the real change (a frame grabbed just after it shows the new picture);
    # sampling ends at the last keyframe.
    assert times[_first_white(frames)] == 6.0 and len(frames) == 10


def test_a_running_ffmpeg_can_be_stopped():
    started = time.monotonic()
    with pytest.raises(media.MediaError, match="stopped"):
        media._run(["ffmpeg", "-v", "error", "-re", "-f", "lavfi", "-i", "testsrc=duration=30", "-f", "null", "-"],
                   stop=lambda: time.monotonic() - started > 0.5)
    assert time.monotonic() - started < 5


@pytest.mark.skipif(os.name != "nt", reason="package-manager launchers are a Windows thing")
def test_tool_sees_through_package_manager_launchers(tmp_path, monkeypatch):
    choco = tmp_path / "chocolatey"
    (choco / "bin").mkdir(parents=True)
    (choco / "bin" / "ffmpeg.exe").write_bytes(b"launcher")
    real = choco / "lib" / "ffmpeg" / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
    real.parent.mkdir(parents=True)
    real.write_bytes(b"ffmpeg")
    shims = tmp_path / "scoop" / "shims"
    shims.mkdir(parents=True)
    (shims / "ffprobe.exe").write_bytes(b"launcher")
    target = tmp_path / "apps" / "ffprobe.exe"
    target.parent.mkdir()
    target.write_bytes(b"ffprobe")
    (shims / "ffprobe.shim").write_text(f'path = "{target}"', encoding="utf-8")
    found = {"ffmpeg": choco / "bin" / "ffmpeg.exe", "ffprobe": shims / "ffprobe.exe"}
    monkeypatch.setattr(media.shutil, "which", lambda name: str(found[name]))
    media.tool.cache_clear()
    try:
        assert media.tool("ffmpeg") == str(real)
        assert media.tool("ffprobe") == str(target)
    finally:
        media.tool.cache_clear()
