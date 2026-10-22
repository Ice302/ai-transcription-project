from app.search import HIT_END, HIT_START, SearchIndex, fts_query

RESULT = {
    "title": "Weekly sync", "filename": "sync.mp4",
    "speakers": [{"id": "S1", "name": "Priya"}],
    "segments": [{"id": 0, "start": 12.5, "text": "We migrate the Postgres cluster on Friday.", "speaker": "S1"},
                 {"id": 1, "start": 30.0, "text": "Costs dropped after tuning.", "speaker": None}],
    "keyframes": [{"id": 0, "t": 0.0, "ocr_text": "Kubernetes Migration\nOwner: Priya Raghunathan", "duplicate_of": None},
                  {"id": 1, "t": 60.0, "ocr_text": "Kubernetes Migration\nOwner: Priya Raghunathan", "duplicate_of": 0}],
}


def test_fts_query_is_sanitized():
    assert fts_query('postgres "cluster') == '"postgres" "cluster"*'
    assert fts_query("  ;; ") is None
    assert fts_query("DROP TABLE hits; --") == '"drop" "table" "hits"*'


def test_index_search_and_remove(tmp_path):
    index = SearchIndex(tmp_path / "index.db")
    index.index("job1", RESULT)
    hits = index.search("postgres")
    assert len(hits) == 1
    hit = hits[0]
    assert (hit["job_id"], hit["kind"], hit["ref"], hit["t"], hit["speaker"]) == ("job1", "speech", 0, 12.5, "Priya")
    assert f"{HIT_START}Postgres{HIT_END}" in hit["snippet"]

    screen = index.search("raghunath")  # prefix match on the last word
    assert [(h["kind"], h["ref"]) for h in screen] == [("screen", 0)]  # duplicate keyframes are not indexed twice
    assert index.search("weekly")[0]["kind"] == "title"
    assert index.indexed_ids() == {"job1"}

    index.index("job1", {**RESULT, "segments": []})  # reindex replaces rows
    assert index.search("postgres") == []
    index.remove("job1")
    assert index.search("kubernetes") == [] and index.indexed_ids() == set()
    index.close()
