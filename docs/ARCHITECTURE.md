# Architecture

TurboTranscribe is two processes: a **FastAPI backend** that does all media and ML work, and a **React frontend** for capture, playback, review and chat. In development the Vite dev server proxies `/api` (HTTP and WebSocket) to the backend, so the browser talks to one origin. In production the backend serves the built frontend itself.

```text
Browser (React)                                     Backend (FastAPI, one Python process)
───────────────                                     ─────────────────────────────────────
Library ── POST /api/jobs (file + options) ───────▶ JobManager ─▶ worker thread ─▶ pipeline.process_media
        ◀─ GET /api/jobs (poll while busy) ───────   job.json / result.json / frames/ / media.*     │ media (ffmpeg)
        ◀─ GET /api/search?q= ────────────────────── SearchIndex (SQLite FTS5)                      │ vision (scenes, OCR pool)
Recording ◀─ GET /api/jobs/{id}, /media, /frames ─                                                 │ transcriber (Whisper)
          ── PATCH segments / speakers / title ──▶ JobManager.edit ─▶ refresh + reindex             │ diarization (sherpa-onnx)
          ── POST corrections / reprocess / cancel                                                  │ crossref
Live ═══ WS /api/ws/live (stereo stream + frames) ▶ LiveSession ── on stop/disconnect ──▶ queued live job
     ◀═ speech / partial / retract / visual / saved     ├─ AudioStream (ffmpeg pipe → PCM, live.pcm on disk)
                                                        ├─ per-channel sliding-window ASR (You / Others)
                                                        └─ frame worker (OCR, newest frame only)
Assistant ── POST /api/chat {job_ids | context, stream} ▶ llm.chat_stream ─▶ OpenRouter (key from .env)
```

## Backend modules (`backend/app/`)

| Module | Responsibility | Notes |
| --- | --- | --- |
| `main.py` | Routes, model holder, startup tasks, security middleware | Models load in a background thread; the API answers immediately. Startup also re-indexes search and recovers interrupted live recordings. |
| `config.py` | Typed settings from env / `.env` | Frozen dataclass; blank values mean "default". |
| `pipeline.py` | Batch orchestration | `read_video` (scenes → keyframes → OCR → captions) runs inline, or for long videos in a background thread during transcription, after `sample_screen_text` has read 16 frames for the spelling hints. `Stages` maps sequential and background progress onto one bar; `merge_channels` combines You/Others with echo removal. Pure function of (file, engines, settings, options). |
| `crossref.py` | Alignment and analysis | **No I/O, no models.** Vocabulary (with tokenizer rarity), glossary, interface-text (`find_chrome`) filtering, scene assignment, corrections (spelling, confidence, sound), editing helpers, stats, notes context. |
| `transcriber.py` | Speech recognition | Model auto-selection by device/VRAM; GPU warm-up with CPU fallback; whole-file language vote (`detect_language`); batched GPU decoding with an out-of-memory fallback; glossary as `hotwords`; word timings and probabilities; `merge_punctuation`, sentence `resegment`, `collapse_repeats` against decoder loops. |
| `diarization.py` | Who spoke when | `Diarizer.label_segments`: fast mode embeds each sentence (WeSpeaker, ONNX) and clusters them (`label_by_embeddings`, pure); precise mode runs pyannote segmentation and `assign_speakers` (pure), which splits sentences at speaker changes using word timings. |
| `vision.py` | Keyframes and OCR | `select_keyframes`, `find_duplicates` (flip-backs, periodic samples), `OcrPool` (parallel engines), `detect_title` (wordy lines only). |
| `live.py` | Live WebSocket sessions | Continuous stream decoding; per-channel commit policy (`split_stable`, `strip_overlap`); echo retraction; the session is a library job from the first second. |
| `jobs.py` | Job queue and library | One worker thread; atomic JSON writes; `edit()` under per-job locks; `reprocess()`, `cancel()`, `recover_live_recordings()`, kept media, storage accounting, TTL cleanup. |
| `search.py` | Full-text search | One FTS5 row per sentence, per slide, per title; snippets with control-character markers (no HTML). |
| `media.py` | ffmpeg / ffprobe | Decode to NumPy over pipes (optionally one channel), WAV writing, AAC transcode, keyframe interval, frame sampling (optionally keyframes only) and extraction. |
| `llm.py` | OpenRouter | System prompt for the SPEECH/SCREEN format, mixed languages, speakers and prompt-injection safety; streaming and non-streaming chat with retries; Windows' `curl.exe` as the transport on Windows (API key passed on stdin); frame captions. |
| `platform_tuning.py` | OS tweaks | Opts out of Windows EcoQoS throttling (13× faster OCR when minimized). |

### Concurrency

- **Event loop:** requests and WebSockets. Nothing blocking runs on it.
- **Job worker** (1 thread): pipelines run strictly in order. The GPU/CPU is saturated by one job anyway. For videos of 10 minutes or more, the job starts one more thread that reads the video (scenes, keyframes, OCR) on the CPU while the job thread transcribes on the GPU. That thread only updates progress fractions; the job thread reports progress and handles cancellation, and on any error it stops the thread (ffmpeg is polled and killed within a second).
- **Thread pool:** live transcription, OCR and file work are called via `run_in_threadpool`.
- **Locks:** each `Transcriber` and `Diarizer` serialises its own calls; the `OcrPool` hands out engines; `JobManager.edit` locks per job. Batch and live use separate Whisper instances, so a long upload never stalls a meeting.

### Job lifecycle

