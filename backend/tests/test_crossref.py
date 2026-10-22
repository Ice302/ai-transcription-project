from app.crossref import (
    Keyframe,
    Segment,
    apply_correction,
    assign_scenes,
    build_glossary,
    build_notes_context,
    build_scenes,
    compute_stats,
    cross_reference,
    extract_vocabulary,
    chrome_labels,
    chrome_words,
    find_chrome,
    is_chrome,
    find_corrections,
    is_noise_line,
    line_key,
    strip_chrome,
    fmt_ts,
    phonetic_key,
    parse_user_glossary,
)


def test_vocabulary_prefers_distinctive_terms():
    vocab = extract_vocabulary(["Kubernetes Deployment Strategy", "the next slide about Kubernetes and Q3"])
    assert vocab[0] == "Kubernetes"
    assert "Q3" in vocab
    assert "the" not in vocab and "about" not in vocab


def test_vocabulary_rarity_filter_drops_common_words():
    common = {"Owner", "Action", "Items"}
    vocab = extract_vocabulary(["Action Items", "Owner: Priya Raghunathan"], is_common=lambda w: w in common)
    assert vocab == ["Priya", "Raghunathan"]


def test_glossary_dedupes_and_respects_length():
    glossary = build_glossary(["Kubernetes", "kubernetes", "Grafana"] + [f"Term{i}" for i in range(500)], max_chars=60)
    assert glossary.startswith("Kubernetes, Grafana, Term0")
    assert len(glossary) <= 60
    assert build_glossary([]) is None


def test_user_glossary_parsing():
    assert parse_user_glossary("Priya Raghunathan, Okafor\nTerraform;  ") == ["Priya Raghunathan", "Okafor", "Terraform"]


def test_scenes_cover_timeline():
    scenes = build_scenes([Keyframe(id=1, t=10), Keyframe(id=0, t=0)], duration=30)
    assert [(s.t, s.end) for s in scenes] == [(0, 10), (10, 30)]


def test_assign_scenes_uses_max_overlap():
    scenes = build_scenes([Keyframe(id=0, t=0), Keyframe(id=1, t=10)], duration=30)
    segs = [Segment(0, 1, 4, "a"), Segment(1, 8, 15, "b"), Segment(2, 9, 11, "c"), Segment(3, 25, 29, "d")]
    assign_scenes(segs, scenes)
    assert [s.scene_id for s in segs] == [0, 1, 0, 1]


def test_corrections_find_misheard_terms():
    seg = Segment(0, 0, 3, "we deploy on cubernetes with terraformm")
    found = {(c["heard"], c["seen"]) for c in find_corrections(seg, ["Kubernetes", "Terraform"])}
    assert ("cubernetes", "Kubernetes") in found
    assert ("terraformm", "Terraform") in found


def test_corrections_match_split_words():
    seg = Segment(0, 0, 3, "post gres is our database")
    found = {(c["heard"], c["seen"]) for c in find_corrections(seg, ["Postgres"])}
    assert ("post gres", "Postgres") in found


def test_corrections_ignore_neighbour_word_pairs_and_inflections():
    seg = Segment(0, 0, 3, "we review our Kubernetes Migration and the clusters")
    assert find_corrections(seg, ["Kubernetes", "Migration", "Cluster"]) == []


def test_corrections_ignore_exact_matches():
    assert find_corrections(Segment(0, 0, 3, "Kubernetes rocks"), ["Kubernetes"]) == []


def test_correction_confidence_uses_word_probability():
    words = [[0, 0.5, " we", 0.99], [0.5, 1.2, " deploy", 0.98], [1.2, 2.0, " cuber", 0.31], [2.0, 2.6, " netties", 0.4]]
    seg = Segment(0, 0, 3, "we deploy cuber netties", words=words)
    (corr,) = find_corrections(seg, ["Kubernetes"])
    assert corr["heard"] == "cuber netties" and corr["probability"] == 0.31 and corr["confidence"] == "high"


