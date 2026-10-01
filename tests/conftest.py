"""Shared fixtures: isolated cwd, synthetic videos, fake word timings."""
import os
import cv2
import numpy as np
import pytest


@pytest.fixture()
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def make_video(path: str, n: int = 48, w: int = 320, h: int = 576,
               mode: str = "motion", fps: int = 24):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for i in range(n):
        if mode == "black":
            fr = np.zeros((h, w, 3), np.uint8)
        elif mode == "frozen":
            fr = np.full((h, w, 3), 120, np.uint8)
        else:  # motion: moving gradient + box
            fr = np.zeros((h, w, 3), np.uint8)
            fr[:] = (60 + i * 2) % 200
            x = int((i / n) * (w - 60))
            cv2.rectangle(fr, (x, h // 3), (x + 60, h // 3 + 120), (255, 255, 255), -1)
            cv2.putText(fr, "test", (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        vw.write(fr)
    vw.release()
    return path


def fake_words(n_sent: int = 8, sent_dur: float = 4.0):
    words, t = [], 0.0
    for s in range(n_sent):
        for k in range(10):
            w = f"word{k}." if k == 9 else f"word{k}"
            words.append({"word": w, "start": round(t, 2), "end": round(t + 0.35, 2)})
            t += 0.4
    return words


@pytest.fixture(scope="session")
def ffmpeg_binary():
    """Use the system or bundled FFmpeg; no network or provider calls."""
    import subprocess
    from engine.render.ffmpeg_renderer import ffmpeg_exe

    try:
        exe = ffmpeg_exe()
        result = subprocess.run([exe, "-version"], capture_output=True, timeout=15)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        pytest.skip(f"FFmpeg is unavailable: {exc}")
    if result.returncode:
        pytest.skip("FFmpeg cannot run in this environment")
    return exe


@pytest.fixture(scope="session")
def ffmpeg_media(tmp_path_factory, ffmpeg_binary):
    """Small deterministic sources for real render/audio regression tests."""
    import subprocess
    import wave

    root = tmp_path_factory.mktemp("ffmpeg-media")
    video = root / "visual.mp4"
    result = subprocess.run(
        [ffmpeg_binary, "-y", "-v", "error", "-f", "lavfi", "-i",
         "testsrc2=size=320x180:rate=24", "-t", "4", "-c:v", "libx264",
         "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(video)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr

    rate = 48000
    t = np.arange(4 * rate) / rate

    def wav(name, samples):
        path = root / name
        channels = samples.shape[1] if samples.ndim == 2 else 1
        with wave.open(str(path), "wb") as fh:
            fh.setnchannels(channels)
            fh.setsampwidth(2)
            fh.setframerate(rate)
            fh.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
        return str(path)

    voice = .2 * np.sin(2 * np.pi * 440 * t)
    music = np.column_stack((.08 * np.sin(2 * np.pi * 220 * t),
                             .05 * np.sin(2 * np.pi * 330 * t)))
    return {
        "video": str(video),
        "voice": wav("voice.wav", voice),
        "voice_pauses": wav("voice-pauses.wav", voice * ((t >= 1) & (t < 3))),
        "music": wav("music.wav", music),
        "silence": wav("silence.wav", np.zeros((len(t), 2))),
        "sfx": wav("sfx.wav", .1 * np.sin(2 * np.pi * 880 * t[:rate // 4])),
    }
