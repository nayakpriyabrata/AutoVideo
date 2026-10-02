import pytest

from engine import captions
from engine.narration_policy import (
    buffered_script_target_seconds,
    narration_duration_matches_target,
    narration_grace_seconds,
)
from engine.planning.script import plan_content


def test_five_minute_voiceover_asks_for_six_minute_script_headroom():
    assert narration_grace_seconds(300) == 60
    assert buffered_script_target_seconds(300) == 360
    assert buffered_script_target_seconds(300, voiceover_enabled=False) == 300


def test_script_planner_honors_the_buffered_word_count():
    plan = plan_content(
        "How to build better daily habits", duration_sec=300,
        use_llm=False, script_quality="standard", target_words=700,
    )
    assert plan["words"] >= int(700 * 0.96)


def test_longform_voiceover_accepts_up_to_one_minute_drift():
    assert narration_duration_matches_target(240, 300)
    assert narration_duration_matches_target(360, 300)
    assert not narration_duration_matches_target(239.9, 300)
    assert not narration_duration_matches_target(360.1, 300)


def test_ten_minute_target_buffer_is_bounded_to_one_minute():
    assert narration_grace_seconds(600) == 60
    assert buffered_script_target_seconds(600) == 660


def test_short_video_keeps_existing_percentage_tolerance():
    assert narration_grace_seconds(60) == 0
    assert buffered_script_target_seconds(60) == 60
    assert narration_duration_matches_target(55.2, 60)
    assert narration_duration_matches_target(66.6, 60)
    assert not narration_duration_matches_target(54, 60)
    assert not narration_duration_matches_target(67, 60)


def test_caption_asr_failure_falls_back_to_exact_script_timing(monkeypatch, tmp_path):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"not-decoded-by-this-test")

    def fail_provider(*args, **kwargs):
        raise captions.CaptionProviderError("Groq unavailable")

    monkeypatch.setattr(captions, "get_word_timestamps", fail_provider)
    monkeypatch.setattr(captions, "_audio_duration", lambda _path: 0.0)

    words = captions.get_word_timestamps_resilient(
        str(audio), provider="groq", script_text="A robust voiceover survives.",
        audio_duration=300,
    )

    assert [word["word"] for word in words] == ["A", "robust", "voiceover", "survives."]
    assert words[-1]["end"] == 300
    assert all(word["start"] <= word["end"] <= 300 for word in words)


def test_caption_fallback_still_fails_if_no_audio_duration_or_script(monkeypatch, tmp_path):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"not-decoded-by-this-test")
    monkeypatch.setattr(
        captions, "get_word_timestamps",
        lambda *args, **kwargs: (_ for _ in ()).throw(captions.CaptionProviderError("ASR unavailable")),
    )
    monkeypatch.setattr(captions, "_audio_duration", lambda _path: 0.0)

    with pytest.raises(captions.CaptionProviderError):
        captions.get_word_timestamps_resilient(
            str(audio), provider="groq", script_text="", audio_duration=0,
        )
