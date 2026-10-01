"""Readable captions and valid timings for YouTube, Shorts, and reels."""
from pathlib import Path
import re
import subprocess

import numpy as np
import pytest

from engine.render.captions_ass import (
    TEMPLATES, _fmt_ass, _fmt_srt, _wrap2, build_captions, words_to_phrases,
)


def words(tokens, step=.4):
    return [{"word": word, "start": i * step, "end": (i + 1) * step}
            for i, word in enumerate(tokens)]


def events(path):
    result = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("Dialogue:"):
            fields = line.split(",", 9)
            def seconds(stamp):
                h, m, s = stamp.split(":")
                assert 0 <= float(s) < 60
                return int(h) * 3600 + int(m) * 60 + float(s)
            result.append((seconds(fields[1]), seconds(fields[2]), fields[9]))
    return result


def visible(text):
    return re.sub(r"\{[^}]*\}", "", text)


@pytest.mark.parametrize("seconds,ass,srt", [
    (0, "0:00:00.00", "00:00:00,000"),
    (-.5, "0:00:00.00", "00:00:00,000"),
    (59.999, "0:01:00.00", "00:00:59,999"),
    (3599.999, "1:00:00.00", "00:59:59,999"),
    (59.9999, "0:01:00.00", "00:01:00,000"),
    (3599.9999, "1:00:00.00", "01:00:00,000"),
    (3600.001, "1:00:00.00", "01:00:00,001"),
    (59.9949, "0:00:59.99", "00:00:59,995"),
])
def test_timestamps_round_with_minute_and_hour_carry(seconds, ass, srt):
    assert _fmt_ass(seconds) == ass
    assert _fmt_srt(seconds) == srt


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_timestamp_formatter_rejects_nonfinite_values(value):
    with pytest.raises(ValueError):
        _fmt_ass(value)
    with pytest.raises(ValueError):
        _fmt_srt(value)


def test_wrap_measures_visible_words_not_ass_tags():
    plain = "extraordinarily short a b"
    tagged = " ".join(r"{\c&H00FFFFFF}" + token for token in plain.split())
    assert visible(_wrap2(tagged)) == _wrap2(plain)
    assert _wrap2(plain) == r"extraordinarily\Nshort a b"


def test_single_long_word_has_no_empty_second_line():
    assert _wrap2("antidisestablishmentarianism") == "antidisestablishmentarianism"


def test_phrase_character_limit_counts_spaces():
    phrases = words_to_phrases(words(["a", "b"]), max_chars=2)
    assert [p["text"] for p in phrases] == ["a", "b"]


def test_slow_speech_does_not_leave_a_phrase_on_screen_too_long():
    phrases = words_to_phrases(words(["one", "two", "three", "four"], step=1))
    assert max(p["end"] - p["start"] for p in phrases) <= 3
    assert " ".join(p["text"] for p in phrases) == "one two three four"


@pytest.mark.parametrize("template", list(TEMPLATES))
def test_tightly_spaced_phrases_have_positive_nonoverlapping_events(tmp_path, template):
    result = build_captions(words(["Go.", "Now.", "Yes."], step=.02),
                            str(tmp_path / template), template=template)
    cues = events(result["ass"])
    assert len(cues) == 3
    assert all(end > start for start, end, _ in cues)
    assert all(a[1] <= b[0] for a, b in zip(cues, cues[1:]))


def test_overlapping_word_timestamps_do_not_overlap_srt_cues(tmp_path):
    timings = [{"word": "First.", "start": 0, "end": .8},
               {"word": "Second.", "start": .6, "end": 1}]
    result = build_captions(timings, str(tmp_path / "captions"))
    srt = Path(result["srt"]).read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:00,600" in srt
    assert "00:00:00,600 --> 00:00:01,000" in srt


