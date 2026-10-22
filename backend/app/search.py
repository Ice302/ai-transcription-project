"""Full-text search across every transcript and every slide (SQLite FTS5, no extra deps).

Each speech segment, each keyframe's on-screen text and each recording's title is one
row, with the timestamp needed to jump straight to the hit.
"""
from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path

HIT_START, HIT_END = "\u0001", "\u0002"  # snippet markers; the UI highlights between them (no HTML)


def fts_query(text: str) -> str | None:
    """Turn free text into a safe FTS5 query: every word must match, the last one as a prefix."""
    tokens = re.findall(r"\w+", text.lower())[:12]
    if not tokens:
        return None
    quoted = [f'"{t}"' for t in tokens]
    quoted[-1] += "*"
    return " ".join(quoted)


class SearchIndex:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._db:
            self._db.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS hits USING fts5("
                "job_id UNINDEXED, kind UNINDEXED, ref UNINDEXED, t UNINDEXED, speaker UNINDEXED, text, "
                "tokenize='unicode61 remove_diacritics 2')"
            )
            self._db.execute("CREATE TABLE IF NOT EXISTS indexed (job_id TEXT PRIMARY KEY, title TEXT)")

    def indexed_ids(self) -> set[str]:
        with self._lock:
            return {row[0] for row in self._db.execute("SELECT job_id FROM indexed")}

    def index(self, job_id: str, result: dict) -> None:
        names = {s["id"]: s.get("name") or s["id"] for s in result.get("speakers", [])}
        rows = [(job_id, "title", None, 0.0, None, f"{result.get('title', '')} {result.get('filename', '')}")]
        rows += [(job_id, "speech", s["id"], s["start"], names.get(s.get("speaker")), s["text"])
                 for s in result.get("segments", []) if s.get("text")]
        rows += [(job_id, "screen", k["id"], k["t"], None, k["ocr_text"])
                 for k in result.get("keyframes", []) if k.get("ocr_text") and k.get("duplicate_of") is None]
        with self._lock, self._db:
            self._db.execute("DELETE FROM hits WHERE job_id = ?", (job_id,))
            self._db.executemany("INSERT INTO hits (job_id, kind, ref, t, speaker, text) VALUES (?,?,?,?,?,?)", rows)
            self._db.execute("INSERT OR REPLACE INTO indexed (job_id, title) VALUES (?, ?)",
                             (job_id, result.get("title", "")))

    def remove(self, job_id: str) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM hits WHERE job_id = ?", (job_id,))
            self._db.execute("DELETE FROM indexed WHERE job_id = ?", (job_id,))

    def search(self, text: str, limit: int = 60) -> list[dict]:
        query = fts_query(text)
        if not query:
            return []
        with self._lock:
            rows = self._db.execute(
                "SELECT job_id, kind, ref, t, speaker, "
                f"snippet(hits, 5, '{HIT_START}', '{HIT_END}', '…', 14) "
                "FROM hits WHERE hits MATCH ? ORDER BY bm25(hits) LIMIT ?",
                (query, limit),
            ).fetchall()
        return [{"job_id": r[0], "kind": r[1], "ref": r[2], "t": r[3], "speaker": r[4], "snippet": r[5]}
                for r in rows]

    def close(self) -> None:
        with self._lock:
            self._db.close()