def test_unsure_words_get_a_lower_similarity_bar():
    words = [[0, 0.4, " the", 0.99], [0.4, 1.2, " Cubarnet's", 0.31], [1.2, 1.8, " migration", 0.95]]
    seg = Segment(0, 0, 2, "the Cubarnet's migration", words=words)
    (corr,) = find_corrections(seg, ["Kubernetes"])
    assert (corr["heard"], corr["seen"], corr["confidence"]) == ("Cubarnet's", "Kubernetes", "high")
    confident = Segment(0, 0, 2, "the Cubarnet's migration", words=[[0, 0.4, " the", 0.99], [0.4, 1.2, " Cubarnet's", 0.97]])
    assert find_corrections(confident, ["Kubernetes"]) == []


def test_phonetic_key():
    assert phonetic_key("QBARnet's") == phonetic_key("Cubarnet's") == phonetic_key("Kubernetes") == "kbrnts"
    assert phonetic_key("post gres") == phonetic_key("Postgres")
    assert phonetic_key("Terraformm") == phonetic_key("Terraform")


def test_unsure_word_that_sounds_like_a_screen_term_is_flagged():
    words = [[0, 0.4, " the", 0.99], [0.4, 1.2, " QBARnet's", 0.22], [1.2, 1.8, " migration", 0.95]]
    seg = Segment(0, 0, 2, "the QBARnet's migration", words=words)
    (corr,) = find_corrections(seg, ["Kubernetes"])
    assert (corr["heard"], corr["seen"], corr["confidence"]) == ("QBARnet's", "Kubernetes", "high")
    # The same spelling heard confidently is left alone, and sound alone never matches common words.
    sure = Segment(0, 0, 2, "the QBARnet's migration", words=[[0.4, 1.2, " QBARnet's", 0.95]])
    assert find_corrections(sure, ["Kubernetes"]) == []
    cost = Segment(0, 0, 2, "the cast", words=[[0, 0.5, " the", 0.9], [0.5, 1, " cast", 0.2]])
    assert find_corrections(cost, ["Costs"]) == []


def test_abbreviations_count_as_spoken():
    frames = [Keyframe(id=0, t=0, ocr_text="Migrate cluster (Fri)\nReview (Tue)")]
    segs = [Segment(0, 1, 5, "We migrate by Friday and review on Tuesday.")]
    scene = cross_reference(segs, frames, duration=10)["scenes"][0]
    assert "Fri" in scene.terms_confirmed and "Tue" in scene.terms_confirmed


def test_apply_correction_updates_text_and_words():
    seg = {"text": "we use post gres, mostly.", "words": [[0, 0.3, " we", 0.9], [0.3, 0.6, " use", 0.9],
                                                         [0.6, 0.9, " post", 0.4], [0.9, 1.2, " gres,", 0.5],
                                                         [1.2, 1.6, " mostly.", 0.9]]}
    assert apply_correction(seg, "post gres", "Postgres")
    assert seg["text"] == "we use Postgres, mostly."
    assert [w[2] for w in seg["words"]] == [" we", " use", " Postgres,", " mostly."]
    assert seg["words"][2][:2] == [0.6, 1.2] and seg["words"][2][3] == 1.0
    assert not apply_correction(seg, "nothing here", "X")


def test_apply_correction_is_literal():
    seg = {"text": "open the folder", "words": None}
    assert apply_correction(seg, "folder", r"C:\new\1")
    assert seg["text"] == r"open the C:\new\1"


def test_cross_reference_confirmed_and_unspoken():
    frames = [Keyframe(id=0, t=0, ocr_text="Kubernetes Rollout\nCanary Deployments\nPrometheus Alerts")]
    segs = [Segment(0, 1, 5, "Today we cover the Kubernetes rollout with canary deployments.")]
    out = cross_reference(segs, frames, duration=10)
    scene = out["scenes"][0]
    assert "Kubernetes" in scene.terms_confirmed
    assert "Prometheus" in scene.terms_unspoken
    assert segs[0].scene_id == 0


def test_cross_reference_numbers_corrections_and_uses_user_terms():
    segs = [Segment(0, 0, 3, "Okafer will migrate the cluster")]
    out = cross_reference(segs, [], duration=3, extra_terms=["Marcus Okafor"])
    assert [(c["id"], c["heard"], c["seen"], c["status"]) for c in out["corrections"]] == [(0, "Okafer", "Okafor", "pending")]


