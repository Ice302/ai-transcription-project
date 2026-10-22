# Performance

All numbers were measured on the development machine: Intel Core i5-13450HX (6 performance + 4 efficiency cores, 16 threads), 24 GB RAM, NVIDIA RTX 4050 Laptop GPU (6 GB), Windows 11, on AC power.

## Version 3.1 (2026-10-22)

Test media: a real **2.5-hour university class recorded from Zoom** (1920×1080, 60 fps MKV, 470 MB, 9,094 s). One teacher speaks Tagalog and English mixed within sentences, over PowerPoint slides with equations. Zoom's toolbar and participant strip surround the slide. Both 3.1 runs were measured while a game (Roblox) used about 4 CPU cores and part of the GPU, with the GPU at 85 °C and its clock throttled. These are numbers from a busy laptop, not a clean benchmark.

### Results on the class

| | 3.0 | 3.1 |
| --- | --- | --- |
| Language | English (first 30 s only, 61% sure) | **Tagalog**, 95% of the vote over 8 windows |
| Words | 1,015 | **15,310** |
| Sentences | 466 (316 of them ", so,") | **1,877** |
| Speakers | 4 | **1** (the teacher; one voice was split into two at 0.91 similarity before the merge rule) |
| Zoom buttons and names in titles, bullets, hints | most scenes | **none**: 17 interface labels (buttons, participant names, REC) removed from every scene |
| Suggested fixes | 28 with the 3.0 rules, 1 useful | **3**, 2 useful ("undounded" → Unbounded, "FND Math" → FNDMATH) |
| Assistant ("Summary") | failed: `TLSV1_ALERT_DECODE_ERROR` | first words after 6 s, finished in 73 s, with timestamps |
| Assistant context | – | 135K characters |

### Time per stage (seconds)

| Stage | 3.0 | 3.1, first fix (one stage after another) | 3.1 final, busy | 3.1 final, via the app |
| --- | --- | --- | --- | --- |
| Probe | 0.1 | 1.9 | 0.1 | 0.2 |
| Decode audio | 13.4 | 73.2 | 19.6 | 12.0 |
| Read 16 sample frames (spelling hints) | – | – | 26.5 | 15.1 |
| Language detection | – | 10.1 | 7.4 | 5.3 |
| Scene detection | 251.3 | 78.7 | 60.5 ∥ | 37.0 ∥ |
| Keyframe extraction | 42.1 | 88.9 | 18.0 ∥ | 10.1 ∥ |
| OCR | 185.6 | 242.3 | 283.3 ∥ | 136.2 ∥ |
| Transcription | 2,424 (with speakers) | 296.7 | 355.9 | 218.5 |
| Speaker identification | (in the row above) | 124.0 | 90.9 | 82.1 |
| Cross-reference | 0.4 | 4.3 | 2.6 | 2.5 |
| **Total** | **2,916 (48.6 min)** | **920 (15.3 min)** | **503 (8.4 min)** | **336 (5.6 min)** |

∥ ran in a background thread during transcription, so it is not part of the total. "Busy" = a game used about 4 CPU cores and the GPU (85 °C, clock throttled); "via the app" = the same game open but mostly idle, through the real API (reprocess).

### Component benchmarks

