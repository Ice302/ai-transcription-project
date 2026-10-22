"""HTTP API tests against the real app with the ML pipeline swapped for a fake processor."""
import io
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.media import write_wav

LOCAL = {"Origin": "http://localhost:5173"}


def fake_processor(job, src, report):
    report("Transcribing speech", 0.5)
    return {
        "filename": job.filename, "title": job.title, "media": {"duration": 2.0, "has_audio": True, "has_video": False},
        "options": job.options, "language": job.options.get("language") or "en",
        "speakers": [{"id": "S1", "name": "Speaker 1", "talk_time": 1.0}, {"id": "S2", "name": "Speaker 2", "talk_time": 1.0}],
        "segments": [
            {"id": 0, "start": 0.0, "end": 1.0, "text": "Marcus migrates post gres on Friday.", "speaker": "S1",
             "scene_id": None, "edited": False,
             "words": [[0, 0.2, " Marcus", 0.9], [0.2, 0.5, " migrates", 0.9], [0.5, 0.7, " post", 0.4],
                       [0.7, 0.8, " gres", 0.4], [0.8, 0.9, " on", 0.9], [0.9, 1.0, " Friday.", 0.9]]},
            {"id": 1, "start": 1.0, "end": 2.0, "text": "Okafer agrees.", "speaker": "S2", "scene_id": None,
             "edited": False, "words": [[1.0, 1.5, " Okafer", 0.5], [1.5, 2.0, " agrees.", 0.9]]},
        ],
        "keyframes": [],
        "corrections": [
            {"id": 0, "segment_id": 0, "t": 0.0, "heard": "post gres", "seen": "Postgres", "similarity": 1.0,
             "confidence": "high", "status": "pending"},
            {"id": 1, "segment_id": 1, "t": 1.0, "heard": "Okafer", "seen": "Okafor", "similarity": 0.83,
             "confidence": "medium", "status": "pending"},
        ],
    }


@pytest.fixture(scope="module")
def client():
    main.jobs.processor = fake_processor
    return TestClient(main.app)  # no context manager: the lifespan (model loading) does not run


def _wav_bytes(tmp_path):
    path = tmp_path / "tone.wav"
    write_wav(path, [0.2 * np.sin(np.linspace(0, 2000, 32000)).astype(np.float32)])
    return path.read_bytes()


def _wait(client, job_id, status="done"):
    for _ in range(100):
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["status"] in ("done", "error", "cancelled"):
            assert body["status"] == status, body
            return body
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_health_reports_loading_state(client):
    body = client.get("/api/health").json()
    assert body["version"] == main.VERSION and body["status"] in ("loading", "ok")
    assert body["llm_configured"] is False


def test_upload_rejects_non_media(client):
    r = client.post("/api/jobs", files={"file": ("notes.mp4", io.BytesIO(b"definitely not a video"))}, headers=LOCAL)
    assert r.status_code == 415
    assert all(j["filename"] != "notes.mp4" for j in client.get("/api/jobs").json())


def test_upload_validates_options(client, tmp_path, ffmpeg):
    data = _wav_bytes(tmp_path)
    r = client.post("/api/jobs", files={"file": ("a.wav", data)}, data={"language": "english!"}, headers=LOCAL)
    assert r.status_code == 422
    r = client.post("/api/jobs", files={"file": ("a.wav", data)}, data={"num_speakers": "99"}, headers=LOCAL)
    assert r.status_code == 422


