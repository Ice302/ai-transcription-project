import numpy as np

from app.vision import OcrLine, detect_title, find_duplicates, frame_change, select_keyframes


def _frames(values):
    return np.array([np.full((36, 64), v, dtype=np.uint8) for v in values])


def test_detects_hard_cuts():
    # 0-9 s black, 10-19 s white, 20-29 s grey
    frames = _frames([0] * 10 + [255] * 10 + [128] * 10)
    keep = select_keyframes(np.arange(30.0), frames, threshold=0.1, min_gap=2, max_gap=60)
    assert keep == [0, 10, 20]


def test_static_video_gets_periodic_samples():
    keep = select_keyframes(np.arange(200.0), _frames([50] * 200), threshold=0.1, min_gap=2, max_gap=60)
    assert keep == [0, 60, 120, 180]


def test_min_gap_suppresses_flicker():
    frames = _frames([0, 255] * 10)
    keep = select_keyframes(np.arange(20.0), frames, threshold=0.1, min_gap=5, max_gap=60)
    assert all(b - a >= 5 for a, b in zip(keep, keep[1:]))


def test_gradual_build_is_caught():
    # Brightness creeps up 2/255 per second: each step is tiny but the total is large.
    frames = _frames([i * 2 for i in range(100)])
    keep = select_keyframes(np.arange(100.0), frames, threshold=0.1, min_gap=1, max_gap=1000)
    assert len(keep) > 1


def test_max_keyframes_cap():
    frames = _frames([0, 255] * 100)
    keep = select_keyframes(np.arange(200.0), frames, threshold=0.1, min_gap=1, max_gap=60, max_keyframes=10)
    assert len(keep) == 10 and keep[0] == 0 and keep == sorted(keep)


def test_empty():
    assert select_keyframes(np.array([]), np.zeros((0, 36, 64), dtype=np.uint8)) == []


def test_small_text_change_counts_as_new_slide():
    # Same dark background, a block of "text" (5% of pixels) changes: a new slide.
    a = np.full((36, 64), 30, dtype=np.uint8)
    b = a.copy()
    b[5:10, 5:28] = 230
    assert frame_change(a, b) > 0.04
    keep = select_keyframes(np.arange(20.0), np.array([a] * 10 + [b] * 10), threshold=0.02)
    assert keep == [0, 10]


def test_compression_noise_is_ignored():
    rng = np.random.default_rng(0)
    base = np.full((36, 64), 120, dtype=np.int16)
    frames = np.array([np.clip(base + rng.integers(-8, 9, base.shape), 0, 255).astype(np.uint8) for _ in range(30)])
    assert select_keyframes(np.arange(30.0), frames, threshold=0.02) == [0]


def test_find_duplicates_spots_flip_backs():
    a, b = _frames([10])[0], _frames([200])[0]
    noisy_a = a.copy()
    noisy_a[0, :3] = 30  # a few pixels of compression noise
    assert find_duplicates([a, b, noisy_a, b, a]) == [None, None, 0, 1, 0]


def _line(text, y, h):
    return OcrLine(text, 0.99, 10, y, h)


def test_detect_title_picks_the_tallest_text():
    lines = [_line("Q3 Revenue", 50, 60), _line("Grew 42% to 4.2M", 200, 32), _line("Owner: Priya", 260, 32)]
    assert detect_title(lines) == "Q3 Revenue"


def test_detect_title_joins_two_line_titles():
    lines = [_line("Kubernetes", 40, 58), _line("Migration Plan", 105, 60), _line("Step 1", 250, 30), _line("Step 2", 300, 30)]
    assert detect_title(lines) == "Kubernetes Migration Plan"


def test_no_title_for_uniform_text():
    lines = [_line(f"line {i}", i * 30, 24) for i in range(6)]
    assert detect_title(lines) == ""
    assert detect_title([]) == ""
    assert detect_title([_line("Only line", 0, 20)]) == "Only line"


def test_equations_are_not_titles():
    lines = [_line("2x²-x-3=0", 50, 60), _line("Solve for x", 200, 30), _line("using the formula", 240, 30)]
    assert detect_title(lines) == ""


def test_all_caps_first_line_is_a_title_when_sizes_are_equal():
    lines = [_line("QUADRATIC EQUATIONS", 20, 30), _line("Standard form", 60, 30), _line("Roots", 100, 30)]
    assert detect_title(lines) == "QUADRATIC EQUATIONS"
