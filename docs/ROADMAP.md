# Roadmap: 250 improvements

Ideas for taking TurboTranscribe further, grouped by area. Items are specific to this codebase; file references point to where the work would happen.

**Priority:** 🔴 high impact · 🟠 valuable · 🟢 nice to have.
**Status:** ✅ done in 3.0 or 3.1 (57) · ◐ partly done (16) · unmarked = open (177). Details in [CHANGELOG.md](CHANGELOG.md).

**Top 10 to do next:** #171 (rotate the leaked key: still open, only you can do it), #206 (put the project in git), #88 (name speakers from on-screen name tags), #67 (hierarchical summaries for long meetings), #20 (a WER benchmark set in CI), #22 (per-scene vocabulary), #49 (live auto-reconnect), #211 (desktop app), #105 (push progress instead of polling), #74 (retrieval instead of sending a whole 2.5-hour class every time).

---

## 1. Speech recognition accuracy (1–20)

1. ✅ 🔴 Offer `large-v3-turbo` as the default on GPUs: far more accurate than `base` and still faster than realtime on an RTX 4050. Auto-pick the model from detected VRAM in `transcriber.py`.
2. ✅ 🔴 Add a per-upload language selector in `BatchPanel` that is passed to the job; auto-detect fails on short clips and code-switching.
3. ✅ 🟠 Let users add a custom glossary (names, product terms) in the UI, merged with the OCR vocabulary into `initial_prompt`.
4. 🟠 Persist a per-user "learned vocabulary" from accepted corrections and reuse it in future jobs.
5. ✅ 🟠 Use the `hotwords` parameter of faster-whisper in addition to `initial_prompt` for stronger term biasing.
6. ✅ 🟠 Score glossary terms by token rarity (Whisper tokenizer pieces per word) so common words like "Owner" or "Action" stop polluting the prompt.
7. 🟠 Expose `temperature` fallback and `compression_ratio_threshold` in `.env` to tame hallucination loops on noisy audio.
8. ✅ 🟠 Detect and strip repeated-phrase hallucinations ("Thank you. Thank you. …") in post-processing.
9. 🟠 Run a second pass with a larger model only on low-confidence segments (`avg_logprob` below a threshold).
10. ✅ 🟠 Store `avg_logprob` / `no_speech_prob` per segment and shade low-confidence text in the UI.
11. 🟢 Add noise suppression (RNNoise via ffmpeg `arnndn`) as an optional pre-processing step for poor recordings.
12. 🟢 Normalize loudness (`loudnorm`) before transcription for quiet speakers.
13. ◐ 🟢 Support multi-track recordings (e.g. OBS, Zoom local recordings): transcribe each track separately for free speaker separation. *(3.0: two-channel live recordings (You / Others))*
14. 🟢 Add number/date normalization (inverse text normalization) so "forty two percent" renders as "42%" consistently.
15. 🟢 Offer translation output (`task="translate"`) alongside the original transcript.
16. 🟢 Expose VAD parameters (`min_silence_duration_ms`, threshold) for different meeting styles.
17. ✅ 🟢 Use the batched inference pipeline of faster-whisper (`BatchedInferencePipeline`) for long files on GPU. *(3.1: 8–16 windows at once, 2.2–3× faster)*
18. 🟢 Add punctuation and casing restoration for models or languages where Whisper omits them.
19. 🟢 Evaluate distil-whisper models for English-only, CPU-bound users and document the WER/speed trade-off.
20. 🟢 Build a small WER benchmark set (with references) and track accuracy per model in CI.

## 2. Video processing and cross-referencing (21–45)

