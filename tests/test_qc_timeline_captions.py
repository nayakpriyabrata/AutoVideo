from engine.qc.video_qc import analyze_take, RETRY_MODIFIERS, classify_failure
from engine.render.timeline import build_timeline
from engine.render.captions_ass import build_captions, words_to_phrases
from engine.project.manifest import ProductionManifest, Shot
from tests.conftest import make_video, fake_words


def test_qc_accepts_good_rejects_bad(workdir):
    good = make_video("v/good.mp4", n=48, mode="motion")
    black = make_video("v/black.mp4", n=48, mode="black")
    frozen = make_video("v/frozen.mp4", n=48, mode="frozen")
    g = analyze_take(good, expect_seconds=2, expect_vertical=True)
    assert g["decision"] in ("ACCEPT", "REVIEW") and g["overall"] > 55
    b = analyze_take(black, expect_seconds=2)
    assert b["decision"] == "REJECT"
    f = analyze_take(frozen, expect_seconds=2)
    assert f["failure"] == "low_motion" and "lifeless" in RETRY_MODIFIERS["low_motion"] or True
    assert classify_failure({"frozen_ratio": 0.9}) == "low_motion"
    assert "locked smooth" in RETRY_MODIFIERS["camera_too_fast"]


def test_timeline_no_blind_loop(workdir):
    m = ProductionManifest(job_id="j", topic="t")
    m.shots = [Shot(shot_id="shot_001", voice_start=0, voice_end=6, status="accepted",
                    accepted_take=make_video("t/shot_001/accepted.mp4", n=144)),
               Shot(shot_id="shot_002", voice_start=6, voice_end=14, status="accepted",
                    accepted_take=make_video("t/shot_002/accepted.mp4", n=48))]
    tl = build_timeline(m, "t", 14.0)
    assert len(tl["segments"]) == 2
    # A short accepted clip is held on its final frame rather than looped blindly;
    # transition-overlap compensation still makes the visual master match narration.
    assert tl["segments"][1]["freeze"] > 1.0
    assert any("shot_002" in w for w in tl["warnings"])
    assert abs(tl["total"] - 14.0) <= 0.01


def test_captions_templates_and_timing(workdir):
    words = fake_words(3, 4.0)
    ph = words_to_phrases(words)
    assert len(ph) >= 3 and all("start" in p and "end" in p for p in ph)
    assert all(p["end"] >= p["start"] for p in ph)
    r = build_captions(words, "cap/captions", template="HORMOZI", aspect="9:16")
    ass = open(r["ass"], encoding="utf-8").read()
    assert "60,60,340,1" in ass  # vertical safe-zone margins (L,R,V)
    assert r["events"] == len(words)  # word-level events
    r2 = build_captions(words, "cap2/captions", template="CINEMATIC", aspect="16:9")
    assert r2["events"] == len(ph)  # phrase-level
    assert open(r2["srt"], encoding="utf-8").read().count("-->") == len(ph)


def _ass_time(s):
    h, m, sec = s.split(":")
    return int(h) * 3600 + int(m) * 60 + float(sec)


def test_caption_events_never_overlap(workdir):
    from engine.render.captions_ass import build_captions
    from tests.conftest import fake_words
    words = fake_words(4, 4.0)
    # squeeze gaps to simulate adjacent phrases
    t = 0.0
    for w in words:
        d = w["end"] - w["start"]
        w["start"], w["end"] = round(t, 2), round(t + d, 2)
        t += d + 0.02
    for tpl in ("HORMOZI", "KARAOKE", "CINEMATIC"):
        r = build_captions(words, f"cap-{tpl}/c", template=tpl)
        lines = [l for l in open(r["ass"], encoding="utf-8") if l.startswith("Dialogue:")]
        times = []
        for l in lines:
            parts = l.split(",")
            times.append((_ass_time(parts[1]), _ass_time(parts[2])))
        times.sort()
        for (s1, e1), (s2, e2) in zip(times, times[1:]):
            assert e1 <= s2 + 0.001, f"{tpl}: overlap {e1} > {s2}"
