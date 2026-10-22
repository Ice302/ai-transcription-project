# Setup and configuration

## Requirements

### Hardware

| | Minimum | Recommended (tested) |
| --- | --- | --- |
| Operating system | 64-bit Windows 10 (1809 or newer) or 11, macOS, or 64-bit Linux | Windows 11 |
| Processor | 64-bit, 4 cores | 6 or more cores (tested: Intel Core i5-13450HX, 10 cores / 16 threads) |
| Memory | 8 GB RAM | 16 GB or more. A 2.5-hour recording needs about 1.5 GB in the backend; the rest is for the browser and other programs. |
| Graphics | none: speech recognition runs on the CPU with a smaller model | NVIDIA GPU with 6 GB of video memory and a driver that supports CUDA 12 (tested: RTX 4050 Laptop, 6 GB) |
| Disk space | about 2 GB, plus recordings | about 6 GB, plus recordings |

**Graphics cards.** With 5 GB of video memory or more, the accurate `large-v3-turbo` model is used. Smaller NVIDIA cards use `small`. AMD and Intel graphics and Apple Silicon run speech recognition on the CPU (`base` model). It works, but it is much slower than an NVIDIA GPU and less accurate on names and jargon. Measured times on the tested laptop are in [PERFORMANCE.md](PERFORMANCE.md); a 2.5-hour class takes about 6 minutes there.

**What uses the disk space** (measured on Windows):

| Item | Size | Where |
| --- | --- | --- |
| Python packages | 1.2 GB | `backend/venv` |
| NVIDIA CUDA libraries (only with an NVIDIA GPU) | 2.0 GB | `backend/venv` |
| Speech model | 1.6 GB (`large-v3-turbo`), 0.5 GB (`small`) or 0.15 GB (`base`) | Hugging Face cache in your user folder |
| Frontend packages | 0.15 GB | `frontend/node_modules` |
| Speaker identification model | 27 MB | `backend/models` |
| Python, Node.js, ffmpeg | about 0.4 GB together | installed system-wide |
| Your recordings | the original file, plus about 5 MB of slide images per hour (13 MB for a 2.5-hour class) | `backend/data` |

### Software

| Tool | Version | Why |
| --- | --- | --- |
| Python | 3.10–3.13 (tested 3.13) | Backend. Newer versions are not tested yet; setup picks a tested one if it is installed, or installs Python 3.12. |
| Node.js | 20 or newer (tested 24) | Frontend dev server, build, tests |
| ffmpeg + ffprobe | any recent version (tested 8.0) | Decoding, keyframes, live stream decoding |
| Browser | current Edge or Chrome | Firefox works too, except capturing a tab's sound for live meetings |
| git | any (optional) | Only for cloning and updating with `git pull` |

On Windows you don't need to install any of these by hand: setup installs whatever is missing with **winget**, the package manager built into Windows 10 and 11 (the "App Installer" app). By hand: `winget install Python.Python.3.12`, `winget install OpenJS.NodeJS.LTS` and `winget install Gyan.FFmpeg` (or `choco install python nodejs-lts ffmpeg`; macOS: `brew install python@3.12 node ffmpeg`; Debian/Ubuntu: `sudo apt install python3 python3-venv ffmpeg`, plus Node.js 20 from <https://nodejs.org/>, because Ubuntu's own Node.js is often older).

## Get the code

```bash
git clone <repository-url> TurboTranscribe
cd TurboTranscribe
```

Or download the repository as a ZIP (on GitHub: **Code → Download ZIP**) and extract it. Any folder works, including ones with spaces in the path.

## Install

Nothing needs to be installed by hand.

- **Windows:** double-click `start_app.bat`. If anything is missing it runs `setup.bat` first, then starts the app. You can also run `setup.bat` on its own.
- **macOS / Linux:** `./start.sh` runs `./setup.sh` when needed.

Setup does the following, and is safe to run again at any time:

