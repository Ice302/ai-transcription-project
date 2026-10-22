"""Runtime configuration, read once from environment variables and ``backend/.env``."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def _str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    # --- Speech recognition -------------------------------------------------
    whisper_engine: str = field(default_factory=lambda: _str("WHISPER_ENGINE") or "auto")  # auto | faster | openai
    # "auto" picks large-v3-turbo on a GPU with >= 5 GB VRAM, small on smaller GPUs, base on CPU.
    whisper_model: str = field(default_factory=lambda: _str("WHISPER_MODEL") or "auto")
    live_whisper_model: str = field(default_factory=lambda: _str("LIVE_WHISPER_MODEL") or "auto")
    whisper_device: str = field(default_factory=lambda: _str("WHISPER_DEVICE") or "auto")  # auto | cpu | cuda
    whisper_compute_type: str = field(default_factory=lambda: _str("WHISPER_COMPUTE_TYPE") or "auto")
    whisper_beam_size: int = field(default_factory=lambda: _int("WHISPER_BEAM_SIZE", 5))
    whisper_cpu_threads: int = field(default_factory=lambda: _int("WHISPER_CPU_THREADS", 0))
    language: str | None = field(default_factory=lambda: _str("TRANSCRIBE_LANGUAGE") or None)
    word_timestamps: bool = field(default_factory=lambda: _bool("WORD_TIMESTAMPS", True))
    # Batched GPU decoding (3.3x faster on a 10-minute class sample). 0 = auto, 1 = off.
    whisper_batch_size: int = field(default_factory=lambda: _int("WHISPER_BATCH_SIZE", 0))

    # --- Speaker diarization (who spoke when) -------------------------------
    diarization: bool = field(default_factory=lambda: _bool("DIARIZATION", True))
    diarization_mode: str = field(default_factory=lambda: _str("DIARIZATION_MODE") or "fast")  # fast | precise
    diarization_threshold: float = field(default_factory=lambda: _float("DIARIZATION_THRESHOLD", 0.0))  # 0 = mode default
    models_dir: Path = field(default_factory=lambda: Path(_str("MODELS_DIR") or BACKEND_DIR / "models"))

    # --- Video processing ---------------------------------------------------
    video_enabled: bool = field(default_factory=lambda: _bool("VIDEO_PROCESSING", True))
    ocr_enabled: bool = field(default_factory=lambda: _bool("OCR_ENABLED", True))
    video_sample_fps: float = field(default_factory=lambda: _float("VIDEO_SAMPLE_FPS", 1.0))
    scene_threshold: float = field(default_factory=lambda: _float("SCENE_THRESHOLD", 0.02))
    scene_min_gap: float = field(default_factory=lambda: _float("SCENE_MIN_GAP", 2.0))
    scene_max_gap: float = field(default_factory=lambda: _float("SCENE_MAX_GAP", 60.0))
    max_keyframes: int = field(default_factory=lambda: _int("MAX_KEYFRAMES", 150))
    ocr_threads: int = field(default_factory=lambda: _int("OCR_THREADS", 4))
    ocr_workers: int = field(default_factory=lambda: _int("OCR_WORKERS", 2))
    ocr_min_confidence: float = field(default_factory=lambda: _float("OCR_MIN_CONFIDENCE", 0.6))
    vocabulary_size: int = field(default_factory=lambda: _int("VOCABULARY_SIZE", 60))

    # --- LLM (OpenRouter) ---------------------------------------------------
    openrouter_api_key: str = field(default_factory=lambda: _str("OPENROUTER_API_KEY"))
    llm_model: str = field(default_factory=lambda: _str("LLM_MODEL") or "google/gemma-4-26b-a4b-it")
    vision_model: str = field(default_factory=lambda: _str("VISION_MODEL"))  # empty = captioning off
    vision_max_frames: int = field(default_factory=lambda: _int("VISION_MAX_FRAMES", 12))
    llm_context_chars: int = field(default_factory=lambda: _int("LLM_CONTEXT_CHARS", 400_000))
    llm_timeout: float = field(default_factory=lambda: _float("LLM_TIMEOUT", 180.0))
    # auto = Windows' own curl.exe (Schannel) on Windows, httpx elsewhere | curl | httpx
    llm_transport: str = field(default_factory=lambda: _str("LLM_TRANSPORT") or "auto")
    # Never send anything to an external service (disables the assistant and captions).
    local_only: bool = field(default_factory=lambda: _bool("LOCAL_ONLY", False))

    # --- Server -------------------------------------------------------------
    data_dir: Path = field(default_factory=lambda: Path(_str("DATA_DIR") or BACKEND_DIR / "data"))
    max_upload_mb: int = field(default_factory=lambda: _int("MAX_UPLOAD_MB", 4096))
    max_media_minutes: float = field(default_factory=lambda: _float("MAX_MEDIA_MINUTES", 600))
    keep_media: bool = field(default_factory=lambda: _bool("KEEP_MEDIA", True))  # playable from the library
    job_ttl_hours: float = field(default_factory=lambda: _float("JOB_TTL_HOURS", 0))  # 0 = keep until deleted
    cors_origins: list[str] = field(
        default_factory=lambda: _list("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    )

    @property
    def llm_configured(self) -> bool:
        return bool(self.openrouter_api_key) and not self.local_only

    @property
    def vision_enabled(self) -> bool:
        return self.llm_configured and bool(self.vision_model)


settings = Settings()