21. ◐ 🔴 Apply high-confidence corrections automatically (with an "undo" per correction) instead of only suggesting them. *(3.0: one click accepts all high-confidence fixes; not automatic)*
22. 🟠 Do a second ASR pass per scene using that scene's OCR terms as the prompt, instead of one global glossary.
23. 🟠 Detect slides vs camera footage per keyframe and use different scene thresholds for each.
24. ✅ 🟠 Deduplicate near-identical keyframes (perceptual hash) when a presenter flips back to an earlier slide.
25. 🟠 Track incremental slide builds and show only the newly added bullet points per keyframe.
26. ◐ 🔴 Turn on vision captions by default when a key is present, but only for frames with little OCR text (charts, diagrams, demos), under a cost cap. *(3.0: per-upload toggle; still off by default)*
27. 🟠 Extract tables from slides into structured data (OCR boxes → rows/columns) for the notes.
28. 🟠 Recognize code on screen (monospace detection) and render it as code blocks in notes.
29. 🟠 Detect and OCR burned-in subtitles or captions as an extra transcript source to cross-check ASR.
30. 🟠 Read embedded subtitle streams (MKV/MP4 `subtitle` tracks) when present and use them as ground truth.
31. 🟠 Read chapter markers from the container and use them as section headings.
32. ✅ 🟠 Make OCR run in parallel with transcription (different hardware: CPU vs GPU) instead of sequentially. *(3.1: videos of 10+ minutes read the slides in a background thread while the GPU transcribes)*
33. 🟠 Let users pick the OCR language (`Rec.lang_type`) for non-Latin slides.
34. 🟢 Use GPU (CUDA/DirectML) execution providers for OCR when available.
35. 🟢 Crop to the shared-screen region in gallery-view meeting recordings before OCR.
36. ✅ 🟢 Recognize slide titles (largest text line) and use them as scene names in the timeline and notes.
37. 🟢 Detect the speaker's face on screen and associate it with diarized speakers.
38. 🟢 Detect a mouse pointer or laser dot and note which slide element is being discussed.
39. 🟢 Recognize URLs and email addresses on screen and make them clickable in notes.
40. 🟢 Add a "visual change intensity" track under the timeline to show where action happens.
41. 🟢 Generate an animated GIF or contact sheet of the keyframes for sharing.
42. 🟢 Support screen recordings with very small text by raising `Det.limit_side_len` adaptively for high-resolution frames.
43. 🟢 Match spoken numbers against on-screen numbers and flag discrepancies ("said 42%, slide shows 24%").
44. 🟢 Allow manual scene splitting and merging in the timeline UI.
45. 🟢 Cross-reference multiple uploaded files of the same meeting (e.g. separate slide PDF + audio recording).

## 3. Live meetings (46–65)

46. ✅ 🔴 Speaker separation in live mode by tracking which source (mic vs tab audio) produced the speech: "You" vs "Others".
47. ✅ 🔴 Fix fragment commits ("Their", repeated "Action") by requiring sentence punctuation or a longer pause before committing pause-split segments in `live.py`.
48. ✅ 🟠 Show a latency indicator (audio received vs transcript committed).
49. 🟠 Auto-reconnect the WebSocket with session resume instead of ending the meeting on a network blip.
50. ✅ 🟠 Persist live sessions as jobs so the meeting appears in history with the same timeline UI as uploads.
51. ✅ 🟠 Record the meeting audio (and optionally video) locally so it can be replayed with click-to-seek afterwards.
52. ✅ 🟠 Run a final high-accuracy batch pass over the recorded audio after the meeting ends and replace the live transcript.
53. 🟠 Send screen frames as binary WebSocket messages instead of base64 JSON (about 33% less bandwidth).
54. 🟠 Send audio as binary frames, too.
55. 🟠 Add a "bookmark this moment" button and keyboard shortcut during meetings.
56. 🟠 Live rolling summary every few minutes, shown in the assistant panel.
57. 🟠 Live action-item detection that pops up as the items are said.
58. 🟢 Push-to-talk mode for the microphone source.
59. 🟢 Adjustable screen-check interval and sensitivity in the UI.
60. 🟢 Show the captured screen preview while recording so users can confirm the right tab is shared.
61. 🟢 Pause/resume the whole session (not just mute).
62. 🟢 Detect long silences and auto-pause the session.
63. 🟢 Support Safari's `audio/mp4` MediaRecorder output explicitly and test it.
64. 🟢 Allow multiple concurrent live sessions with a per-session model pool.
65. 🟢 Warn when the browser tab is backgrounded and timers are throttled.

## 4. AI notes and summaries (66–85)

