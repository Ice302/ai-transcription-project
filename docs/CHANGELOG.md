# Changelog

## 3.1.0 (2026-10-22)

Fixes for long, real-world recordings, found on a 2.5-hour Zoom class held in Tagalog and English. In 3.0 that class came out as 1,015 words, mostly ", so,", the assistant failed with a TLS error, and processing took 48.6 minutes. In 3.1 it gives 15,310 words of real Taglish, one speaker (the teacher), slide titles without Zoom's buttons, a working assistant, and it is processed in 5.6 minutes (8.4 with a game running on the same laptop).

### Fixed

- **Mixed-language recordings were transcribed in the wrong language.** Whisper picked the language from the first 30 seconds. A class that opened with an English greeting was decoded as English for 2.5 hours, so the Tagalog speech came out as ", so,". The language is now voted on across 8 speech-rich 30-second windows from the whole recording. If two languages are close, a sample is transcribed in both and the clearer result wins. Live meetings lock the language once 4 windows agree.
- **Punctuation-only lines.** Punctuation that Whisper emits as a separate "word" is now joined to the word before it, and lines without letters or digits are dropped.
- **The assistant failed with `TLSV1_ALERT_DECODE_ERROR`.** On the development network, about 40% of large requests from Python's TLS stack were corrupted. Two changes:
  - On Windows, requests now go through Windows' own `curl.exe`; the API key is passed on stdin, never on the command line.
  - Dropped connections are retried 3 times, but only before the answer starts streaming.

  Errors now explain the likely cause (VPN, antivirus HTTPS scanning, school or office networks) and offer **Try again**.
- **Zoom's interface took over the notes.** "Mute", "Share", "REC", toolbar labels and participant names became slide titles, bullet points and spelling hints. Text that appears on at least 30% of the distinct screens is now treated as interface text and left out. Matching ignores case and punctuation, and still works when OCR merges two neighbouring labels into one line or splits one apart. The Cross-check tab lists what was removed.
- **Equations as slide titles** ("2x²-x-3=0"). A title must now be mostly letters. A first line in ALL CAPS is used when the font sizes are uniform.
- **One teacher appeared as several speakers.** Voices whose average voice prints are nearly identical are merged: the class's "speakers" scored 0.91 against each other, while two different voices scored 0.5–0.6. A speaker count you set is always respected. Clustering itself is stricter (0.5), so two different voices stay apart even when only a few sentences are long enough to compare, and a word too short to embed takes the speaker of the closer sentence. The two-voice test meeting: 12 of 12 lines right.
- **Noisy suggested fixes.** On the class transcript, the 3.0 rules made 28 suggestions and 1 was useful. These are now ignored:
  - other forms of the same word (inequality / INEQUALITIES, fractions / Fractional);
  - hyphenation (left open / Left-Open);
  - clearly heard words that are only the start of the screen word (line / LINEAR);
  - pairs of filler words matched against OCR junk (it is / iThis).

  Three remain, and two of them are real catches: "undounded" → Unbounded and "FND Math" → FNDMATH.
- **Cancelling during video processing left ffmpeg running.** Chocolatey and Scoop install launcher programs for ffmpeg, and killing the launcher did not kill ffmpeg. The real executables are now called directly, the whole process tree is killed, and a cancel stops ffmpeg within a second.

### Faster

The 2.5-hour class: **48.6 min → 5.6 min**, or 8.4 min while a game was using 4 CPU cores and the GPU. Per-stage times: [PERFORMANCE.md](PERFORMANCE.md).

- **Batched GPU transcription:** 8 windows at a time below 8 GB of VRAM, 16 above. 2.2–3× faster; it halves the batch if the GPU runs out of memory.
- **Speaker identification from one voice print per sentence** (`DIARIZATION_MODE=fast`, the default): 5.4 s instead of 68 s per 10 minutes. `precise` keeps the full diarization.
- **Keyframe-only scene scan** for recordings over 20 minutes: 4.6× faster.
- **Slides are read while the GPU transcribes** (videos of 10 minutes or more). A 16-frame sample supplies the spelling hints first.
- Keyframes are extracted 4 at a time, and ffmpeg is called directly instead of through package-manager launchers.
- Uploads were never the bottleneck: the 470 MB file took 3.1 s directly and 6.1 s through the development proxy.

### Added

- Cross-check tab: how the language was chosen (vote or test transcription, with the alternatives), and the interface text that was left out.
- "Tagalog / Filipino (incl. Taglish)" in the language menus.
- **Automatic install and updates.**
  - `start_app.bat` runs setup by itself when anything is missing.
  - `setup.bat` installs missing Python, Node.js and ffmpeg with winget; `setup.sh` uses Homebrew or apt.
  - After an update (`git pull` or a new ZIP), changed Python or JavaScript dependencies are installed before the app starts.
  - Setup uses `npm install` rather than `npm ci`, which would delete the packages of a running copy.
