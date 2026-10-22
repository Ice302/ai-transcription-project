# API reference

Base URL: `http://127.0.0.1:8000` (or the port `start_app.bat` picked). In development the frontend calls `/api/...` on its own origin and Vite proxies it. Interactive docs are at `/docs` while the backend runs.

## Security

- Requests that change state (POST/PATCH/DELETE) and the WebSocket are rejected with `403` / close code `1008` when they come from a web page that isn't local (checked via the `Origin` header).
- Scripts and `curl` (no Origin) are fine. Add other origins with `CORS_ORIGINS`.

## Health

### `GET /api/health`

```jsonc
{
  "status": "ok",                       // "loading" while models load, "error" if loading failed
  "stage": "Ready", "error": null, "version": "3.0.0",
  "engine": "faster-whisper", "model": "large-v3-turbo", "live_model": "small", "device": "cuda",
  "ffmpeg": true, "video_processing": true, "ocr": true,
  "diarization": true, "diarization_error": null,
  "llm_configured": true, "llm_model": "google/gemma-4-26b-a4b-it", "vision_enabled": false,
  "local_only": false, "keep_media": true, "storage_bytes": 502731, "jobs": 2
}
```

## Recordings (jobs)

### `POST /api/jobs` → `202`

`multipart/form-data`:

| Field | Type | Notes |
| --- | --- | --- |
| `file` | file | Any audio/video ffmpeg can read |
| `language` | string | e.g. `en`, `pt-BR`; empty = auto-detect |
| `glossary` | string | Names & terms, comma or newline separated |
| `diarize` | bool | Identify speakers (default true) |
| `num_speakers` | int 1–20 | Optional, improves diarization |
| `describe_visuals` | bool | AI captions for keyframes (needs `VISION_MODEL`) |
| `title` | string | Optional title |

The file is probed before queueing. Errors:

- `415`: not audio/video;
- `413`: too large (`MAX_UPLOAD_MB`) or too long (`MAX_MEDIA_MINUTES`);
- `422`: invalid options.

Returns the job summary:

```jsonc
{ "id": "5446702baa0c", "filename": "standup.mp4", "kind": "file", "title": "standup",
  "status": "queued", "stage": "Queued", "progress": 0.0, "error": null,
  "created_at": 1792540800.1, "started_at": null, "finished_at": null,
  "options": { "language": "en", "glossary": "", "diarize": true, "num_speakers": null, "describe_visuals": false, "title": "" },
  "media": { "duration": 37.1, "has_audio": true, "has_video": true, "width": 1280, "height": 720, "audio_channels": 1 },
  "media_file": null, "has_media": false, "stats": {}, "size_bytes": 0 }
```

`status` is one of `recording | queued | running | done | error | cancelled`.

### `GET /api/jobs`

All recordings, newest first (summaries; `stats` filled once done).

### `GET /api/jobs/{id}`

