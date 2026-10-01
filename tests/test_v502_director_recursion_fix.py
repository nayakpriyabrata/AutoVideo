from engine.planning.director import _split_long_sentences


def _w(word, start, end):
    return {"word": word, "start": start, "end": end}


def test_v502_unsplittable_long_segment_terminates_without_recursion():
    # Reproduces the old infinite-recursion condition: a >8s segment with
    # fewer than six words used to be returned unchanged and recursively
    # processed forever.
    words = [
        _w("One", 0.0, 0.4),
        _w("very", 2.8, 3.2),
        _w("long", 5.5, 5.9),
        _w("sentence", 8.7, 9.2),
        _w("ends.", 11.5, 12.0),
    ]
    sents = [{"text": "One very long sentence ends.", "start": 0.0, "end": 12.0}]
    out = _split_long_sentences(words, sents, 8.0)
    assert out
    assert len(out) >= 2
    assert out[0]["start"] == 0.0
    assert out[-1]["end"] == 12.0


def test_v502_malformed_timings_never_recurse_forever():
    words = [
        _w("broken", 0.0, 0.0),
        _w("timing", 0.0, 0.0),
    ]
    sents = [{"text": "broken timing", "start": 0.0, "end": 30.0}]
    out = _split_long_sentences(words, sents, 8.0)
    assert len(out) == 1
    assert out[0]["end"] == 30.0


def test_v502_normal_sentence_is_unchanged():
    words = [_w("Short", 0.0, 0.4), _w("sentence.", 0.5, 1.0)]
    sents = [{"text": "Short sentence.", "start": 0.0, "end": 1.0}]
    assert _split_long_sentences(words, sents, 8.0) == sents
