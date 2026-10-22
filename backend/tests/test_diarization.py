import numpy as np

from app.diarization import assign_speakers, label_by_embeddings, speaker_at, talk_times

TURNS = [(0.0, 5.8, 1), (6.4, 12.5, 0), (13.1, 19.3, 1)]


def test_speaker_at_prefers_overlap_then_nearest():
    assert speaker_at(1, 2, TURNS) == 1
    assert speaker_at(5.5, 7.0, TURNS) == 0  # 0.6 s overlap with turn 2 beats 0.3 s with turn 1
    assert speaker_at(5.9, 6.1, TURNS) == 1  # in a gap: nearest turn within 1 s
    assert speaker_at(30, 31, TURNS) is None


def _seg(id_, words):
    return {"id": id_, "start": words[0][0], "end": words[-1][1], "text": "".join(w[2] for w in words).strip(),
            "words": words}


def test_assign_speakers_numbers_by_first_appearance():
    segs = [_seg(0, [[0.5, 1.0, " Hi", 0.9], [1.0, 1.4, " all.", 0.9]]),
            _seg(1, [[7.0, 7.5, " Sure.", 0.9]])]
    out, speakers = assign_speakers(segs, TURNS)
    assert [s["speaker"] for s in out] == ["S1", "S2"]
    assert speakers == [{"id": "S1", "name": "Speaker 1"}, {"id": "S2", "name": "Speaker 2"}]


def test_assign_speakers_splits_a_segment_at_a_speaker_change():
    words = [[4.6, 5.0, " Thanks", 0.9], [5.0, 5.5, " everyone.", 0.9], [6.5, 6.9, " Sure,", 0.9],
             [6.9, 7.3, " we", 0.9], [7.3, 7.8, " moved.", 0.9]]
    out, _ = assign_speakers([_seg(0, words)], TURNS)
    assert [(s["id"], s["speaker"], s["text"]) for s in out] == [(0, "S1", "Thanks everyone."),
                                                                  (1, "S2", "Sure, we moved.")]
    assert out[1]["start"] == 6.5 and out[1]["end"] == 7.8


def test_single_word_flicker_is_smoothed():
    # The middle word slightly overlaps the other speaker's turn; it must not become its own segment.
    turns = [(0.0, 2.0, 0), (2.0, 2.3, 1), (2.3, 6.0, 0)]
    words = [[1.5, 1.9, " one", 0.9], [1.95, 2.25, " two", 0.9], [2.3, 2.8, " three", 0.9]]
    out, speakers = assign_speakers([_seg(0, words)], turns)
    assert len(out) == 1 and out[0]["speaker"] == "S1" and len(speakers) == 1


def test_no_turns_leaves_segments_unchanged():
    segs = [_seg(0, [[0, 1, " x", 1.0]])]
    assert assign_speakers(segs, []) == (segs, [])


def test_talk_times():
    segs = [{"start": 0, "end": 2, "speaker": "S1"}, {"start": 3, "end": 4.5, "speaker": "S2"},
            {"start": 5, "end": 6, "speaker": "S1"}, {"start": 7, "end": 8, "speaker": None}]
    assert talk_times(segs) == {"S1": 3.0, "S2": 1.5}


def _unit(*v):
    a = np.array(v, dtype=np.float32)
    return a / np.linalg.norm(a)


def _by_axis(x):  # stand-in for the clustering: the dominant axis is the voice
    return [int(np.argmax(row)) for row in x]


def _sentences(*durations):
    out, t = [], 0.0
    for d in durations:
        out.append({"start": t, "end": t + d, "text": "x"})
        t += d + 0.5
    return out


def test_sentence_voice_prints_become_speakers():
    a, b = _unit(1, 0, 0), _unit(0, 1, 0)
    segs, speakers = label_by_embeddings(_sentences(5, 4, 0.3, 6, 3), {0: a, 1: b, 3: _unit(0.9, 0.1, 0), 4: b},
                                         _by_axis, min_speaker_seconds=1)
    assert [s["speaker"] for s in segs] == ["S1", "S2", "S2", "S1", "S2"]  # the 0.3 s one inherits
    assert speakers == [{"id": "S1", "name": "Speaker 1"}, {"id": "S2", "name": "Speaker 2"}]


def test_short_sentences_join_the_nearest_voice_instead_of_making_one():
    embeddings = {0: _unit(1, 0, 0), 1: _unit(0, 1, 0), 2: _unit(0.3, 0.1, 1.0)}  # 2 is a 1 s "Okay"
    segs, speakers = label_by_embeddings(_sentences(5, 5, 1.0), embeddings, _by_axis, min_speaker_seconds=1)
    assert [s["speaker"] for s in segs] == ["S1", "S2", "S1"] and len(speakers) == 2


def test_voices_with_little_talk_time_merge_unless_the_count_is_fixed():
    durations = [5] * 20 + [3]
    embeddings = {i: _unit(1, 0, 0) if i < 10 else _unit(0, 1, 0) for i in range(20)}
    embeddings[20] = _unit(0.2, 0.6, 0.8)  # a 3 s cluster of its own, closest to the second voice
    segs, speakers = label_by_embeddings(_sentences(*durations), embeddings, _by_axis)
    assert len(speakers) == 2 and segs[20]["speaker"] == "S2"
    segs, speakers = label_by_embeddings(_sentences(*durations), embeddings, _by_axis, fixed_count=True)
    assert len(speakers) == 3 and segs[20]["speaker"] == "S3"


def test_no_voice_prints_means_no_speakers():
    segs, speakers = label_by_embeddings(_sentences(1, 2), {}, _by_axis)
    assert [s["speaker"] for s in segs] == [None, None] and speakers == []


def test_one_voice_in_two_conditions_is_one_speaker():
    a, a_turned = _unit(1, 0, 0), _unit(0.95, 0.3, 0)  # cosine 0.95: same person, other acoustics
    embeddings = {i: a if i < 10 else a_turned for i in range(20)}
    def split(vectors):  # what the clustering returned
        return [0] * 10 + [1] * 10

    _, speakers = label_by_embeddings(_sentences(*[5] * 20), embeddings, split)
    assert len(speakers) == 1
    _, speakers = label_by_embeddings(_sentences(*[5] * 20), embeddings, split, fixed_count=True)
    assert len(speakers) == 2  # a speaker count given by the user is respected
    two_people = {i: a if i < 10 else _unit(0.5, 0, 0.87) for i in range(20)}  # cosine 0.5
    _, speakers = label_by_embeddings(_sentences(*[5] * 20), two_people, split)
    assert len(speakers) == 2


def test_a_short_word_takes_the_speaker_of_the_closer_sentence():
    segs = [{"start": 0.0, "end": 5.0, "text": "a"}, {"start": 5.5, "end": 10.0, "text": "b"},
            {"start": 11.5, "end": 11.8, "text": "Great."}, {"start": 12.0, "end": 17.0, "text": "a again"}]
    embeddings = {0: _unit(1, 0, 0), 1: _unit(0, 1, 0), 3: _unit(1, 0, 0)}
    out, _ = label_by_embeddings(segs, embeddings, _by_axis, min_speaker_seconds=1)
    assert [s["speaker"] for s in out] == ["S1", "S2", "S1", "S1"]  # 0.2 s before "a again", 1.5 s after "b"