1. **System tools.** It installs Python, Node.js and ffmpeg if they are missing (winget on Windows; Homebrew or apt on macOS/Linux). If a fresh install is not visible in the open window yet, it tells you to run it once more.
2. **Python packages.** It creates `backend/venv` and installs `backend/requirements.txt` (faster-whisper, RapidOCR, sherpa-onnx, FastAPI, …). With an NVIDIA GPU (`nvidia-smi` is found), it also installs the CUDA libraries.
3. **Frontend packages.** It runs `npm install` in `frontend/`.
4. **Settings.** It copies `backend/.env.example` to `backend/.env` if there isn't one. An existing `.env` is never overwritten.

Setup remembers what it installed: a copy of `requirements.txt` in `backend/venv/requirements.installed`, and of `package-lock.json` in `frontend/node_modules/.turbotranscribe-lock`. `start_app.bat` and `start.sh` compare these with the current files on every start. That is how an update that adds a package gets it installed automatically.

The models are not part of setup: they download on the first start (see below), so the first start needs an internet connection.

### By hand

```bash
cd backend
python -m venv venv
venv/Scripts/python -m pip install -r requirements.txt      # Linux/macOS: venv/bin/python
cp .env.example .env                                         # then edit it
cd ../frontend && npm install
```

## Updating

```bash
git pull
```

Then start as usual. Changed Python or JavaScript dependencies are installed before the app starts, as described above. Settings (`backend/.env`), your library (`backend/data/`), the installed packages and the downloaded models are all ignored by git (`.gitignore`), so an update never touches them.

With a ZIP download instead, extract the new version and copy `backend/.env` and `backend/data/` over from the old folder. The first start of the new folder then installs the packages again; the speech model is already cached in your user folder.

Moving to another computer works the same way: copy `backend/.env` and `backend/data/` to a fresh download.

## Run

```bat
start_app.bat          :: Windows
./start.sh             # macOS / Linux
```

Both start the backend and the frontend dev server and open the app. Ports 8000 and 5173 are preferred; if another program already uses one, the next free port is picked automatically and printed. The shutdown key in `start_app.bat` stops only the two windows it started.

By hand, in two terminals:

```bash
cd backend  && venv/Scripts/python -m uvicorn main:app --host 127.0.0.1 --port 8000
cd frontend && npm run dev                   # http://localhost:5173 (set BACKEND_URL if the backend isn't on 8000)
```

**What happens on first start.** Models download in the background while the API is already up. The status pill and the setup checklist in the library show progress:

- the speech model (`large-v3-turbo` on a GPU, about 1.6 GB; `base` on CPU, about 150 MB) from Hugging Face;
- the speaker identification model, about 27 MB (33 MB in `precise` mode), from the sherpa-onnx GitHub releases, into `backend/models/`;
- the OCR models, which ship inside the `rapidocr` package.

Uploads made before the models are ready simply wait in the queue.

**Single-process mode:** after `npm run build` in `frontend/`, the backend also serves the built app at `http://127.0.0.1:8000/`.

## GPU acceleration

faster-whisper uses CUDA when an NVIDIA GPU is detected **and** the CUDA 12 runtime libraries (cuBLAS, cuDNN 9) can be loaded:

```bash
venv/Scripts/python -m pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"
```

`app/transcriber.py` adds those packages' DLL folders to the search path on Windows. It also runs a one-second warm-up at load time: if the GPU can't actually run (missing libraries, driver problems), it logs a warning and falls back to CPU, re-choosing the model for CPU when `WHISPER_MODEL=auto`.

## Configuration reference (`backend/.env`)

Every setting is optional except the API key, which the assistant needs. Blank values mean "use the default". Restart the backend after editing.

### AI assistant

