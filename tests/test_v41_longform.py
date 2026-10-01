from engine.planning.director import _sentences_with_time, _split_long_sentences


def test_long_paragraph_transcript_is_split_into_visual_beats():
    words = []
    for i in range(600):
        t = i * 0.5
        w = f"word{i}"
        if (i + 1) % 75 == 0:
            w += "."
        words.append({"word": w, "start": t, "end": t + 0.4})
    original = _sentences_with_time(words)
    assert len(original) == 8
    split = _split_long_sentences(words, original, 8)
    assert len(split) >= 30
    assert max(x["end"] - x["start"] for x in split) <= 9.1
