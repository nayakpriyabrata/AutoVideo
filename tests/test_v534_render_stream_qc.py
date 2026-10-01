from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from engine.render.ffmpeg_renderer import (
    _black_duration_ratio,
    _probe_av_durations,
    _video_coverage_ratio,
)


def _ffmpeg():
    return shutil.which('ffmpeg')


@pytest.mark.skipif(_ffmpeg() is None, reason='ffmpeg not installed')
def test_video_stream_coverage_detects_audio_longer_than_picture(tmp_path: Path):
    out = tmp_path / 'short-video-long-audio.mp4'
    cmd = [
        _ffmpeg(), '-y',
        '-f', 'lavfi', '-i', 'color=c=white:s=320x180:r=24:d=2',
        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=44100:duration=4',
        '-map', '0:v:0', '-map', '1:a:0',
        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
        str(out),
    ]
    cp = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert cp.returncode == 0, cp.stderr
    d = _probe_av_durations(str(out))
    assert d['video'] is not None and 1.8 <= d['video'] <= 2.2
    assert d['audio'] is not None and 3.8 <= d['audio'] <= 4.2
    cov = _video_coverage_ratio(str(out), 4.0)
    assert cov is not None and 0.45 <= cov <= 0.55


@pytest.mark.skipif(_ffmpeg() is None, reason='ffmpeg not installed')
def test_missing_video_tail_counts_as_blank(tmp_path: Path):
    out = tmp_path / 'short-video-long-audio.mp4'
    cmd = [
        _ffmpeg(), '-y',
        '-f', 'lavfi', '-i', 'color=c=white:s=320x180:r=24:d=2',
        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=44100:duration=4',
        '-map', '0:v:0', '-map', '1:a:0',
        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
        str(out),
    ]
    cp = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert cp.returncode == 0, cp.stderr
    ratio = _black_duration_ratio(str(out), expected_duration=4.0)
    # Picture itself is white, so the approximately 2-second missing tail is
    # what contributes the black/missing visual ratio.
    assert ratio is not None and 0.45 <= ratio <= 0.55