| Variable | Default | Notes |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | – | From <https://openrouter.ai/keys>. Never put it in frontend code. |
| `LLM_MODEL` | `google/gemma-4-26b-a4b-it` | Must fit whole transcripts: 262K-token context, low cost. |
| `VISION_MODEL` | empty (off) | e.g. `google/gemma-4-26b-a4b-it`. Describes charts and diagrams that OCR can't read. Per-upload toggle; costs per frame. |
| `VISION_MAX_FRAMES` | `12` | Cap on described frames per recording. |
| `LOCAL_ONLY` | `false` | `true` = nothing ever leaves the machine (assistant and captions disabled). |
| `LLM_CONTEXT_CHARS` / `LLM_TIMEOUT` | `400000` / `180` | Context cap; seconds per request. |
| `LLM_TRANSPORT` | `auto` | How requests reach OpenRouter. `auto` uses Windows' own `curl.exe` (Windows TLS) on Windows and `httpx` elsewhere. On a network that broke ~40% of large uploads from Python ("TLSV1_ALERT_DECODE_ERROR"), curl got through. Dropped connections are retried 3 times either way. |

### Speech recognition

| Variable | Default | Notes |
| --- | --- | --- |
| `WHISPER_MODEL` | `auto` | `large-v3-turbo` on a GPU with ≥ 5 GB, `small` on smaller GPUs, `base` on CPU. Or name one: `tiny` … `large-v3`, `distil-large-v3`. |
| `LIVE_WHISPER_MODEL` | `auto` | Model for the live preview: `small` on a GPU, `base` on CPU. Every meeting is redone with `WHISPER_MODEL` afterwards. |
| `WHISPER_ENGINE` | `auto` | `faster` (CTranslate2) or `openai` (PyTorch; `pip install openai-whisper`). |
| `WHISPER_DEVICE` / `WHISPER_COMPUTE_TYPE` | `auto` / `auto` | float16 on GPU, int8 on CPU. |
| `WHISPER_BEAM_SIZE` | `5` | Live mode uses 1. |
| `WHISPER_BATCH_SIZE` | auto | GPU only: how many 30-second windows are decoded at once. Auto = 16 with ≥ 8 GB of VRAM, else 8 (3.6 GB peak with `large-v3-turbo`). About 3× faster than one at a time; halves itself if the GPU runs out of memory. `1` = one window at a time. |
| `TRANSCRIBE_LANGUAGE` | auto-detect | Default language; uploads can override it. Auto-detect votes across 8 speech-rich 30-second windows from the whole recording. When two languages are close (Tagalog and English mixed, for example), it test-transcribes a sample in both and keeps the clearer one. For Taglish classes, `tl` usually works best. |
| `WORD_TIMESTAMPS` | `true` | Sentence segments, word highlighting, confidence underlines, speaker splitting. |

### Speaker identification

| Variable | Default | Notes |
| --- | --- | --- |
| `DIARIZATION` | `true` | Who said what. Per-upload toggle and optional speaker count. |
| `DIARIZATION_MODE` | `fast` | `fast`: one voice print per sentence, then clustering (5 s instead of 68 s for 10 minutes of a class). `precise`: full pyannote segmentation, which can also split a sentence where the speaker changes mid-way, but runs at about 8× real time on a laptop CPU. |
| `DIARIZATION_THRESHOLD` | `0.5` | Lower = more speakers. In fast mode, voices whose average voice prints are at least 0.8 alike are joined afterwards (one person heard through different microphones or rooms). If one person still shows up as two speakers, give the speaker count when reprocessing. |
| `MODELS_DIR` | `backend/models` | Where the speaker models are downloaded. |

### Video processing

| Variable | Default | Notes |
| --- | --- | --- |
| `VIDEO_PROCESSING` / `OCR_ENABLED` | `true` / `true` | |
| `OCR_THREADS` / `OCR_WORKERS` | `4` / `2` | Two 4-thread engines were 21% faster than one; three were not faster. |
| `OCR_MIN_CONFIDENCE` | `0.6` | Lines below this are dropped. |
| `VIDEO_SAMPLE_FPS` | `1.0` | Frames per second examined for scene changes. |
| `SCENE_THRESHOLD` | `0.02` | Fraction of pixels that must change to start a new scene. |
| `SCENE_MIN_GAP` / `SCENE_MAX_GAP` | `2` / `60` s | Debounce; periodic sample for long static shots (merged if identical). |
| `MAX_KEYFRAMES` | `150` | The biggest changes win if exceeded. |
| `VOCABULARY_SIZE` | `60` | On-screen terms offered to the speech model as spelling hints. |

