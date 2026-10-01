import os
from engine.render.ffmpeg_renderer import build_ffmpeg_cmd, detect_encoder
from engine.providers.flow_browser import FlowBrowser, FlowState

SEGS = [{"shot_id": "shot_001", "src": "a.mp4", "in": 0, "dur": 6.0, "freeze": 0,
         "trans_in": "cut", "trans_out": "dissolve"},
        {"shot_id": "shot_002", "src": "b.mp4", "in": 1, "dur": 8.0, "freeze": 0.5,
         "trans_in": "cut", "trans_out": "cut"}]


def test_ffmpeg_cmd_construction(workdir):
    cmd, meta = build_ffmpeg_cmd(SEGS, "voice.mp3", "out.mp4", W=1080, H=1920,
                                 music="m.mp3", quality="standard", encoder="libx264")
    s = " ".join(cmd)
    assert "xfade" in s and "loudnorm" in s
    assert "sidechaincompress" not in s  # m.mp3 doesn't exist -> skipped honestly
    assert meta["total"] == round(6.0 + 8.5 - 0.35, 3)
    assert "-t" in cmd and "libx264" in s and "aac" in s
    # with real music file -> ducking appears
    open("m.mp3", "wb").write(b"x" * 100)
    cmd2, _ = build_ffmpeg_cmd(SEGS, "voice.mp3", "out.mp4", music="m.mp3", encoder="libx264")
    assert "sidechaincompress" in " ".join(cmd2)
    assert detect_encoder() in ("h264_nvenc", "h264_qsv", "h264_amf", "libx264")


def test_flow_states_and_watch(workdir):
    assert FlowState.GENERATING.value == "GENERATING"
    states = [s.value for s in FlowState]
    for k in ("SUBMITTING", "GENERATING", "QC", "ACCEPTED", "RETRYING", "FAILED"):
        assert k in states
    # assisted watch detects a fresh finished file
    os.makedirs("dl", exist_ok=True)
    p = "dl/Flow Clip 1.mp4"
    with open(p, "wb") as f:
        f.write(b"0" * 200000)
    got = FlowBrowser.watch_folder("dl", known=set(), timeout_s=20, poll=1)
    assert got == p
    assert FlowBrowser.watch_folder("dl", known={p}, timeout_s=2, poll=1) is None