def test_karaoke_preserves_real_word_onsets_including_pauses(tmp_path):
    timings = [{"word": "Choose", "start": 0, "end": .2},
               {"word": "wisely", "start": .65, "end": 1}]
    result = build_captions(timings, str(tmp_path / "captions"), template="KARAOKE")
    text = events(result["ass"])[0][2]
    assert re.findall(r"\\k(\d+)", text)[0] == "65"


@pytest.mark.parametrize("aspect,W,H,margins", [
    ("9:16", 540, 960, [30, 30, 170]),
    ("16:9", 960, 540, [40, 40, 55]),
])
def test_safe_zones_and_font_scale_to_output_resolution(tmp_path, aspect, W, H, margins):
    result = build_captions(words(["Readable", "captions"]), str(tmp_path / "captions"),
                            template="HORMOZI", aspect=aspect, W=W, H=H)
    style = next(line for line in Path(result["ass"]).read_text().splitlines()
                 if line.startswith("Style: Cap,")).removeprefix("Style: ").split(",")
    assert int(style[2]) == 42
    assert [int(x) for x in style[19:22]] == margins
    assert len(style) == 23


def test_caption_hold_is_clamped_to_video_duration(tmp_path):
    result = build_captions(words(["Stop.", "Outside."], step=1),
                            str(tmp_path / "captions"), duration=.75)
    cues = events(result["ass"])
    assert len(cues) == 1 and cues[-1][1] == .75
    srt = Path(result["srt"]).read_text()
    assert "00:00:00,750" in srt and "Outside" not in srt


@pytest.mark.parametrize("timings", [
    [{"word": "bad", "start": float("nan"), "end": 1}],
    [{"word": "bad", "start": 0, "end": float("inf")}],
    [{"word": "bad", "start": 1, "end": .5}],
    [{"word": "bad", "start": -.1, "end": .5}],
    [{"word": "bad", "start": 0}],
    [{"word": "later", "start": 1, "end": 2}, {"word": "earlier", "start": 0, "end": 1}],
])
def test_invalid_word_timings_fail_before_writing_files(tmp_path, timings):
    with pytest.raises(ValueError, match="word"):
        build_captions(timings, str(tmp_path / "captions"))
    assert not (tmp_path / "captions.ass").exists()


def test_empty_captions_still_produce_valid_sidecars(tmp_path):
    result = build_captions([], str(tmp_path / "captions"))
    assert result["events"] == 0
    assert "[Events]" in Path(result["ass"]).read_text()
    assert Path(result["srt"]).read_text() == ""


def test_real_libass_keeps_highlight_layout_stable(ffmpeg_binary, tmp_path):
    filters = subprocess.run([ffmpeg_binary, "-filters"], capture_output=True, text=True, timeout=15)
    if "subtitles" not in filters.stdout + filters.stderr:
        pytest.skip("FFmpeg was built without libass")
    result = build_captions(words("extraordinarily short a b".split(), step=.5),
                            str(tmp_path / "captions"), aspect="16:9", W=320, H=180)
    # This calls the real subtitles filter at two different highlight positions.
    # Text must stay inside the scaled safe zone and not reflow as color changes.
    from engine.render.ffmpeg_renderer import _esc_filter_path
    boxes = []
    for at in (.25, .75):
        cmd = [ffmpeg_binary, "-v", "error", "-f", "lavfi", "-i",
               "color=c=black:s=320x180:r=24:d=2",
               "-vf", f"subtitles='{_esc_filter_path(result['ass'])}'",
               "-ss", str(at), "-frames:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
        rendered = subprocess.run(cmd, capture_output=True, timeout=30)
        assert rendered.returncode == 0, rendered.stderr.decode(errors="replace")
        frame = np.frombuffer(rendered.stdout, dtype=np.uint8).reshape(180, 320, 3)
        y, x = np.where(frame.max(axis=2) > 30)
        assert len(x) > 100, "Captions were not visible in the rendered frame"
        assert x.min() >= 10 and x.max() < 310
        assert y.max() < 180 - 15
        boxes.append((x.min(), x.max(), y.min(), y.max()))
    assert boxes[0] == boxes[1]
