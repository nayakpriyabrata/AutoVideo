"""Audio quality checks, including actual offline FFmpeg renders."""
import subprocess

import numpy as np
import pytest

from engine.render.ffmpeg_renderer import build_ffmpeg_cmd


def render_audio(ffmpeg_binary, media, out, **kwargs):
    voice = kwargs.pop("voice", media["voice"])
    cmd, meta = build_ffmpeg_cmd(
        [{"src": media["video"], "in": 0, "dur": 4, "freeze": 0, "hard_cut": True}],
        voice, str(out), W=320, H=180, fps=24, encoder="libx264",
        quality="preview", safe_concat=True, **kwargs,
    )
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr[-5000:]
    decoded = subprocess.run(
        [ffmpeg_binary, "-v", "error", "-i", str(out), "-map", "0:a:0",
         "-ar", "48000", "-f", "f32le", "-"],
        capture_output=True, timeout=30,
    )
    assert decoded.returncode == 0, decoded.stderr.decode(errors="replace")
    # The stereo master must actually retain two channels, not just claim it
    # in metadata. Decode without -ac so an accidental mono mix fails here.
    samples = np.frombuffer(decoded.stdout, dtype="<f4").reshape(-1, 2)
    assert abs(len(samples) / 48000 - meta["total"]) < .05
    assert np.isfinite(samples).all()
    return samples


@pytest.mark.parametrize("use_loudnorm", [True, False])
@pytest.mark.parametrize("bed", ["music", "ambience", "sfx", "all"])
def test_real_ffmpeg_renders_sound_beds(ffmpeg_binary, ffmpeg_media, tmp_path, bed, use_loudnorm):
    kwargs = {"use_loudnorm": use_loudnorm}
    if bed in ("music", "all"):
        kwargs["music"] = ffmpeg_media["music"]
    if bed in ("ambience", "all"):
        kwargs["ambience"] = ffmpeg_media["music"]
    if bed in ("sfx", "all"):
        kwargs["sfx"] = [{"path": ffmpeg_media["sfx"], "at": 1.2, "vol": .2}]
    samples = render_audio(ffmpeg_binary, ffmpeg_media, tmp_path / "mixed.mp4", **kwargs)
    assert np.sqrt(np.mean(samples ** 2)) > .01
    if bed in ("music", "ambience", "all"):
        assert np.sqrt(np.mean((samples[:, 0] - samples[:, 1]) ** 2)) > .0001


def test_silent_music_does_not_attenuate_narration(ffmpeg_binary, ffmpeg_media, tmp_path):
    plain = render_audio(ffmpeg_binary, ffmpeg_media, tmp_path / "plain.mp4", use_loudnorm=False)
    mixed = render_audio(ffmpeg_binary, ffmpeg_media, tmp_path / "mixed.mp4",
                         music=ffmpeg_media["silence"], use_loudnorm=False)
    rms = lambda samples: float(np.sqrt(np.mean(samples[48000:3 * 48000] ** 2)))
    assert rms(mixed) / rms(plain) == pytest.approx(1, abs=.025)


def tone_amplitude(samples, frequency, start, end):
    signal = samples[int(start * 48000):int(end * 48000), 0]
    t = np.arange(len(signal)) / 48000
    # Measure only the music frequency, excluding the 440 Hz narration.
    return float(2 * abs(np.mean(signal * np.exp(-2j * np.pi * frequency * t))))


@pytest.mark.parametrize("repeat", range(3))
def test_background_music_ducks_during_speech(ffmpeg_binary, ffmpeg_media, tmp_path, repeat):
    samples = render_audio(ffmpeg_binary, ffmpeg_media, tmp_path / "ducked.mp4",
                           voice=ffmpeg_media["voice_pauses"],
                           music=ffmpeg_media["music"], use_loudnorm=False)
    before = tone_amplitude(samples, 220, .2, .7)
    during = tone_amplitude(samples, 220, 1.6, 2.2)
    after = tone_amplitude(samples, 220, 3.6, 3.95)
    assert during < before * .5
    # A 600ms release intentionally recovers gradually; do not require full
    # gain recovery less than a second after speech stops (AAC also adds delay).
    assert after > during * 1.2


def test_ducking_graph_splits_voice_and_preserves_mix_gain(tmp_path):
    music = tmp_path / "music.wav"
    music.write_bytes(b"fixture")
    _, meta = build_ffmpeg_cmd(
        [{"src": "visual.mp4", "in": 0, "dur": 4}], "voice.wav", "out.mp4",
        music=str(music), encoder="libx264",
    )
    graph = meta["filter_complex"]
    assert "[voice]asplit=2[voice_mix][voice_sidechain]" in graph
    assert "[bed][voice_sidechain]sidechaincompress" in graph
    assert "[voice_mix][duck]amix=inputs=2" in graph
    assert graph.count("normalize=0") == 2
    assert "atrim=0:5.0[voice]" in graph and "atrim=0:5.0[bed]" in graph
    assert "normalize=0,atrim=0:4.0[mix]" in graph
    assert meta["total"] == 4  # The internal drain guard is not part of the movie.


def test_voice_only_graph_needs_no_split():
    _, meta = build_ffmpeg_cmd(
        [{"src": "visual.mp4", "in": 0, "dur": 4}], "voice.wav", "out.mp4",
        encoder="libx264",
    )
    assert "asplit" not in meta["filter_complex"]
    assert "sidechaincompress" not in meta["filter_complex"]