### Library and server

| Variable | Default | Notes |
| --- | --- | --- |
| `KEEP_MEDIA` | `true` | Keep recordings for playback and reprocessing (live meetings are stored as compressed `.m4a`). |
| `JOB_TTL_HOURS` | `0` | Delete finished recordings after N hours; `0` keeps them until you delete them. |
| `MAX_UPLOAD_MB` / `MAX_MEDIA_MINUTES` | `4096` / `600` | Upload size and recording length limits (live sessions stop at the length limit). |
| `DATA_DIR` | `backend/data` | Recordings, keyframes, results, search index. |
| `CORS_ORIGINS` | localhost:5173 | Any `localhost` / `127.0.0.1` port is always allowed; add other origins (e.g. a LAN address) here. |

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Transcript is mostly ", so," or has very few words | The wrong language was used. Recordings made before version 3.1 picked it from the first 30 seconds only. Open the recording, press ↻ (**Reprocess with new settings**), and pick the language (for Taglish, *Tagalog / Filipino*) or leave it on auto-detect. |
| Assistant: "Couldn't reach OpenRouter" or `TLSV1_ALERT_DECODE_ERROR` | Something on the network is interfering with HTTPS: a VPN, antivirus "HTTPS scanning", or a school/office proxy. The app already retries 3 times using Windows' own TLS. If it keeps failing, try another network or turn off HTTPS scanning, then press **Try again**. |
| One person appears as several speakers | Reprocess with the number of speakers set, or raise `DIARIZATION_THRESHOLD` (e.g. 0.7). |
| Setup: "winget is not available" | Install **App Installer** from the Microsoft Store (it provides winget), or install the tool from the link shown, then run `setup.bat` again. |
| Setup: "installed but this window cannot see it yet" | Windows only updates `PATH` for new windows. Close the window and run `start_app.bat` (or `setup.bat`) again. |
| Setup: `pip` fails building a package | Usually an untested Python version. Install Python 3.12 (`winget install Python.Python.3.12`), delete `backend\venv`, and run setup again. |
| Setup: `EPERM` / "operation not permitted" from npm | A running copy of the app has the files open. Close the TurboTranscribe windows and run setup again. |
| Pill says "Backend offline" | The backend isn't running, or the dev proxy points elsewhere (`BACKEND_URL`). `start_app.bat` sets this for you. |
| `ffmpeg not found on PATH` | Install ffmpeg and restart the terminal / `start_app.bat`. |
| Pill shows `CPU` although you have an NVIDIA GPU | Install the CUDA libraries (above); check the backend window for the fallback warning. |
| "Speaker identification unavailable" in the setup check | The speaker-model download (27 MB; 33 MB in `precise` mode) failed (offline?). It retries on the next start; transcription works without it. |
| Live: "No audio was shared" | In the share dialog pick a **tab** and tick **Share tab audio** (or "Share system audio" for a whole screen). |
| Live: "You" lines duplicate the others | Your mic hears your speakers. Use headphones; duplicates are also removed when the meeting is re-processed. |
| Live text falls behind (Delay grows) | Use `LIVE_WHISPER_MODEL=base` or `tiny`, or a GPU. |
| A video won't play in the browser | Unusual codecs (some MKV/AVI/WMV). Keyframes and transcript still work; convert to MP4 for playback. |
| "Cross-site request blocked" | You opened the app from a non-local address; add it to `CORS_ORIGINS`. |
| Hugging Face symlink warning on Windows | Harmless. Enable Developer Mode or set `HF_HUB_DISABLE_SYMLINKS_WARNING=1`. |