66. ✅ 🔴 Stream assistant responses (SSE) so long notes appear progressively.
67. 🟠 Hierarchical summarization for very long meetings: summarize per scene or chapter, then summarize the summaries.
68. 🟠 Notes templates: lecture, stand-up, sales call, interview, 1:1, with editable prompts.
69. 🟠 Auto-generate notes when a job finishes, so they are ready without asking.
70. 🟠 Structured JSON output for action items (task, owner, due date, timestamp) to power a checklist UI.
71. 🟠 Let users choose the model in the UI from an allow-list defined in `.env`.
72. 🟠 Cache answers per (context hash, prompt) to avoid paying twice for the same summary.
73. 🟠 Count tokens and show estimated cost before sending large contexts.
74. 🟠 Retrieval (embeddings) over long or multi-file contexts instead of sending everything every time.
75. 🟠 Cite scenes as clickable thumbnails in answers, not only timestamps.
76. 🟠 Verify LLM claims against the transcript (quote check) and highlight unsupported statements.
77. 🟢 Support local LLMs (Ollama / llama.cpp) for fully offline use.
78. 🟢 Generate flashcards and quizzes from lectures.
79. 🟢 Generate a glossary of terms with definitions from the content.
80. 🟢 Produce an executive one-paragraph TL;DR plus a detailed version.
81. 🟢 Detect decisions, risks and open questions as separate typed lists.
82. 🟢 Let users edit AI notes in place and save them with the job.
83. ✅ 🟢 Keep chat history per file or meeting instead of resetting on mode switch.
84. ◐ 🟢 Add "regenerate" and "make shorter / longer" actions on answers. *(3.0: regenerate is there; shorter/longer is not)*
85. ✅ 🟢 Prompt-injection hardening: wrap transcript content in delimiters and instruct the model to ignore instructions inside it.

## 5. Speakers and people (86–95)

86. ✅ 🔴 Speaker diarization (pyannote or NeMo) for uploaded files, merged into segments as `speaker` labels.
87. ✅ 🟠 Rename speakers in the UI and propagate the names through the transcript and notes.
88. 🟠 Use on-screen name tags (OCR of video-call tiles) to name diarized speakers automatically.
89. ✅ 🟠 Per-speaker talk-time statistics.
90. 🟠 Assign action-item owners from the speaker who accepted the task.
91. 🟢 Voice enrollment to recognize recurring participants across meetings.
92. ✅ 🟢 Show speaker turns as colored blocks on the timeline.
93. ✅ 🟢 Filter the transcript by speaker.
94. 🟢 Export per-speaker transcripts.
95. 🟢 Detect overlapping speech and mark it.

## 6. Performance and scalability (96–115)

96. 🟠 Stream decoding for very long files (chunked PCM) to cap memory: about 230 MB per hour of audio today.
97. 🟠 Process OCR in a separate process pool to use multiple cores without GIL or lock contention.
98. 🟠 Download and warm up models in `setup.bat` so the first start is instant.
99. 🟠 Unload idle models after a timeout to free VRAM and RAM on laptops.
100. 🟠 Configurable worker count for GPU servers with headroom for parallel jobs.
101. ✅ 🟠 Hardware-accelerated video decoding (`-hwaccel cuda/d3d11va`) for scene sampling on long videos. *(3.1: measured slower (CUDA 81 s, D3D11VA 290 s per 10 min vs 15 s); decoding only keyframes is 4.6× faster instead)*
102. 🟠 Skip decoding non-keyframes for scene sampling on very long videos (`-skip_frame nokey`) as a fast mode.
103. ✅ 🟠 Cancel a running job (cooperative cancellation between pipeline stages and segments).
104. ◐ 🟠 Resume interrupted jobs after a restart instead of marking them failed. *(3.0: interrupted live recordings are recovered; uploads are not resumed)*
105. 🟢 Replace job polling with Server-Sent Events for progress.
106. ◐ 🟢 Lazy-load keyframe images with thumbnails (generate 320 px versions) to cut page weight. *(3.0: images load lazily; no separate thumbnails yet)*
107. 🟢 Virtualize long transcripts in the UI (thousands of segments).
108. ✅ 🟢 Code-split the Markdown renderer so the initial bundle is smaller.
109. 🟢 Compress `result.json` (gzip) on disk and over HTTP (`GZipMiddleware`).
110. 🟢 Benchmark `int8_float16` on GPU to save VRAM for larger models.
111. 🟢 Pin onnxruntime threads relative to `os.cpu_count()` and core type, not a fixed 4.
112. 🟢 Add a `/api/metrics` endpoint (queue depth, stage durations, realtime factor).
113. 🟢 Profile and reduce the Python overhead in `find_corrections` for multi-hour transcripts (precompute n-grams).
114. 🟢 Deduplicate uploads by content hash and reuse existing results.
115. 🟢 Offer an "audio only" quick mode for videos where visuals don't matter.