def _result(**extra):
    base = {
        "filename": "talk.mp4", "title": "Weekly sync", "media": {"duration": 70},
        "speakers": [{"id": "S1", "name": "Priya"}],
        "segments": [{"id": 0, "start": 2, "end": 5, "text": "revenue was about four million", "scene_id": 0,
                      "speaker": "S1", "words": [[2, 3, " revenue", 0.9], [3, 5, " million", 0.3]]}],
        "keyframes": [{"id": 0, "t": 0, "end": 70, "title": "Q3 Revenue", "ocr_text": "Q3 Revenue\n$4.2M",
                       "terms_unspoken": ["Q3"]}],
        "corrections": [{"id": 0, "t": 2, "heard": "for", "seen": "Four", "status": "dismissed"},
                        {"id": 1, "t": 3, "heard": "milion", "seen": "Million", "status": "pending"}],
    }
    base.update(extra)
    return base


def test_notes_context_contains_both_sources_and_speakers():
    ctx = build_notes_context(_result())
    assert ctx.startswith("=== FILE: talk.mp4 | TITLE: Weekly sync | DURATION: 01:10 ===")
    assert "SPEAKERS: S1 = Priya" in ctx
    assert "[SCENE 1 | 00:00–01:10] Q3 Revenue" in ctx
    assert "SCREEN: Q3 Revenue · $4.2M" in ctx
    assert "SPEECH [00:02] Priya: revenue was about four million" in ctx
    assert '"milion" -> "Million"' in ctx and '"for"' not in ctx  # dismissed suggestions are dropped


def test_audio_only_context():
    ctx = build_notes_context({"filename": "a.mp3", "segments": [{"id": 0, "start": 65, "end": 70, "text": "hello"}]})
    assert "SPEECH [01:05] hello" in ctx


def test_stats():
    stats = compute_stats(_result())
    assert stats == {"segments": 1, "words": 2, "scenes": 1, "speakers": 1, "low_confidence_words": 1,
                     "corrections_pending": 1}


def test_fmt_ts():
    assert fmt_ts(5) == "00:05" and fmt_ts(3725) == "1:02:05"


def test_interface_text_on_most_screens_is_chrome():
    frames = [["Mute", "Share Screen", "Quadratic Equations"], ["Mute", "Share Screen", "Roots"],
              ["Mute", "Share Screen", "Discriminant"], ["Mute", "Vertex form"]]
    assert find_chrome(frames) == {"mute", "share screen"}


def test_a_slide_that_stays_up_is_not_chrome():
    frames = [["Agenda", "Intro"]] * 10 + [["REC", "Topic A"], ["REC", "Topic B"], ["REC", "Topic C"]]
    assert find_chrome(frames) == {"rec"}
    assert find_chrome([["Mute"], ["Mute", "Hi"]]) == set()  # too few distinct screens to tell


def test_strip_chrome_and_noise_lines():
    assert strip_chrome("Mute\nKey idea\nS\n\n2x + 1 = 0", {"mute"}) == "Key idea\n2x + 1 = 0"
    assert is_noise_line("S") and is_noise_line("× 2") and not is_noise_line("Sum")


def test_notes_context_groups_sentences_and_marks_repeated_slides():
    result = {
        "filename": "class.mkv", "speakers": [{"id": "S1", "name": "Teacher"}, {"id": "S2", "name": "Student"}],
        "keyframes": [{"id": 0, "t": 0, "end": 100, "title": "Roots", "ocr_text": "Roots", "terms_unspoken": ["Vieta"]},
                      {"id": 1, "t": 100, "end": 200, "title": "Roots", "ocr_text": "Roots", "duplicate_of": 0,
                       "terms_unspoken": ["Vieta"]}],
        "segments": [{"id": 0, "start": 1, "end": 3, "text": "Okay class.", "speaker": "S1", "scene_id": 0},
                     {"id": 1, "start": 3, "end": 6, "text": "Today we solve for x.", "speaker": "S1", "scene_id": 0},
                     {"id": 2, "start": 7, "end": 8, "text": "Ma'am, question po.", "speaker": "S2", "scene_id": 0},
                     {"id": 3, "start": 90, "end": 95, "text": "Next one.", "speaker": "S2", "scene_id": 0},
                     {"id": 4, "start": 120, "end": 125, "text": "Back to roots.", "speaker": "S1", "scene_id": 1}],
    }
    ctx = build_notes_context(result)
    assert "SPEECH [00:01] Teacher: Okay class. Today we solve for x." in ctx
    assert "SPEECH [00:07] Student: Ma'am, question po." in ctx
    assert "SPEECH [01:30] Student: Next one." in ctx  # a fresh timestamp after a minute
    assert "SCREEN: same slide as scene 1" in ctx and ctx.count("ON SCREEN BUT NOT SPOKEN") == 1


