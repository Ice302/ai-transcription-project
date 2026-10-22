import threading

import numpy as np

from app import transcriber as transcriber_module
from app.transcriber import (
    Transcriber,
    aggregate_language_votes,
    collapse_repeats,
    merge_punctuation,
    resegment,
    resolve_model,
    speech_windows,
)


def _words(text, start=0.0, step=0.3, prob=0.9):
    out, t = [], start
    for w in text.split():
        out.append((t, t + step - 0.05, " " + w, prob))
        t += step
    return out


def test_splits_on_sentence_end():
    segs = resegment(_words("Hello there. How are you? Fine!"))
    assert [s["text"] for s in segs] == ["Hello there.", "How are you?", "Fine!"]
    assert segs[1]["start"] == 0.6 and [s["id"] for s in segs] == [0, 1, 2]


def test_segments_keep_word_timings_and_probabilities():
    (seg,) = resegment(_words("Hi all.", prob=0.42))
    assert seg["words"] == [[0.0, 0.25, " Hi", 0.42], [0.3, 0.55, " all.", 0.42]]


def test_splits_on_pause():
    words = _words("first part") + _words("second part", start=5.0)
    assert [s["text"] for s in resegment(words)] == ["first part", "second part"]


def test_caps_length():
    segs = resegment(_words(" ".join(["word"] * 100), step=0.1), max_words=40)
    assert [len(s["text"].split()) for s in segs] == [40, 40, 20]


def test_empty():
    assert resegment([]) == []


def test_collapse_repeated_phrase_loops():
    words = _words("Thank you. Thank you. Thank you. Thank you. Bye.")
    assert "".join(w[2] for w in collapse_repeats(words)).strip() == "Thank you. Bye."


def test_collapse_keeps_natural_repetition():
    text = "it was very very very good and no no we did not"
    assert "".join(w[2] for w in collapse_repeats(_words(text))).strip() == text
    assert "".join(w[2] for w in collapse_repeats(_words("the the the the end"))).strip() == "the end"


def test_resolve_model():
    assert resolve_model("small", "cuda") == "small"
    assert resolve_model("auto", "cpu") == "base"
    assert resolve_model("auto", "cpu", live=True) == "base"


def test_punctuation_tokens_join_the_previous_word():
    words = [(0.0, 0.3, " so", 0.9), (0.3, 0.35, ",", 0.4), (0.4, 0.7, " we", 0.9), (0.7, 0.75, " .", 0.5)]
    assert merge_punctuation(words) == [(0.0, 0.35, " so,", 0.9), (0.4, 0.75, " we.", 0.9)]
    assert merge_punctuation([(0.0, 0.1, ",", 0.3), (0.1, 0.4, " hi", 0.9)]) == [(0.1, 0.4, " hi", 0.9)]


def test_sentences_without_words_are_dropped():
    words = [(0.0, 0.2, " ,", 0.3), (0.2, 0.4, " so,", 0.4), (5.0, 5.2, " .", 0.2)]
    assert [s["text"] for s in resegment(words)] == ["so,"]


def test_language_vote_averages_all_windows():
    votes = [[("en", 0.6), ("tl", 0.3)], [("tl", 0.9), ("en", 0.05)], [("tl", 0.8), ("en", 0.1)]]
    assert aggregate_language_votes(votes) == ("tl", 0.667, [("tl", 0.667), ("en", 0.25)])
    assert aggregate_language_votes([]) == (None, 0.0, [])


def test_speech_windows_for_short_and_silent_audio():
    short = np.zeros(16000 * 10, dtype=np.float32)
    ((ratio, window),) = speech_windows(short)
    assert ratio == 1.0 and window.size == short.size
    windows = speech_windows(np.zeros(16000 * 240, dtype=np.float32), count=4)
    assert len(windows) == 1 and windows[0][1].size == 16000 * 30  # nothing scores: one fallback window


class FakeDetector(Transcriber):
    def __init__(self, probs, scores):
        self._lock = threading.Lock()
        self.probs, self.scores = list(probs), scores

    def _language_probs(self, window):
        return self.probs.pop(0)

    def _sample_score(self, sample, language):
        return self.scores[language]


def _two_windows(monkeypatch):
    monkeypatch.setattr(transcriber_module, "speech_windows",
                        lambda audio: [(0.9, np.zeros(4, np.float32)), (0.8, np.zeros(4, np.float32))])


def test_clear_language_vote_is_used_directly(monkeypatch):
    _two_windows(monkeypatch)
    result = FakeDetector([[("en", 0.95), ("tl", 0.03)], [("en", 0.9), ("tl", 0.05)]], {}).detect_language(None)
    assert (result["language"], result["method"], result["windows"]) == ("en", "vote", 2)


def test_mixed_language_vote_is_settled_by_trial_transcription(monkeypatch):
    _two_windows(monkeypatch)
    detector = FakeDetector([[("en", 0.6), ("tl", 0.35)], [("en", 0.5), ("tl", 0.45)]], {"en": 40.0, "tl": 180.0})
    result = detector.detect_language(None)
    assert (result["language"], result["method"], result["probability"]) == ("tl", "trial", 0.4)
    assert result["trial_scores"] == {"en": 40.0, "tl": 180.0}


def test_batch_size_follows_the_gpu(monkeypatch):
    t = Transcriber.__new__(Transcriber)
    t.batch_size_setting, t.device, t.live = 0, "cuda", False
    monkeypatch.setattr(transcriber_module, "gpu_memory_gb", lambda: 6.0)
    assert t.batch_size == 8
    monkeypatch.setattr(transcriber_module, "gpu_memory_gb", lambda: 12.0)
    assert t.batch_size == 16
    t.live = True
    assert t.batch_size == 1  # live windows are short
    t.live, t.device = False, "cpu"
    assert t.batch_size == 1
    t.batch_size_setting = 4
    assert t.batch_size == 4