```text
upload ─▶ (validated with ffprobe) ─▶ queued ─▶ running ─▶ done ──▶ edits / reprocess ─▶ queued …
live   ─▶ recording ─▶ (stop or disconnect) ─▶ queued ─▶ running ─▶ done
                           any state ─▶ cancelled / error (media kept, so "Try again" works)
```

On disk: `data/jobs/<id>/job.json` (summary), `result.json`, `frames/NNNN.jpg`, and `media.<ext>` (uploads) or `media.m4a` (live). Live meetings also have `live_frames.json`, and `live.pcm` while recording. `data/index.db` is the search index.

## Result format (v3; `language_detection` and `screen_chrome` since 3.1)

```jsonc
{
  "version": 3, "id": "…", "kind": "file|live", "title": "…", "filename": "…", "created_at": 1792540800,
  "options": { "language": "en", "glossary": "…", "diarize": true, "num_speakers": 2, "channel_labels": [] },
  "media": { "duration": 37.1, "has_audio": true, "has_video": true, "width": 1280, "height": 720, "audio_channels": 1 },
  "language": "tl", "language_probability": 0.62, "engine": "faster-whisper", "model": "large-v3-turbo", "device": "cuda",
  "language_detection": { "language": "tl", "probability": 0.62, "candidates": [["tl", 0.62], ["en", 0.31]], "windows": 8,
                          "method": "vote|trial|chosen", "trial_scores": { "tl": 180.4, "en": 61.2 } },
  "screen_chrome": ["mute", "participants", "share screen", …],
  "segments": [ { "id": 0, "start": 0.0, "end": 1.8, "text": "Hi everyone…", "scene_id": 0, "speaker": "S1",
                  "words": [[0.0, 0.3, " Hi", 0.98], …], "edited": false } ],
  "speakers": [ { "id": "S1", "name": "Speaker 1", "talk_time": 13.3 } ],
  "keyframes": [ { "id": 0, "t": 0, "end": 13.1, "title": "Kubernetes Migration", "image": "/api/jobs/…/frames/0000.jpg",
                   "ocr_text": "…", "caption": "", "duplicate_of": null, "terms_confirmed": […], "terms_unspoken": […] } ],
  "vocabulary": […], "glossary": "Priya, Raghunathan, Kubernetes, …",
  "corrections": [ { "id": 0, "segment_id": 1, "t": 2.4, "heard": "QBARnet's", "seen": "Kubernetes", "similarity": 0.67,
                     "probability": 0.22, "confidence": "high", "status": "pending|accepted|dismissed|stale" } ],
  "stats": { "segments": 12, "words": 78, "scenes": 3, "speakers": 2, "low_confidence_words": 2, "corrections_pending": 0 },
  "text": "…", "notes_context": "…", "timings": { … }
}
```

`text`, `stats` and `notes_context` are derived. `main.refresh_result` recomputes them after every edit, so exports, search and the assistant always see the edited version.

## Frontend (`frontend/src/`)

| Area | Files | Notes |
| --- | --- | --- |
| Shell | `App.jsx`, `components/TopBar.jsx`, `lib/router.js` | Hash routes `#/`, `#/live`, `#/job/<id>?t=`; the assistant panel is sticky on wide screens and a drawer on narrow ones. |
| Library | `components/library/*`, `hooks/useLibrary.js` | Upload with options (remembered), pastel cards, selection for the assistant, debounced full-text search, setup checklist. |
| Recording | `components/job/*`, `hooks/useJob.js`, `hooks/useMediaTime.js` | Player with captions/speed, scene track, Timeline / Transcript / Cross-check / Speakers tabs, export menu, reprocess dialog, print view. Edits go through `useJob` and replace the result with the server's response. |
| Live | `components/live/LiveView.jsx`, `hooks/useLiveSession.js` | Capture (tab, mic, or both on two channels), the continuous recorder, change-detected screen frames, partials and retractions, the "saved" hand-off. The session lives in `App`, so it keeps running while you browse. |
| Assistant | `components/AssistantPanel.jsx`, `components/Markdown.jsx` | Streaming SSE, per-scope history, lazy-loaded Markdown with GFM tables, clickable timestamps. |
| Design system | `index.css`, `components/ui.jsx`, `components/Art.jsx`, `lib/palette.js` | See [DESIGN.md](DESIGN.md). |

## Key design decisions

1. **The LLM key lives on the server**, and the assistant receives job ids, not raw text, so edits are always reflected.
2. **Cross-referencing happens before and after recognition.** Before: on-screen vocabulary, filtered for rarity, becomes Whisper `hotwords` for every window. After: alignment, corrections and unspoken content, all fed to the assistant.
3. **Corrections are suggestions, applied with one click.** A similar-looking word on screen is evidence, not proof.
4. **Live meetings are never lost.** The recording is on disk from the first second and is re-done at full accuracy after the meeting.
5. **A pure, testable core.** `crossref` (including `find_chrome`), `select_keyframes`, `find_duplicates`, `detect_title`, `merge_punctuation`, `resegment`, `collapse_repeats`, `aggregate_language_votes`, `label_by_embeddings`, `assign_speakers`, `merge_channels`, `split_stable` and `strip_overlap` all take plain data. 112 backend tests, 19 frontend unit tests and a browser end-to-end test cover them and the HTTP surface.
6. **Measured tuning.** Model choice, batch size, OCR threads and workers, the diarization mode and threshold, the keyframe-only scan and the frame-change metric each come from a benchmark ([PERFORMANCE.md](PERFORMANCE.md)), including a real 2.5-hour class recording.