| Component (10-minute excerpt unless noted) | Before | After |
| --- | --- | --- |
| Transcription, GPU, `large-v3-turbo` | 37 s, one 30-s window at a time | 12.5–16.8 s batched ×8 (3.6 GB VRAM peak); 10.8–11.2 s ×16 (4.7 GB); 95% of words identical |
| Speaker identification | 67.8 s (segmentation + embeddings) | 5.4 s (one voice print per sentence); 95% agreement; test dialogue 12 of 12 |
| Scene scan of 1080p60 video | 15.2 s, every frame decoded | 3.3 s, keyframes only (CUDA decoding: 81 s, D3D11VA: 290 s; both slower) |
| Language detection, whole class | first 30 s: English, 61% | 8 windows: Tagalog, 95%, 5.5 s |
| OCR of one class frame (49 text boxes incl. Zoom's) | 1.30 s at 960 px | 1.01 s at 736 px, but equations were lost ("x-1=0", "2x-5=0"), so 960 px stays |
| OCR pool on class frames | – | 0.94 s/frame with 2 engines, 0.98 with 3 |
| Keyframe extraction (136 frames, 4 at a time) | 42 s one at a time via the Chocolatey launcher | 10–18 s, calling the real ffmpeg directly |
| Upload of the 470 MB file | – | 3.1 s directly, 6.1 s through the Vite dev proxy: not a bottleneck |

### Network

Requests to OpenRouter with the class context (155K characters) from the development machine:

| Transport | Result |
| --- | --- |
| Python `httpx` (OpenSSL), 400 KB body | 3 of 5 succeeded; failures were `TLSV1_ALERT_DECODE_ERROR` / connection resets |
| Windows `curl.exe` (Schannel), 400 KB body | 5 of 5 (11 of 11 in an earlier series); once later `SEC_E_MESSAGE_ALTERED`, which a retry fixed |
| gzip-compressed body | rejected by OpenRouter ("JSON parsing failed") |

Hence 3.1 uses curl on Windows, retries dropped connections, and keeps the context compact.

## Version 3 (2026-10-21)

Test media: `frontend/e2e/fixtures/standup.mp4`, a 37 s, 3-slide meeting with **two voices** (Windows SAPI "Zira" and "David") alternating over six lines. The script deliberately uses names and jargon (Kubernetes, Grafana, Snowflake, Postgres, Terraform, Priya, Marcus Okafor); the slides carry details that are never spoken (ARR impact: 1.2M USD).

### Accuracy

| | Word error rate vs. the exact script (78 words) | Notes |
| --- | --- | --- |
| `base`, GPU | 3.8% and 5.1% (two runs) | "QBARnet's"/"Cubarnet's" for Kubernetes, "move"/"tune" for moved/tuned |
| `large-v3-turbo`, GPU | **0.0%** | the `auto` choice on GPUs with ≥ 5 GB |

| Speaker identification | Result |
| --- | --- |
| Turns found (pyannote seg-3.0 + WeSpeaker, threshold 0.5) | **6 of 6 turns, all correct**, 0.1–0.6 s boundary error |
| Threshold 0.7 / 0.9 | merged both voices into one speaker (why 0.5 is the default) |
| Sentences attributed correctly after `assign_speakers` (turbo run) | **12 of 12** |
| Two-channel live, mic hearing the meeting at 30% volume | every echoed line retracted live; final pass: **12 of 12** correct, no duplicates |

| Cross-referencing evidence | Before the fix | After |
| --- | --- | --- |
| Glossary when the rarity filter checked capitalised words | "Kubernetes" dropped (1 token capitalised); "Migration", "Costs", "Items", "Schedule" kept | lowercase check: Kubernetes kept, common words dropped |
| Title Case leaking into speech (`base`) | "Migration Status", "Snowflake Costs", "Postgres Cluster" | gone |
| "QBARnet's" (67% alike in spelling, heard with 22% certainty) | not flagged | flagged as **Kubernetes**, high confidence (sound + uncertainty) |
| "Fri", "Tue" on the slide | listed as never said | matched to "Friday", "Tuesday" |

The glossary also moved from `initial_prompt` to `hotwords`. `initial_prompt` only reaches the first 30-second windows (the decoder's own output replaces it), so on long recordings the vocabulary hints silently stopped applying. `hotwords` is re-sent with every window.

### Speed

| Stage (37 s video, GPU, `large-v3-turbo`) | Time |
| --- | --- |
| Probe + decode | 0.30 s |
| Scene detection + keyframes | 0.66 s |
| OCR (3 slides, 2 engines) | 1.74 s (includes loading the second engine) |
| Transcription + speaker identification | 6.79 s |
| Cross-reference | 0.03 s |
| **Total** | **9.5 s** (3.9× realtime, with speakers) |

| Component | Measurement |
| --- | --- |
| `large-v3-turbo` vs `base` on GPU (transcription + speakers) | 6.8 s vs 5.6 s: the much more accurate model costs about 20% more time |
| Speaker identification on CPU | 4.2–4.7 s per 37 s (8–9× realtime); 8 threads ≈ 4 threads; the int8 segmentation model was not faster |
| OCR pool, 24 frames | 1 engine 0.43 s/frame · **2 engines 0.34 s/frame** (−21%) · 3 engines 0.43 s/frame |
| Live preview delay (`small`, GPU, two channels) | about 1.3 s behind speech |

### Frontend

| | v2 | v3 |
| --- | --- | --- |
| Initial JavaScript | 340 KB (106 KB gzip) | **318 KB (99 KB gzip)**, despite the library, editor, live and assistant views |
| Lazy-loaded | — | Markdown + tables, 154 KB (46 KB gzip), only once the assistant answers |
| Fonts | system | Geist, Geist Mono and Instrument Serif bundled (about 95 KB of Latin woff2; no CDN, works offline) |
| Word highlighting during playback | — | updates about 15×/s; only the active line re-renders (memoized lines) |

## Version 2 (2026-10-20)

Measured with the `base` model. Test media: a 25 s, 1280×720, 3-slide video with synthesized narration (Windows SAPI), and the same audio looped to 100 s for the speech benchmark.

### Headline results

| Workload | Before | After (v2) |
| --- | --- | --- |
| 25 s slide video, end to end with video processing (v1 had none; "before" = first untuned v2 draft) | ~30 s; 1 of 3 scenes found | **4.3 s**; all 3 scenes |
| Speech recognition, 100 s audio, CPU | 16.5 s (openai-whisper) | **7.9 s** (faster-whisper int8) |
| Speech recognition, 100 s audio, GPU | not supported (CPU-only PyTorch) | **3.2 s** (31× realtime) |
| OCR, one 720p frame (sustained) | 5–20 s, erratic | **0.40 s**, steady |
| Server while transcribing | blocked; every request waits | responsive (thread pool) |
| Live-mode word accuracy at chunk edges | words cut at every 5 s boundary | continuous stream; no cuts |

### What made the difference

#### 1. faster-whisper instead of openai-whisper

| Engine | Device | 100 s audio | Realtime factor |
| --- | --- | --- | --- |
| openai-whisper (PyTorch) | CPU | 16.45 s | 6.1× |
| faster-whisper (CTranslate2, int8) | CPU | 7.85 s | 12.7× |
| faster-whisper (float16) | RTX 4050 | 3.21 s | 31.1× |

The GPU was always present, but the installed PyTorch is a CPU build, so the old backend could never use it. CTranslate2 plus the pip-installed cuBLAS/cuDNN runtime enables the GPU. A warm-up probe falls back to CPU if those libraries are missing.

faster-whisper's built-in **VAD** also skips silence: it removed 5.5 s of the 25 s test clip before decoding, which makes it faster and avoids Whisper's habit of inventing "Thank you." during silence.

#### 2. Windows power throttling (EcoQoS)

Windows 11 moves processes without a foreground window, like the backend in its minimized console, onto efficiency cores at reduced clock speed. Same process, same image, 10 consecutive OCR calls:

| | Per-frame OCR time (s) |
| --- | --- |
| Default | 0.90, 0.83, **5.28, 5.14, 5.33, 5.51, 5.43, 5.66, 5.35, 5.28** |
| `SetProcessInformation(ProcessPowerThrottling)` opt-out | 0.91, 0.44, 0.43, 0.49, 0.42, 0.40, 0.40, 0.41, 0.41, 0.40 |

The first runs are fast until Windows classifies the process as background. `app/platform_tuning.py` opts out at startup. CPU transcription benefits the same way.

#### 3. OCR configuration

RapidOCR defaults vs the tuned settings (same text recognized in every case):

| Settings | Per-frame time (s), 8 runs |
| --- | --- |
| Default (all cores, angle classifier, no size cap) | 1.3–20, erratic |
| Classifier off, max side 960 px, 4 intra-op threads, 1 inter-op | 0.92, 0.44, 0.41, 0.41, 0.41, 0.40, 0.40, 0.42 |
| Same with all cores | 0.78–1.34 |
| Same with 2 threads | ~0.65 |

More threads were slower: oversubscription on a hybrid CPU. `OCR_THREADS=4` is the default.

#### 4. Scene detection metric

Frame-to-frame difference on the test video at the two slide changes (7–8 s and 16–17 s):

| Metric | Slide change | Static frames |
| --- | --- | --- |
| Mean absolute difference (v1 plan) | 0.012, 0.008 | 0.000 |
| Fraction of pixels changed > 24/255 (v2) | 0.050, 0.033 | 0.000 |

Scene detection costs **0.19 s** for the 25 s video: one ffmpeg pass straight to 64×36 grayscale, compared in NumPy.

#### 5. Other optimizations

- **No temp files for audio:** ffmpeg decodes straight to a NumPy array over a pipe, for uploads and the live stream alike. The v1 server wrote every 5 s live chunk to disk, transcribed it, and deleted it.
- **Uploads stream to disk** in 1 MB chunks, instead of buffering in a `SpooledTemporaryFile` and copying.
- **Polling only while needed:** the frontend polls just the jobs still in flight, once per second, and stops when they finish.
- **Change-detected screen frames in live mode:** a 64×36 diff in the browser means frames are only uploaded and OCR'd when the screen changes. OCR results more than 90% similar to the previous text are suppressed.
- **Frontend bundle:** template leftovers (unused CSS, images, PostCSS, Autoprefixer) removed. The production build is 339 KB JS (106 KB gzip) and 42 KB CSS.

### Per-stage timings

Every result includes `timings`. For the 25 s test video on the GPU:

| probe | decode audio | scene detection | keyframes | OCR (3 frames) | transcription | cross-reference |
| --- | --- | --- | --- | --- | --- | --- |
| 0.16 s | 0.13 s | 0.19 s | 0.48 s | 2.84 s* | 0.89 s | 0.02 s |

\* Includes OCR model warm-up in a fresh process. Sustained, it's about 0.4 s per frame.

For long videos, expect OCR to be about 0.4 s × number of keyframes (capped by `MAX_KEYFRAMES`), and transcription at roughly 13× realtime on CPU or 30× on this GPU with `base`.

## Reproducing

The benchmark scripts are simple Python loops around `OcrEngine.read` and `Transcriber.transcribe`. Each result's `timings` field and the backend log (`faster_whisper: Processing audio with duration …`) give per-file numbers.