- **Documentation** for hardware and software requirements, with measured disk use; for getting the code from a repository or ZIP; and for updating without losing your library or settings.
- `.gitattributes` keeps Windows batch files in CRLF and shell scripts in LF, whatever machine clones the repository.
- Settings: `WHISPER_BATCH_SIZE`, `DIARIZATION_MODE`, `LLM_TRANSPORT`. `LLM_TIMEOUT` now defaults to 180 s.
- `timings.total` in results.
- Tests: 112 backend tests (was 70) and 19 frontend unit tests (was 14). The browser end-to-end test caught a speaker-clustering regression before release.

### Changed

- **More compact assistant context.** Consecutive sentences of one speaker form one line, with a fresh timestamp at least every minute, and a repeated slide is referenced instead of repeated. The 2.5-hour class is 135K characters.
- System prompt: speech may mix languages; answer in the user's language.
- Background ffmpeg processes are opted out of Windows power throttling, like the backend itself.

## 3.0.0 (2026-10-21)

A redesigned interface around a persistent library, plus three accuracy upgrades: the right model per machine, speaker identification, and stronger speech/screen cross-checking.

### Added

- **Library:** every recording is kept, listed as cards, playable, renameable, deletable and reprocessable with new settings (language, names & terms, speaker count). Recordings survive restarts; `JOB_TTL_HOURS=0` keeps them until deleted.
- **Speaker identification** (sherpa-onnx: pyannote segmentation + WeSpeaker, CPU, no token). Sentences split at speaker changes; speakers can be renamed everywhere; talk-time statistics; a speaker filter; voice turns on the scene track.
- **Full-text search** across every transcript, slide and title (SQLite FTS5), with highlighted snippets that jump to the moment.
- **Review tools:**
  - word-level karaoke highlighting, and click any word to seek;
  - underlines on words the model was unsure of;
  - inline "heard X → screen shows Y [Fix]" suggestions, plus "accept all high-confidence";
  - line editing and speaker reassignment;
  - captions (WebVTT) on the video, playback speed, ±5 s, and keyboard shortcuts.
- **Slide titles** detected from OCR (the tallest text) name scenes in the timeline, exports and AI context. **Duplicate slides** are recognised: periodic samples fold into one scene, and flip-backs reuse OCR.
- **Live meetings:**
  - "Tab + mic" keeps **You** and **Others** on separate channels, with echo removal;
  - every meeting is saved to the library from the first second (and recovered after a crash), then re-transcribed at full accuracy with speakers and slides;
  - live delay indicator, a big clock, title/language/glossary before starting, and screen-change cards with images.
- **Assistant:**
  - streaming answers with a Stop button, Markdown tables, and clickable timestamps;
  - quick prompts for decisions and a follow-up email;
  - questions across several selected recordings;
  - per-recording chat history, copy, save as note, and regenerate.
- **Exports:** Obsidian note (front matter) and plain text; print / save as PDF.
- **Per-upload options:** language, names & terms, speaker identification on/off, number of speakers, describe charts & images.
- Job cancellation, upload validation (ffprobe, length limit), toasts and desktop notifications when processing finishes, a setup checklist, dark mode, and a mobile layout with an assistant drawer.
- **Security:** a local-origin check on state-changing requests and the live WebSocket; a CSP and security headers for the served UI; WebSocket message size and session length limits; `LOCAL_ONLY` mode; prompt-injection guidance in the system prompt.
- `start_app.bat` picks free ports automatically. Added `start.sh` / `setup.sh` for macOS and Linux.
- **Tests:** 70 backend tests (API lifecycle, pipeline end to end on a generated video, search, diarization assignment, live commit policy), 14 frontend unit tests (Vitest), and a browser end-to-end test (`npm run e2e`) covering upload, review, search, the assistant, dark/mobile layouts and a live meeting.

### Changed

- **Interface redesign** from three references: a flat lime/black UI, pastel calendar cards with big numerals, and an editorial collage. See [DESIGN.md](DESIGN.md). Fonts and icons are bundled locally.
- **`WHISPER_MODEL=auto`** picks `large-v3-turbo` on GPUs with ≥ 5 GB (0% WER on the test meeting vs 3.8–5.1% for `base`), `small` on smaller GPUs and `base` on CPU. Live mode previews with a smaller model, and the final pass uses the main one.
- **The glossary is passed as `hotwords`,** re-sent with every 30-second window. As `initial_prompt` it silently stopped applying after the first minute of long recordings.
- **Glossary rarity filter** (Whisper tokenizer, judged on the lowercase form): drops common words that caused Title Case artefacts, and keeps product names such as Kubernetes.
- **Suggested fixes use more evidence:** Whisper's own word confidence and a phonetic key ("QBARnet's" → Kubernetes). Plural/tense variants are ignored, and abbreviations count as spoken ("Fri" → Friday).
- **Live commit policy:** a sentence must end with punctuation or be followed by a pause, and repeated words at the cut point are stripped (fewer one-word fragments).
- Decoder loops ("Thank you. Thank you. Thank you.") are collapsed.
- Parallel OCR (2 engines, 21% faster).
- The assistant's context is built server-side from job ids, so edits, renames and accepted fixes are always included.
- The initial JavaScript bundle shrank to 318 KB (99 KB gzip); the Markdown renderer loads on demand.