def test_cross_site_requests_are_blocked(client, tmp_path):
    r = client.post("/api/jobs", files={"file": ("a.wav", b"x")}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert r.status_code == 200 and "access-control-allow-origin" not in r.headers
    assert r.headers["x-content-type-options"] == "nosniff"


def test_full_job_lifecycle(client, tmp_path, ffmpeg):
    r = client.post("/api/jobs", files={"file": ("standup.wav", _wav_bytes(tmp_path), "audio/wav")},
                    data={"language": "en", "glossary": "Marcus Okafor", "num_speakers": "2", "title": "Standup"},
                    headers=LOCAL)
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["title"] == "Standup" and job["media"]["has_audio"] and job["options"]["num_speakers"] == 2
    body = _wait(client, job["id"])
    result = body["result"]
    assert result["has_media"] and result["title"] == "Standup" and result["stats"]["corrections_pending"] == 2
    assert "SPEECH [00:00] Speaker 1: Marcus migrates post gres on Friday." in result["notes_context"]

    # Playback with HTTP range requests (seeking).
    media = client.get(f"/api/jobs/{job['id']}/media", headers={"Range": "bytes=0-99"})
    assert media.status_code == 206 and len(media.content) == 100

    # Rename the recording and a speaker.
    result = client.patch(f"/api/jobs/{job['id']}", json={"title": "Daily standup", "speakers": {"S1": "Priya"}},
                          headers=LOCAL).json()
    assert result["title"] == "Daily standup" and result["speakers"][0]["name"] == "Priya"
    assert "SPEECH [00:00] Priya:" in result["notes_context"]

    # Accept one suggestion, dismiss the other.
    result = client.post(f"/api/jobs/{job['id']}/corrections/0", json={"action": "accept"}, headers=LOCAL).json()
    assert result["segments"][0]["text"] == "Marcus migrates Postgres on Friday."
    assert [w[2] for w in result["segments"][0]["words"]][2] == " Postgres"
    result = client.post(f"/api/jobs/{job['id']}/corrections/1", json={"action": "dismiss"}, headers=LOCAL).json()
    assert [c["status"] for c in result["corrections"]] == ["accepted", "dismissed"]
    assert result["stats"]["corrections_pending"] == 0 and "POSSIBLE MIS-TRANSCRIPTIONS" not in result["notes_context"]

    # Edit a line by hand: word timings no longer match, so they are dropped.
    result = client.patch(f"/api/jobs/{job['id']}/segments/1", json={"text": "Marcus Okafor agrees.", "speaker": "S1"},
                          headers=LOCAL).json()
    seg = result["segments"][1]
    assert seg["text"] == "Marcus Okafor agrees." and seg["edited"] and seg["words"] is None and seg["speaker"] == "S1"
    assert client.patch(f"/api/jobs/{job['id']}/segments/1", json={"text": "x", "speaker": "S9"},
                        headers=LOCAL).status_code == 422

    # Search finds the edited text, with the timestamp to jump to.
    groups = client.get("/api/search", params={"q": "okafor agr"}).json()
    assert groups[0]["job_id"] == job["id"] and groups[0]["hits"][0]["t"] == 1.0

    # Library listing carries what the UI needs.
    listed = next(j for j in client.get("/api/jobs").json() if j["id"] == job["id"])
    assert listed["title"] == "Daily standup" and listed["has_media"] and listed["stats"]["segments"] == 2

    # Reprocess with new options re-runs on the stored media.
    r = client.post(f"/api/jobs/{job['id']}/reprocess", json={"language": "de", "glossary": "Okafor"}, headers=LOCAL)
    assert r.status_code == 202
    body = _wait(client, job["id"])
    assert body["options"]["language"] == "de" and body["result"]["language"] == "de"
    assert client.post(f"/api/jobs/{job['id']}/cancel", headers=LOCAL).status_code == 409

    # Path traversal and bad ids are rejected.
    assert client.get(f"/api/jobs/{job['id']}/frames/..%2Fjob.json").status_code == 404
    assert client.get("/api/jobs/not-a-job").status_code == 404

    # Delete removes the job and its search rows.
    assert client.delete(f"/api/jobs/{job['id']}", headers=LOCAL).status_code == 200
    assert client.get(f"/api/jobs/{job['id']}").status_code == 404
    assert client.get("/api/search", params={"q": "okafor"}).json() == []


def test_cancel_queued_job(client, tmp_path, ffmpeg):
    gate = {"open": False}

    def slow_processor(job, src, report):
        while not gate["open"]:
            report("Working", 0.1)  # raises JobCancelled once cancel() is requested
            time.sleep(0.01)
        return fake_processor(job, src, report)

    main.jobs.processor = slow_processor
    try:
        first = client.post("/api/jobs", files={"file": ("one.wav", _wav_bytes(tmp_path))}, headers=LOCAL).json()
        second = client.post("/api/jobs", files={"file": ("two.wav", _wav_bytes(tmp_path))}, headers=LOCAL).json()
        assert client.post(f"/api/jobs/{second['id']}/cancel", headers=LOCAL).json()["status"] == "cancelled"
        assert client.post(f"/api/jobs/{first['id']}/cancel", headers=LOCAL).status_code == 200
        _wait(client, first["id"], status="cancelled")
        assert client.get(f"/api/jobs/{second['id']}").json()["status"] == "cancelled"
    finally:
        gate["open"] = True
        main.jobs.processor = fake_processor


def test_chat_requires_a_key(client):
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}], "context": "x"}, headers=LOCAL)
    assert r.status_code == 503 and "OPENROUTER_API_KEY" in r.json()["detail"]


def test_chat_context_is_built_from_jobs():
    req = main.ChatRequest(messages=[{"role": "user", "content": "hi"}], job_ids=["0123456789ab"], context="")
    with pytest.raises(main.HTTPException) as exc:
        main._chat_context(req)
    assert exc.value.status_code == 400