## 7. Backend architecture and code quality (116–135)

116. 🟠 Add type checking (mypy or pyright) to the backend in strict mode.
117. 🟠 Add Ruff for linting and formatting, with a pre-commit hook.
118. 🟠 Use Pydantic models for job results instead of raw dicts, and publish them in the OpenAPI schema.
119. 🟠 Move from module-level globals (`models`, `jobs`) to FastAPI dependency injection for testability.
120. 🟠 Add structured JSON logging with job ids.
121. ◐ 🟠 Replace the in-memory job index with SQLite so jobs can be queried and filtered. *(3.0: search index is SQLite; the job index is still JSON files)*
122. 🟠 Define an engine interface (ASR, OCR, LLM) so alternatives can be plugged in via config.
123. 🟠 Version the API (`/api/v1`) before external clients exist.
124. 🟠 Centralize error types and return consistent error JSON (`code`, `message`).
125. 🟢 Make pipeline stages composable and individually re-runnable (e.g. redo OCR only).
126. ✅ 🔴 Add an end-to-end API test using a generated video (ffmpeg `drawtext` + TTS), like the one used to validate 2.0, to the test suite.
127. 🟢 Graceful shutdown that waits for the current job, with a timeout.
128. 🟢 Validate `.env` on startup and print a readable summary of the effective settings.
129. 🟢 Replace `print`-style progress strings with stage enums plus i18n-able labels.
130. 🟢 Split `main.py` routes into routers (`jobs`, `chat`, `live`, `health`).
131. 🟢 Add `pyproject.toml` with pinned, hashed dependencies (uv or pip-tools).
132. 🟢 Python 3.13 free-threading readiness check for OCR and ASR threads.
133. 🟢 Add docstrings with examples to all public functions in `crossref.py`.
134. 🟢 Make `frame_url` and data paths injectable for alternative storage backends.
135. 🟢 Health check that verifies ffmpeg can decode a tiny built-in sample.

## 8. Frontend UX (136–160)

136. ✅ 🟠 Job history sidebar loaded from `GET /api/jobs`, so results survive a page reload.
137. ✅ 🟠 Keep the original media (opt-in) so history items stay playable after reload.
138. ✅ 🟠 Search within a transcript, highlighting matches on the timeline.
139. ✅ 🟠 Inline transcript editing with save, and corrected text used for notes.
140. ✅ 🟠 One-click "accept correction" chips inside the transcript text.
141. ✅ 🟠 Keyboard shortcuts: space play/pause, J/K/L seek, / search.
142. ◐ 🟠 Playback speed control and "skip silence". *(3.0: playback speed is there; skip-silence is not)*
143. ✅ 🟠 Dark mode.
144. ✅ 🟠 Remove a queued job before it starts (cancel button).
145. 🟠 Show estimated time remaining from the job's realtime factor.
146. ✅ 🔴 Onboarding: first-run checklist (backend reachable, ffmpeg, model, API key) built on `/api/health`.
147. ✅ 🟢 Drag-and-drop anywhere on the page, not just the drop zone.
148. 🟢 Paste a URL (YouTube or any direct link) to download and transcribe (yt-dlp).
149. 🟢 Side-by-side view: slide on the left, transcript on the right, synced.
150. 🟢 Picture-in-picture video while scrolling the transcript.
151. ✅ 🔴 Toast notifications plus a browser notification when long jobs finish.
152. 🟢 Resizable chat panel.
153. 🟢 Show which file a chat answer refers to when multiple files are loaded.
154. 🟢 "Copy as rich text" for pasting notes into email or docs.
155. 🟢 Settings page for scene sensitivity, model and language, saved per user.
156. 🟢 Empty-state sample file to try the app instantly.
157. 🟢 Timeline zoom for long recordings.
158. ◐ 🟢 Mobile layout polish: sticky player, collapsible chat. *(3.0: responsive layout and assistant drawer; no sticky mini-player)*
159. 🟢 Migrate the frontend to TypeScript.
160. 🟢 Introduce a component library or design tokens for consistent styling.