### Fixed

- A blank `LIVE_WHISPER_MODEL=` in `.env` produced an empty model name.
- `start_app.bat` failed when port 8000 was taken by another program.

## 2.0.0 (2026-10-20)

A rewrite of the prototype around accurate notes from audio **and** video.

### Fixed

- **The backend could not start.** `start_app.bat` ran `uvicorn main:app` in `backend/`, but `main.py` sat inside `backend/venv/`. The duplicate (`realtime_prototype.py`) was removed, and the real entry point is `backend/main.py`.
- **The AI assistant never worked.** The key check compared the key to itself, so it always showed "Setup Required". The OpenRouter key was also hard-coded in `App.jsx`, visible to anyone who loaded the page. The key now lives in `backend/.env` (gitignored), and chat goes through `POST /api/chat`. **Rotate the old key**: it was in plain text in frontend source.
- **Mute did nothing in live mode.** The 5 s interval read a stale `isMuted` value captured when the meeting started. Mute now disables the audio tracks.
- **Live transcription cut words at every 5 s boundary**, and dropped 200 ms of audio between chunks. It's replaced by continuous streaming with a sliding-window commit policy.
- **The server froze during transcription.** Whisper ran inside `async` handlers and blocked the event loop. It now runs in worker threads.
- **Path traversal and collisions in uploads.** The temp file was named `temp_{user filename}`. Uploads now get server-generated names in per-job folders, with a size limit.
- **Fake progress bar.** It was a timer climbing to 95%. It's replaced by real stage-by-stage progress from the backend.
- **`start_app.bat` shutdown killed any process on ports 8000/5173**, including unrelated programs. It now stops only the windows it started, and refuses to start if the backend port is taken.
- `prose` (Markdown) styles had no effect because `@tailwindcss/typography` wasn't installed, and `animate-in`/`fade-in` classes referenced a plugin that wasn't installed either.
- Page title was "frontend".

### Added

- **Video processing and audio/video cross-referencing** ([VIDEO_PROCESSING.md](VIDEO_PROCESSING.md)): scene detection, keyframes, local OCR, on-screen vocabulary fed to Whisper, speech-to-scene alignment, mis-transcription detection, "shown but not said" terms, optional vision captions, and a merged SPEECH/SCREEN context for the LLM.
- **Live screen reading:** shared tabs and screens are OCR'd when they change, and live speech is biased toward on-screen terms.
- **"Screen audio + mic" source** mixes both sides of a call.
- **Results UI:** video/audio player, keyframe strip, scene timeline, cross-check tab, follow-along highlighting, click-to-seek.
- **Exports:** Markdown notes, SRT, VTT, JSON.
- **Assistant:** quick prompts (Summary, Meeting notes, Action items, What was shown), clickable `[mm:ss]` timestamps, copy button, health warning when no key is configured.
- **Background job queue** with persistence across restarts, TTL cleanup, delete endpoint.
- Drag-and-drop upload, upload progress, backend status pill (engine, model, device).
- GPU support with automatic CPU fallback; Windows power-throttling opt-out.
- `setup.bat`, `.env.example` with every setting documented, `requirements*.txt`, `.gitignore`.
- Tests: 29 backend unit tests (cross-referencing, keyframe selection, sentence segmentation, live commit policy).
- Documentation in `docs/`.

### Changed

- Speech engine: openai-whisper → faster-whisper (2.1× faster on CPU, 5.1× with the GPU); openai-whisper remains as a fallback.
- Default LLM: `google/gemma-2-27b-it` (8K context, too small for long meetings) → `google/gemma-4-26b-a4b-it` (262K context, image input, about 8× cheaper per input token). Configurable via `LLM_MODEL`.
- Frontend split from one 430-line component into hooks, components and a small API layer. The dev server proxies `/api`, so there are no hard-coded backend URLs.
- CORS restricted to the frontend origins; methods limited to GET/POST/DELETE.

### Removed

- Unused Vite template files (`App.css`, `hero.png`, `react.svg`, `vite.svg`, `icons.svg`) and unused PostCSS/Autoprefixer dependencies.
- The `POST /transcribe` and `/ws/live` v1 endpoints; use `/api/jobs` and `/api/ws/live`.