The summary, plus `result` when `status == "done"`. The result format is described in [ARCHITECTURE.md](ARCHITECTURE.md#result-format-v3).

### `PATCH /api/jobs/{id}`

`{"title": "Weekly sync", "speakers": {"S1": "Priya"}}`. Either field is optional. Returns the updated result, or the summary if the job isn't done.

### `PATCH /api/jobs/{id}/segments/{segment_id}`

`{"text": "Corrected sentence.", "speaker": "S2"}`. `speaker` is optional; `""` clears it. Editing text drops that line's word timings (`edited: true`). Returns the updated result. `422` for an unknown speaker.

### `POST /api/jobs/{id}/corrections/{correction_id}`

`{"action": "accept" | "dismiss" | "reset"}`.

- `accept` rewrites the line (text and word timings). If the heard words are no longer in the line (e.g. after an edit), the status becomes `stale`.
- `reset` restores a dismissed suggestion.

Returns the updated result.

### `POST /api/jobs/{id}/corrections`

`{"confidence": "high" | "all"}` accepts every pending suggestion of that confidence. Returns the updated result.

### `POST /api/jobs/{id}/reprocess` → `202`

JSON with the same options as upload (`language`, `glossary`, `diarize`, `num_speakers`, `describe_visuals`). It re-runs the pipeline on the stored media. `409` if the media wasn't kept or the job is busy.

### `POST /api/jobs/{id}/cancel`

Cancels a queued or running job (`409` otherwise). A running job stops at its next progress update. Speaker identification can't be interrupted mid-way, so it finishes that stage first.

### `DELETE /api/jobs/{id}`

Deletes the recording, its files and its search rows (`409` while a live meeting is still recording).

### `GET /api/jobs/{id}/media`

The kept media file. Supports HTTP Range requests (seeking). `404` if not kept.

### `GET /api/jobs/{id}/frames/{NNNN}.jpg`

A keyframe. The name is validated against `^\d{4}\.jpg$`.

## Search

### `GET /api/search?q=postgres cluster`

Full-text search over every sentence, slide and title. Every word must match, and the last one also matches as a prefix. Results are grouped by recording:

```json
[{ "job_id": "5446702baa0c", "title": "standup", "kind": "file", "created_at": 1792540800.1,
   "hits": [{ "kind": "speech", "ref": 10, "t": 27.6, "speaker": "Priya",
              "snippet": "Marcus migrates the \u0001Postgres\u0002 \u0001cluster\u0002 by Friday." }] }]
```

`kind` is `speech`, `screen` or `title`. Matches in `snippet` are wrapped in `\u0001`…`\u0002`; render them as highlights and never as HTML.

## Assistant

### `POST /api/chat`

```json
{ "messages": [{ "role": "user", "content": "List the action items." }],
  "job_ids": ["5446702baa0c"], "context": "", "stream": true }
```

- **Context:** `job_ids` (up to 20) for recordings, built server-side from their current notes, edits included; `context` for a live meeting. Both can be combined.
- **Streaming:** with `stream: true` the response is `text/event-stream`. It sends `data: {"delta": "…"}` events, then `data: {"done": true, "model": "…"}`, or `data: {"error": "…"}`. Without `stream`: `{"reply": "…", "model": "…"}`.
- **Errors:** `503` when no key is configured or `LOCAL_ONLY` is on; `400` when there is nothing to analyze; `502` for provider errors.

## Live meetings — `WS /api/ws/live`

JSON text frames.

### Client → server

| Message | Meaning |
| --- | --- |
| `{"type":"start","channels":1\|2,"labels":["You","Others"],"glossary":"…","language":"en","title":"…","save":true}` | Optional, first. Two channels = left mic ("You"), right meeting audio ("Others"). |
| `{"type":"audio","data":"<base64>"}` | The next bytes of **one continuous** `MediaRecorder` stream (webm/opus, ogg or mp4), in order. |
| `{"type":"frame","t":12.5,"data":"<base64 jpeg>"}` | Screen frame captured `t` seconds after the start. Send only when the screen changed. |
| `{"type":"stop"}` | End: the server flushes, commits the remaining speech, saves, then replies `saved` and `done`. |

Messages over 8 MB are rejected. A session stops at `MAX_MEDIA_MINUTES`.

### Server → client

| Message | Meaning |
| --- | --- |
| `{"type":"ready","engine","model","ocr","job_id","channels"}` | Session open; the recording already exists in the library. |
| `{"type":"speech","id","t","end","text","speaker"}` | Final sentence (`speaker` is the channel label in two-channel mode). |
| `{"type":"partial","t","text","speaker","lag"}` | Unstable tail, replacing the previous partial for that speaker; `lag` = seconds of audio not yet committed. |
| `{"type":"retract","id"}` | Remove an earlier "You" line: it was echo of "Others". |
| `{"type":"visual","t","text","title","terms","image"}` | The screen changed; `image` is the stored keyframe URL. |
| `{"type":"correction","t","heard","seen","similarity"}` | A spoken word likely misheard, based on the screen. |
| `{"type":"error","message"}` | Non-fatal problem. |
| `{"type":"saved","job_id"}` | The meeting is queued for the full-accuracy pass. |
| `{"type":"done"}` | Reply to `stop`; safe to close. |

If the socket closes without `stop`, the recording is still saved and processed.
