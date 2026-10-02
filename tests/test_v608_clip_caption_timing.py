from engine.clipping import _clip_word_timings, _normalize_word_timings
from engine.render.captions_ass import build_captions


def test_provider_word_timings_are_sorted_and_invalid_ends_are_repaired():
    source = [
        {"word": "later", "start": 2.0, "end": 1.9},
        {"word": "first", "start": 0.5, "end": 0.8},
        {"word": "middle", "start": 1.1, "end": 1.3},
    ]

    words = _normalize_word_timings(source, total=3.0)

    assert [word["word"] for word in words] == ["first", "middle", "later"]
    assert all(word["start"] <= word["end"] for word in words)
    assert [word["start"] for word in words] == sorted(word["start"] for word in words)
    assert words[-1]["end"] >= words[-1]["start"]


def test_clip_window_clamps_and_orders_asr_words_before_caption_build(tmp_path):
    source = [
        {"word": "inside-late", "start": 4.2, "end": 4.7},
        {"word": "before", "start": 1.0, "end": 1.5},
        {"word": "inside-first", "start": 2.2, "end": 2.5},
        {"word": "crosses-end", "start": 4.8, "end": 5.6},
        {"word": "bad-end", "start": 3.2, "end": 3.0},
    ]

    words = _clip_word_timings(source, start=2.0, end=5.0)

    assert [word["word"] for word in words] == [
        "inside-first", "bad-end", "inside-late", "crosses-end",
    ]
    assert [word["start"] for word in words] == sorted(word["start"] for word in words)
    assert all(0 <= word["start"] <= word["end"] <= 3.0 for word in words)
    # Keep the caption renderer's strict ordering check enabled; the clip path
    # repairs provider timing before handing words to this shared validator.
    result = build_captions(words, str(tmp_path / "clip-caption"), duration=3.0)
    assert result["events"] > 0
