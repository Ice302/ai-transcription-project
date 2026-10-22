"""Cross-reference speech (Whisper segments) with visuals (keyframe OCR / captions).

Everything here is pure Python so it can be unit-tested without models or ffmpeg.

The core idea:
  * Each keyframe is "on screen" from its timestamp until the next keyframe -> a *scene*.
  * Every speech segment is assigned to the scene it overlaps most.
  * Words on screen are spelled correctly but carry no narrative; speech carries the
    narrative but mangles names and jargon. Comparing them per scene yields
    - confirmed terms   (on screen AND spoken)        -> high-confidence facts
    - unspoken terms    (on screen, never said)       -> content the notes would miss
    - corrections       (spoken word ~ on-screen term) -> likely mis-transcriptions
  * The on-screen vocabulary is also given to Whisper as a glossary before
    transcription, which biases decoding toward the correct spellings.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Callable

STOPWORDS = frozenset(
    """a about above after again against all also am an and any are as at be because been before being
    below between both but by can could did do does doing down during each few for from further had has
    have having he her here hers him his how i if in into is it its itself just let me more most my no nor
    not now of off on once only or other our ours out over own same she should so some such than that the
    their theirs them then there these they this those through to too under until up very was we were what
    when where which while who whom why will with would you your yours yes okay ok like get got go going
    one two three new use used using via per vs etc www com http https page slide next back click""".split()
)

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'+#.\-]*[A-Za-z0-9+#]|[A-Za-z]")
_SUFFIXES = ("s", "es", "ed", "ing", "er", "ly", "'s")
FUZZY_MIN_CHARS = 12  # interface lines shorter than this are only matched exactly

IsCommon = Callable[[str], bool]


@dataclass
class Segment:
    id: int
    start: float
    end: float
    text: str
    scene_id: int | None = None
    speaker: str | None = None
    words: list | None = None


@dataclass
class Keyframe:
    id: int
    t: float
    image: str = ""
    ocr_text: str = ""
    caption: str = ""
    end: float = 0.0
    title: str = ""
    duplicate_of: int | None = None
    spoken_text: str = ""
    terms_confirmed: list[str] = field(default_factory=list)
    terms_unspoken: list[str] = field(default_factory=list)


def tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text.replace("\u2019", "'"))  # OCR often reads ' as a curly quote


def norm(word: str) -> str:
    return re.sub(r"[^a-z0-9+#]", "", word.lower())


def _is_distinctive(word: str) -> bool:
    """Heuristic for "worth biasing Whisper towards": names, acronyms, jargon, numbers."""
    n = norm(word)
    if len(n) < 2 or n in STOPWORDS or "'" in word:  # contractions are never terms: "Don't", "We'll"
        return False
    if word[0].islower() and word[1:2].isupper() and word[1:].lower() in STOPWORDS:
        return False  # an icon read as a letter: "iThis" (but "iPhone" stays)
    if len(n) == 2:  # only short acronyms / codes: "AI", "Q3", "UX"
        return word.isupper() or (any(c.isdigit() for c in n) and any(c.isalpha() for c in n))
    return (
        word[0].isupper()
        or any(c.isdigit() for c in word)
        or any(c.isupper() for c in word[1:])  # camelCase / acronyms
        or len(n) >= 8
    )


def extract_vocabulary(texts: list[str], limit: int = 40, is_common: IsCommon | None = None,
                       exclude: set[str] | None = None) -> list[str]:
    """Most frequent distinctive terms across OCR texts, original casing preserved.

    ``is_common`` (from the speech model's tokenizer) drops ordinary words such as
    "Owner" or "Action" that are only capitalized because they start a line: Whisper
    spells those correctly anyway, and they made the "not spoken" lists noisy.
    ``exclude`` holds words of the interface text (see ``chrome_words``); OCR variants
    of them ("Emanuel" for "Emmanuel") are dropped too.
    """
    counts: Counter[str] = Counter()
    spelling: dict[str, str] = {}
    for text in texts:
        for word in tokenize(text):
            word = word.strip(".-'")
            if word.lower().endswith("'s"):
                word = word[:-2]  # "Priya's" -> "Priya"
            if _is_distinctive(word) and not (is_common and is_common(word)) and \
                    not (exclude and _near_any(norm(word), exclude)):
                key = norm(word)
                counts[key] += 1
                spelling.setdefault(key, word)
    return [spelling[k] for k, _ in counts.most_common(limit)]


def build_glossary(terms: list[str], max_chars: int = 500) -> str | None:
    """Comma-separated hint list for Whisper (its prompt window is ~224 tokens)."""
    out, size, seen = [], 0, set()
    for term in terms:
        term = term.strip()
        key = norm(term)
        if not term or key in seen:
            continue
        if size + len(term) + 2 > max_chars:
            break
        seen.add(key)
        out.append(term)
        size += len(term) + 2
    return ", ".join(out) or None


def parse_user_glossary(text: str | None) -> list[str]:
    """User-supplied terms: one per line or comma-separated; multi-word names allowed."""
    return [t.strip() for t in re.split(r"[,\n;]", text or "") if t.strip()][:200]


def line_key(line: str) -> str:
    """Comparable form of an OCR line: case, punctuation and spacing are ignored, so
    "03_Armenteros, Vinz Syril." and "03_Armenteros, Vinz Syril" are one label."""
    return re.sub(r"[\W_]+", " ", line.lower()).strip()


def is_noise_line(line: str) -> bool:
    """Lines too short to be content: avatar initials, icons, stray digits ("S", "×", "2")."""
    return sum(c.isalnum() for c in line) < 3


def find_chrome(frames: list[list[str]], min_share: float = 0.3, min_count: int = 3) -> set[str]:
    """Interface text that is on screen all the time (video-call chrome, app toolbars).

    In a screen-recorded Zoom class, "Meeting", "Video", "Share", "REC" and the
    participants' names were on 60-80% of all frames and buried the slide content.
    A line counts as chrome when it appears on at least ``min_share`` of the
    *distinct* screens (frames with identical text count once, so a slide that
    simply stays up for a long time is not mistaken for chrome).
    """
    screens = {frozenset(key for key in map(line_key, lines) if key) for lines in frames}
    screens.discard(frozenset())
    if len(screens) < min_count:
        return set()
    where: dict[str, set[int]] = {}
    for n, screen in enumerate(screens):
        for key in screen:
            where.setdefault(key, set()).add(n)
    threshold = max(min_count, min_share * len(screens))
    chrome = {key for key, seen in where.items() if len(seen) >= threshold}
    # OCR reads a label slightly differently from frame to frame ("This meeting is being
    # transcribed" / "iThis meeting is being transcribed"); recurring variants count together.
    groups: list[tuple[str, set[int], list[str]]] = []
    for key in sorted((k for k, seen in where.items() if len(seen) >= 2), key=lambda k: (-len(where[k]), k)):
        for rep, seen, members in groups:
            if _similar_keys(key, rep):
                seen |= where[key]
                members.append(key)
                break
        else:
            groups.append((key, set(where[key]), [key]))
    for _, seen, members in groups:
        if len(seen) >= threshold:
            chrome.update(members)
    return chrome


def _similar_keys(a: str, b: str, threshold: float = 0.85) -> bool:
    """Near-identical long lines (short ones like "Chat" / "Chart" are never fuzzy-matched)."""
    if min(len(a), len(b)) < FUZZY_MIN_CHARS or abs(len(a) - len(b)) > 0.3 * max(len(a), len(b)):
        return False
    matcher = SequenceMatcher(None, a, b)
    return matcher.real_quick_ratio() >= threshold and matcher.quick_ratio() >= threshold and \
        matcher.ratio() >= threshold


def _near_any(word: str, words: set[str]) -> bool:
    if word in words:
        return True
    return len(word) >= 5 and any(len(w) >= 5 and abs(len(w) - len(word)) <= 2 and similarity(word, w) >= 0.85
                                  for w in words)


def chrome_words(chrome: set[str]) -> set[str]:
    """The words of the interface text, to keep names and buttons out of the vocabulary."""
    return {w for key in chrome for w in (norm(x) for x in key.split()) if len(w) >= 3}


def is_chrome(line: str, chrome: set[str]) -> bool:
    """A chrome line, a run of 2+ words of one, or neighbouring chrome labels that OCR
    read as one line ("03_Armenteros, Vinz SyrilRainier Lawrence Valdez" = two names)."""
    key = line_key(line)
    if not key or key in chrome:
        return bool(key)
    if " " in key and any(f" {key} " in f" {k} " for k in chrome):
        return True  # part of a label OCR usually reads merged ("Santino Emmanuel Edralin")
    if len(key) >= FUZZY_MIN_CHARS and any(_similar_keys(key, k) for k in chrome):
        return True  # the same label, read a little differently ("03_Armenteros, Vinz S..")
    joined = key.replace(" ", "")
    pieces = {p for p in (k.replace(" ", "") for k in chrome) if len(p) >= 3}
    if not any(joined.startswith(p) for p in pieces):
        return False  # most lines: no need for the word-break search below
    ends = [True] + [False] * len(joined)  # ends[i]: joined[:i] is made of chrome pieces
    for i in range(1, len(joined) + 1):
        ends[i] = any(len(p) <= i and ends[i - len(p)] and joined.startswith(p, i - len(p)) for p in pieces)
    return ends[-1]


def chrome_labels(frames: list[list[str]], chrome: set[str], limit: int = 40) -> list[str]:
    """Readable spellings of the interface text that was left out (shown in the UI).
    OCR variants of one label are listed once, in their most frequent spelling."""
    counts: Counter[str] = Counter()
    spelling: dict[str, str] = {}
    for lines in frames:
        for line in lines:
            key = line_key(line)
            if key in chrome and not is_noise_line(line):
                counts[key] += 1
                spelling.setdefault(key, line.strip())
    shown: list[str] = []
    for key, _ in counts.most_common():
        if not any(_similar_keys(key, other) for other in shown):
            shown.append(key)
    return sorted((spelling[k] for k in shown), key=str.lower)[:limit]


def strip_chrome(text: str, chrome: set[str]) -> str:
    return "\n".join(line for line in text.splitlines()
                     if line.strip() and not is_noise_line(line) and not is_chrome(line, chrome))


def build_scenes(keyframes: list[Keyframe], duration: float) -> list[Keyframe]:
    keyframes = sorted(keyframes, key=lambda k: k.t)
    for i, kf in enumerate(keyframes):
        kf.end = keyframes[i + 1].t if i + 1 < len(keyframes) else max(duration, kf.t)
    return keyframes


def assign_scenes(segments: list[Segment], scenes: list[Keyframe]) -> None:
    """Attach each segment to the scene it overlaps the most (two-pointer sweep, O(n+m))."""
    if not scenes:
        return
    j = 0
    for seg in segments:
        while j + 1 < len(scenes) and scenes[j].end <= seg.start:
            j += 1
        best, best_overlap = scenes[j].id, -1.0
        k = j
        while k < len(scenes) and scenes[k].t < max(seg.end, seg.start + 1e-6):
            overlap = min(seg.end, scenes[k].end) - max(seg.start, scenes[k].t)
            if overlap > best_overlap:
                best, best_overlap = scenes[k].id, overlap
            k += 1
        seg.scene_id = best


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def phonetic_key(word: str) -> str:
    """Consonant skeleton of a word, so mis-hearings that sound alike compare equal.

    "QBARnet's", "Cubarnet's" and "Kubernetes" all become "kbrnts"; "post gres" and
    "Postgres" become "pstkrs". Deliberately crude (no dictionary, any language
    written in Latin script): it is only used as extra evidence for words the
    speech model itself was unsure about.
    """
    w = norm(word)
    for pattern, repl in ((r"ph", "f"), (r"ck", "k"), (r"q", "k"), (r"x", "ks"), (r"c(?=[eiy])", "s"),
                          (r"c", "k"), (r"g", "k"), (r"z", "s"), (r"d", "t"), (r"v", "f"), (r"[hwy]", ""),
                          (r"[aeiou]", ""), (r"[^a-z]", ""), (r"(.)\1+", r"\1")):
        w = re.sub(pattern, repl, w)
    return w


_STEMS = (("ies", "y"), ("ied", "y"), ("ally", ""), ("ing", ""), ("ed", ""), ("es", ""), ("al", ""),
          ("ly", ""), ("er", ""), ("s", ""))


def _stem(word: str) -> str:
    for suffix, repl in _STEMS:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)] + repl
    return word


def _inflection_of(a: str, b: str) -> bool:
    """True for forms of one word ("cluster"/"clusters", "inequality"/"INEQUALITIES",
    "fractions"/"Fractional"): different words, not mis-hearings."""
    short, long_ = sorted((a, b), key=len)
    return (long_.startswith(short) and long_[len(short):] in _SUFFIXES) or _stem(a) == _stem(b)


def _same_words(heard: str, term: str) -> bool:
    """"left open" vs "Left-Open": the same words, only joined differently."""
    def parts(text: str) -> list[str]:
        return [p for p in (norm(x) for x in re.split(r"[\s\-_/]+", text)) if p]
    return parts(heard) == parts(term)


def _word_run(words: list, target: str) -> tuple[int, int] | None:
    """Indices (i, j) of consecutive Whisper words whose letters spell ``target`` (normalized)."""
    norms = [norm(w[2]) for w in words]
    for i in range(len(words)):
        if not norms[i]:
            continue
        acc = ""
        for j in range(i, min(i + 5, len(words))):
            acc += norms[j]
            if acc == target:
                return i, j
            if len(acc) >= len(target):
                break
    return None


def _heard_probability(words: list | None, heard: str) -> float | None:
    """Lowest Whisper word probability among the words that make up ``heard``."""
    run = _word_run(words or [], norm(heard))
    if run is None:
        return None
    return min(float(w[3]) for w in words[run[0]:run[1] + 1] if len(w) > 3)


def find_corrections(segment: Segment, screen_terms: list[str], min_ratio: float = 0.8,
                     unsure_ratio: float = 0.7) -> list[dict]:
    """Spoken words that look like a mis-hearing of a term visible on screen.

    Single words ("cubernetes" -> "Kubernetes") and adjacent pairs ("post gres" ->
    "Postgres") are considered. A pair only counts if it matches better than either
    of its words alone, so "our Kubernetes" is not reported against "Kubernetes".
    Plural/tense variants are ignored. Words Whisper itself was unsure of (word
    probability < 0.5) need less evidence: ``unsure_ratio`` spelling similarity
    ("Cubarnet's" is 74% like "Kubernetes"), or a near-identical sound
    ("QBARnet's" is only 67% alike in spelling but sounds the same). Confidence is
    "high" when the strings are very close or Whisper was unsure.
    """
    terms = [(t, norm(t)) for t in screen_terms if len(norm(t)) >= 5]
    if not terms:
        return []
    tokens = tokenize(segment.text)
    norms = [norm(w) for w in tokens]
    suggestions: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def plausible(nc: str, nt: str) -> float:
        if len(nc) < 4 or nc in STOPWORDS or abs(len(nc) - len(nt)) > max(2, len(nt) // 3):
            return 0.0  # cheap length filter before the O(n*m) similarity
        if _inflection_of(nc, nt):
            return 0.0
        return similarity(nc, nt)

    def accept(heard: str, term: str, ratio: float) -> bool:
        if _same_words(heard, term):
            return False
        prob = _heard_probability(segment.words, heard)
        nh, nt = norm(heard), norm(term)
        if prob is not None and prob >= 0.9 and nh != nt and nt.startswith(nh):
            return False  # a clearly heard word that only starts the screen word: "line" vs "LINEAR"
        if ratio >= min_ratio:
            return True
        if prob is None or prob >= 0.5:
            return False
        if ratio >= unsure_ratio:
            return True
        key_heard, key_term = phonetic_key(heard), phonetic_key(term)
        return len(key_term) >= 4 and similarity(key_heard, key_term) >= 0.9

    def add(heard: str, term: str, ratio: float):
        if (heard.lower(), term) in seen or not accept(heard, term, ratio):
            return
        seen.add((heard.lower(), term))
        prob = _heard_probability(segment.words, heard)
        confident = ratio >= 0.9 or (prob is not None and prob < 0.6)
        suggestions.append({"segment_id": segment.id, "t": segment.start, "heard": heard, "seen": term,
                            "similarity": round(ratio, 2), "probability": prob,
                            "confidence": "high" if confident else "medium"})

    for term, nt in terms:
        for i, nc in enumerate(norms):
            if nc != nt:
                ratio = plausible(nc, nt)
                if ratio >= 0.55:  # accept() decides, using word confidence and sound
                    add(tokens[i], term, ratio)
            if i + 1 < len(norms):
                if nt in (nc, norms[i + 1]) or (nc in STOPWORDS and norms[i + 1] in STOPWORDS):
                    continue  # "it is" is never a mis-hearing of "iThis" (OCR noise)
                if _inflection_of(nc, nt) or _inflection_of(norms[i + 1], nt):
                    continue  # "inequality is" is just "inequality" (vs "INEQUALITIES") plus a word
                pair_ratio = 1.0 if nc + norms[i + 1] == nt else plausible(nc + norms[i + 1], nt)
                singles = max(similarity(nc, nt), similarity(norms[i + 1], nt))
                if pair_ratio >= 0.55 and pair_ratio > singles + 0.05:
                    add(f"{tokens[i]} {tokens[i + 1]}", term, pair_ratio)
    return suggestions


def _spoken(term: str, spoken_words: set[str], spoken_joined: str) -> bool:
    """Was an on-screen term said? Exact word, a long term inside the speech, or an
    abbreviation that starts a spoken word ("Fri" -> "Friday")."""
    return (
        term in spoken_words
        or (len(term) > 5 and term in spoken_joined)
        or (len(term) >= 3 and term.isalpha() and any(w.startswith(term) for w in spoken_words))
    )


def cross_reference(segments: list[Segment], keyframes: list[Keyframe], duration: float,
                    is_common: IsCommon | None = None, extra_terms: list[str] | None = None,
                    exclude: set[str] | None = None) -> dict:
    """Align speech and visuals; returns scenes and correction suggestions.

    ``extra_terms`` (the user's glossary) are checked against every segment;
    ``exclude`` (interface words) are never treated as slide terms.
    """
    scenes = build_scenes(keyframes, duration)
    assign_scenes(segments, scenes)

    by_scene: dict[int | None, list[Segment]] = {}
    for seg in segments:
        by_scene.setdefault(seg.scene_id, []).append(seg)

    user_terms = [w for t in (extra_terms or []) for w in tokenize(t)]
    corrections: list[dict] = []
    for scene in scenes:
        scene_segments = by_scene.get(scene.id, [])
        scene.spoken_text = " ".join(s.text.strip() for s in scene_segments).strip()
        terms = extract_vocabulary([scene.ocr_text], limit=25, is_common=is_common, exclude=exclude)
        spoken_norm = {norm(w) for w in tokenize(scene.spoken_text)}
        spoken_joined = norm(scene.spoken_text)
        scene.terms_confirmed = [t for t in terms if _spoken(norm(t), spoken_norm, spoken_joined)]
        scene.terms_unspoken = [t for t in terms if t not in scene.terms_confirmed]
        # A term on screen in the neighbouring scene is still a good candidate (slides change mid-sentence).
        neighbour_terms = terms + extract_vocabulary(
            [s.ocr_text for s in scenes if abs(s.id - scene.id) == 1], limit=15, is_common=is_common,
            exclude=exclude,
        ) + user_terms
        for seg in scene_segments:
            corrections.extend(find_corrections(seg, neighbour_terms))
    if not scenes and user_terms:
        for seg in segments:
            corrections.extend(find_corrections(seg, user_terms))
    for i, c in enumerate(corrections):
        c["id"], c["status"] = i, "pending"
    return {"scenes": scenes, "corrections": corrections}


# ---------------------------------------------------------------- editing helpers
def apply_correction(segment: dict, heard: str, seen: str) -> bool:
    """Replace ``heard`` with ``seen`` in a stored segment's text and word list."""
    pattern = r"(?<![\w])" + r"[\s\-]*".join(re.escape(p) for p in re.split(r"[\s\-]+", heard)) + r"(?![\w])"
    new_text, n = re.subn(pattern, lambda _: seen, segment["text"], count=1, flags=re.IGNORECASE)
    if not n:
        return False
    segment["text"] = new_text
    words = segment.get("words")
    run = _word_run(words or [], norm(heard))
    if run is not None:
        i, j = run
        first, last = words[i], words[j]
        lead = first[2][: len(first[2]) - len(first[2].lstrip())]
        trail = re.search(r"[^\w]*$", last[2].strip()).group()
        segment["words"] = words[:i] + [[first[0], last[1], f"{lead}{seen}{trail}", 1.0]] + words[j + 1:]
    return True


def compute_stats(result: dict) -> dict:
    segments = result.get("segments", [])
    words = [w for s in segments for w in (s.get("words") or [])]
    word_count = len(words) or sum(len(s["text"].split()) for s in segments)
    return {
        "segments": len(segments),
        "words": word_count,
        "scenes": len(result.get("keyframes", [])),
        "speakers": len(result.get("speakers", [])),
        "low_confidence_words": sum(1 for w in words if len(w) > 3 and w[3] < 0.5),
        "corrections_pending": sum(1 for c in result.get("corrections", []) if c.get("status") == "pending"),
    }


def fmt_ts(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _condense(text: str, limit: int = 700) -> str:
    text = " · ".join(line.strip() for line in text.splitlines() if line.strip())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def build_notes_context(result: dict, max_chars: int = 400_000) -> str:
    """Render a stored result as the merged timeline the LLM reads.

        === FILE: meeting.mp4 | TITLE: Weekly sync | DURATION: 00:37 ===
        SPEAKERS: S1 = Priya, S2 = Speaker 2

        [SCENE 2 | 00:13–00:26] Snowflake Costs Q3
        SCREEN: Snowflake Costs Q3 · Warehouse tuning: -18% cost · ...
        ON SCREEN BUT NOT SPOKEN: ARR
        SPEECH [00:13] Priya: What about the Snowflake costs?
    """
    names = {s["id"]: s.get("name") or s["id"] for s in result.get("speakers", [])}
    duration = (result.get("media") or {}).get("duration") or 0
    header = f"=== FILE: {result.get('filename', '')}"
    if result.get("title") and result.get("title") != result.get("filename"):
        header += f" | TITLE: {result['title']}"
    lines = [header + f" | DURATION: {fmt_ts(duration)} ==="]
    if names:
        lines.append("SPEAKERS: " + ", ".join(f"{k} = {v}" for k, v in names.items()))

    def speech(segs: list[dict]) -> list[str]:
        """Consecutive sentences of one speaker form one paragraph, with a fresh timestamp
        at least every minute so citations stay precise (keeps long meetings compact)."""
        out: list[str] = []
        group: list[dict] = []

        def flush():
            if group:
                spk = group[0].get("speaker")
                who = f" {names.get(spk, spk)}:" if spk else ""
                out.append(f"SPEECH [{fmt_ts(group[0]['start'])}]{who} " + " ".join(s["text"].strip() for s in group))
                group.clear()

        for seg in segs:
            if group and (seg.get("speaker") != group[0].get("speaker") or seg["start"] - group[0]["start"] > 60):
                flush()
            group.append(seg)
        flush()
        return out

    segments = result.get("segments", [])
    scenes = result.get("keyframes", [])
    if not scenes:
        lines += speech(segments)
    else:
        by_scene: dict[int | None, list[dict]] = {}
        for seg in segments:
            by_scene.setdefault(seg.get("scene_id"), []).append(seg)
        lines += speech(by_scene.get(None, []))
        for scene in scenes:
            title = f" {scene['title']}" if scene.get("title") else ""
            lines.append(f"\n[SCENE {scene['id'] + 1} | {fmt_ts(scene['t'])}–{fmt_ts(scene['end'])}]{title}")
            if scene.get("duplicate_of") is not None:
                lines.append(f"SCREEN: same slide as scene {scene['duplicate_of'] + 1}")
            elif (scene.get("ocr_text") or "").strip():
                lines.append(f"SCREEN: {_condense(scene['ocr_text'])}")
            if scene.get("caption"):
                lines.append(f"VISUAL: {_condense(scene['caption'], 400)}")
            if scene.get("terms_unspoken") and scene.get("duplicate_of") is None:
                lines.append(f"ON SCREEN BUT NOT SPOKEN: {', '.join(scene['terms_unspoken'][:12])}")
            lines += speech(by_scene.get(scene["id"], []))
    pending = [c for c in result.get("corrections", []) if c.get("status", "pending") == "pending"]
    if pending:
        lines.append("\nPOSSIBLE MIS-TRANSCRIPTIONS (spoken -> spelling on screen):")
        lines += [f"- [{fmt_ts(c['t'])}] \"{c['heard']}\" -> \"{c['seen']}\"" for c in pending[:100]]
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[: max_chars - 60] + "\n[... context truncated to fit the model window ...]"
    return text