def test_chrome_ignores_punctuation_and_catches_merged_labels():
    frames = [["03_Armenteros, Vinz Syril.", "Rainier Lawrence Valdez", f"Slide {i}"] for i in range(4)]
    frames[1][0] = "03_Armenteros, Vinz Syril"  # OCR dropped the period on one frame
    chrome = find_chrome(frames)
    assert chrome == {"03 armenteros vinz syril", "rainier lawrence valdez"}
    assert is_chrome("03_Armenteros, Vinz SyrilRainier Lawrence Valdez", chrome)  # two labels read as one line
    assert not is_chrome("Vinz explains the quadratic formula", chrome)
    merged = find_chrome([["Santino Edralin Shaun Balgua", f"Slide {i}"] for i in range(4)])
    assert is_chrome("Santino Edralin", merged) and is_chrome("Shaun Balgua", merged)  # read apart this time
    assert not is_chrome("Santino", merged)  # one word alone could be content
    assert chrome_labels(frames, chrome) == ["03_Armenteros, Vinz Syril.", "Rainier Lawrence Valdez"]


def _sure(text, prob=0.99):
    return Segment(0, 0, 3, text, words=[[0, 0.3, " " + w, prob] for w in text.split()])


def test_corrections_ignore_word_forms_hyphenation_and_word_starts():
    assert find_corrections(_sure("the inequality holds"), ["INEQUALITIES"]) == []
    assert find_corrections(_sure("the inequality is strict"), ["INEQUALITIES"]) == []
    assert find_corrections(_sure("add the fractions"), ["Fractional"]) == []
    assert find_corrections(_sure("a left open interval"), ["Left-Open"]) == []
    assert find_corrections(_sure("the number line"), ["LINEAR"]) == []
    assert find_corrections(_sure("so it is negative"), ["iThis"]) == []
    # an unsure word that only starts the screen term is still worth a look
    (corr,) = find_corrections(_sure("the number line", prob=0.3), ["LINEAR"])
    assert corr["heard"] == "line"


def test_real_mishearings_survive_the_new_rules():
    (corr,) = find_corrections(_sure("an undounded interval", prob=0.63), ["Unbounded"])
    assert (corr["heard"], corr["seen"]) == ("undounded", "Unbounded")
    (corr,) = find_corrections(_sure("post gres is our database"), ["Postgres"])
    assert corr["heard"] == "post gres"


def test_variants_of_a_recurring_label_count_together():
    banner = ["This meeting is being transcribed.", "iThis meeting is being transcribed."]
    frames = [[banner[i % 2], f"Slide {i}"] if i < 6 else [f"Slide {i}"] for i in range(12)]
    chrome = find_chrome(frames)  # each spelling is on 3 of 12 screens, together on 6
    assert chrome == {"this meeting is being transcribed", "ithis meeting is being transcribed"}
    assert is_chrome("[This meeting is being transcribed", chrome)
    assert not is_chrome("Chart", {"chat"})  # short labels are only matched exactly


def test_interface_words_stay_out_of_the_vocabulary():
    exclude = chrome_words({"santino emmanuel edralin", "magpantay"})
    assert exclude == {"santino", "emmanuel", "edralin", "magpantay"}
    texts = ["Santino Emanuel Eralin", "Magpant", "Quadratic Discriminant"]
    assert extract_vocabulary(texts, exclude=exclude) == ["Quadratic", "Discriminant"]


def test_contractions_and_icon_letters_are_not_terms():
    texts = ["Don't share yet", "iThis meeting is live", "Priya's iPhone demo", "We\u2019ll see"]
    assert extract_vocabulary(texts) == ["Priya", "iPhone"]


def test_variants_of_a_label_are_listed_once():
    frames = [["Santino Emmanuel Edralin Shaun Brent Balgua"]] * 3 + [["Santino Emmanuel Edr..Shaun Brent Balgua"]]
    chrome = {line_key(f[0]) for f in frames}
    assert chrome_labels(frames, chrome) == ["Santino Emmanuel Edralin Shaun Brent Balgua"]