## 9. Accessibility and internationalization (161–170)

161. ◐ 🟠 Full keyboard navigation and visible focus states for all controls. *(3.0: focus rings, labelled icon buttons, skip link; no full audit yet)*
162. ✅ 🟠 ARIA live region announcing new live-transcript lines for screen-reader users.
163. 🟠 Alt text for keyframes generated from OCR or captions.
164. ✅ 🟠 Caption overlay on the video player from the transcript (WebVTT track).
165. 🟢 Color-contrast audit (WCAG AA) of chips and badges.
166. ✅ 🟢 Respect `prefers-reduced-motion` for pulsing indicators and smooth scrolling.
167. 🟢 UI translations (i18n framework) starting with the most-used transcript languages.
168. 🟢 Right-to-left layout support for Arabic and Hebrew transcripts.
169. 🟢 Adjustable transcript font size.
170. 🟢 Dyslexia-friendly font option.

## 10. Security and privacy (171–190)

171. 🔴 Rotate the OpenRouter key that was previously hard-coded in `App.jsx`, and check that no copy remains elsewhere (old builds, backups).
172. 🟠 Optional authentication (single shared token) when the backend is exposed beyond localhost.
173. 🟠 Rate-limit `/api/chat` and uploads.
174. ✅ 🟠 Validate uploads by probing before queueing; reject non-media early with a clear error.
175. ✅ 🟠 Enforce maximum media duration and maximum resolution to avoid resource exhaustion.
176. ✅ 🟠 Content Security Policy and security headers for the served frontend.
177. ◐ 🟠 A clear privacy notice in the UI: what stays local, what goes to OpenRouter. *(3.0: the setup checklist explains what is local; no dedicated notice)*
178. ✅ 🟠 A "local only" switch that disables all external calls.
179. 🟠 Redact PII (emails, phone numbers, card numbers) from the context before sending it to the LLM (opt-in).
180. 🟠 Encrypt stored results at rest (optional key in `.env`).
181. 🟢 Secure deletion of job folders on delete or expiry.
182. 🟢 Audit log of LLM requests (timestamp, size, model), without content.
183. 🟢 Dependency vulnerability scanning (`pip-audit`, `npm audit`) in CI.
184. 🟢 Run ffmpeg with resource limits and timeouts to contain malformed media.
185. 🟢 Sandbox OCR and ffmpeg in a subprocess with lower privileges.
186. 🟢 Bind to localhost by default everywhere and document the risks of `--host 0.0.0.0`.
187. ✅ 🟢 Validate WebSocket `Origin` to stop other websites from opening live sessions.
188. ✅ 🟢 Limit WebSocket message size and session duration.
189. 🟢 Signed, expiring URLs for keyframe images if multi-user.
190. 🟢 Recording-consent reminder before starting a live meeting.

## 11. Testing and QA (191–205)

191. ✅ 🟠 Frontend unit tests (Vitest) for `format.js` exports and `liveContext.js`.
192. ✅ 🟠 Playwright end-to-end tests: upload flow, chat with a mocked LLM, live mode with a fake microphone (all of these were exercised manually for 2.0).
193. ✅ 🟠 Backend API tests with `TestClient` and a fake processor for the jobs endpoints.
194. ◐ 🟠 WebSocket protocol tests for `LiveSession` using a short generated webm stream. *(3.0: the commit policy is unit-tested; the protocol was tested with a script, not in CI)*
195. 🟠 Golden-file tests for `build_notes_context` output.
196. 🟢 Property-based tests (Hypothesis) for `assign_scenes` and `resegment`.
197. 🟢 Regression corpus of tricky media: no audio, audio-only MP4, cover-art MP3, variable frame rate, portrait video.
198. 🟢 Performance regression tests (OCR per frame, ASR realtime factor) with thresholds.
199. 🟢 Test the GPU fallback path by simulating missing CUDA libraries.
200. 🟢 Visual regression snapshots of key UI states.
201. 🟢 Accessibility tests (axe) in the Playwright suite.
202. 🟢 Load test: 20 queued uploads, confirm ordering and memory stability.
203. 🟢 Fuzz the upload endpoint with malformed files.
204. ◐ 🟢 Contract test for the OpenRouter response format, with recorded fixtures. *(3.1: streaming, error bodies and retries are tested with a fake transport)*
205. 🟢 Coverage reporting with a minimum threshold in CI.

