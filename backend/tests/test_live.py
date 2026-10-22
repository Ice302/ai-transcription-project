from collections import Counter

from app.live import MAX_WINDOW, LiveSession, split_stable, strip_overlap


def seg(start, end, text="Done."):
    return {"start": start, "end": end, "text": text}


def test_commits_only_segments_clear_of_the_edge():
    segs = [seg(0, 2), seg(2, 4.5), seg(4.6, 5.8)]
    assert split_stable(segs, window_len=6.0, final=False) == 2


def test_unpunctuated_segment_needs_a_longer_pause():
    assert split_stable([seg(0, 4.0, "Their")], window_len=6.0, final=False) == 0
    assert split_stable([seg(0, 2.5, "Their")], window_len=6.0, final=False) == 1


def test_keeps_everything_pending_when_all_near_edge():
    assert split_stable([seg(0, 5.5)], window_len=6.0, final=False) == 0


def test_final_commits_everything():
    assert split_stable([seg(0, 5.5), seg(5.5, 5.9)], window_len=6.0, final=True) == 2


def test_full_window_forces_progress():
    segs = [seg(0, MAX_WINDOW - 0.2, "no end"), seg(MAX_WINDOW - 0.2, MAX_WINDOW)]
    assert split_stable(segs, window_len=MAX_WINDOW, final=False) == 1
    assert split_stable([seg(0, MAX_WINDOW, "x")], window_len=MAX_WINDOW, final=False) == 1


def test_nothing_to_commit():
    assert split_stable([], window_len=10, final=False) == 0


def test_strip_overlap():
    assert strip_overlap("Then the action", "Action items migrate the cluster.") == "items migrate the cluster."
    assert strip_overlap("We moved forty services", "services so far, and") == "so far, and"
    assert strip_overlap("Hello there.", "Completely new.") == "Completely new."
    assert strip_overlap("", "Fresh start.") == "Fresh start."
    assert strip_overlap("ok", "ok") == "ok"  # never strip everything


def _session(language=None, votes=()):
    session = LiveSession.__new__(LiveSession)
    session.options = {"language": language}
    session.language_votes = Counter(votes)
    return session


def test_live_language_locks_after_a_clear_majority():
    assert _session(votes=["tl", "en", "tl"])._language() is None  # too early to tell
    assert _session(votes=["tl", "en", "tl", "tl"])._language() == "tl"
    assert _session(votes=["tl", "en", "tl", "en"])._language() is None  # no clear majority yet
    assert _session("en", ["tl"] * 5)._language() == "en"  # a chosen language always wins