## 12. DevOps, packaging and deployment (206–220)

206. 🟠 Initialize a git repository and commit the current state; the project has no version control yet.
207. 🟠 GitHub Actions CI: pytest, ruff, oxlint, vite build on every push.
208. 🟠 Dockerfile (CPU) and a CUDA variant, with ffmpeg included.
209. 🟠 `docker-compose.yml` for one-command startup.
210. ✅ 🟠 Cross-platform launch scripts (`start.sh`) for macOS and Linux.
211. 🔴 Package as a desktop app (Tauri or Electron) with the backend bundled, so there are no terminals or ports for end users.
212. 🟢 Windows installer (Inno Setup) that installs ffmpeg and creates shortcuts.
213. 🟢 Automatic model download progress shown in the UI during first start.
214. 🟢 Semantic versioning and release notes generated from the changelog.
215. 🟢 Renovate or Dependabot for dependency updates.
216. 🟢 Run the backend as a Windows service or background tray app.
217. ✅ 🟢 Auto-pick free ports in `start_app.bat` instead of failing when one is taken.
218. 🟢 A `make`/`just` task file for common commands.
219. 🟢 Pre-built wheels cache for offline installs.
220. 🟢 Telemetry-free crash reports saved locally for bug reports.

## 13. Data, storage and search (221–235)

221. ✅ 🟠 Full-text search across all past transcripts and screen text (SQLite FTS5).
222. 🟠 Semantic search ("when did we discuss pricing?") with local embeddings.
223. 🟠 Tags and folders for organizing recordings.
224. ✅ 🟠 Ask questions across multiple meetings ("what did we decide about Postgres this month?").
225. ◐ 🟠 Configurable retention per job (keep forever / auto-delete). *(3.0: global TTL or keep-forever; not per recording)*
226. 🟢 Storage usage view with cleanup suggestions.
227. 🟢 Import existing transcripts (SRT/VTT/TXT) to use the assistant on them.
228. 🟢 Import a slide deck (PDF/PPTX) and align it to an audio recording, for when only audio was recorded.
229. 🟢 Backup and restore of the data directory.
230. 🟢 Store keyframes as WebP to halve disk usage.
231. 🟢 Keep job metadata (duration, language, participants) for dashboards.
232. ◐ 🟢 Topic segmentation across the transcript with auto-generated chapter titles. *(3.0: slide titles act as chapter names)*
233. 🟢 Keyword trend view across meetings.
234. 🟢 Link related meetings automatically by shared vocabulary.
235. 🟢 Export the whole library as a zip of Markdown files.

## 14. Integrations and export (236–250)

236. ◐ 🟠 Export notes to DOCX and PDF with embedded keyframe images. *(3.0: PDF via print; no DOCX)*
237. 🟠 Send notes to Notion, Confluence or Google Docs.
238. 🟠 Create tasks from action items in Jira, Linear, Todoist or Microsoft To Do.
239. 🟠 Email a summary to participants after a meeting.
240. 🟠 Post summaries to Slack or Teams channels via webhook.
241. 🟢 Calendar integration to name live sessions after the current meeting.
242. 🟢 Zoom, Teams and Google Meet cloud-recording import.
243. ✅ 🟢 Obsidian-friendly Markdown export with front matter and backlinks.
244. 🟢 Anki deck export for lecture flashcards.
245. 🟢 Browser extension that starts a live session from the meeting tab in one click.
246. 🟢 Public REST API tokens for scripting batch transcription.
247. 🟢 Watch-folder mode: auto-transcribe files dropped into a directory.
248. 🟢 Export subtitles burned into the video (ffmpeg `subtitles` filter).
249. 🟢 Export the scene timeline as a slide-by-slide PDF handout.
250. 🟢 Webhook on job completion for automation tools (Zapier, n8n).
