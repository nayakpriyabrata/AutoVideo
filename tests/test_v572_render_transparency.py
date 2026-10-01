from pathlib import Path


def test_graphics_cards_remain_transparent(tmp_path):
    from engine.render.graphics import OverlayEvent, render_overlay_png
    from PIL import Image

    for kind in ("intro", "chapter", "keypoint", "progress_list", "recap", "outro"):
        p = tmp_path / f"{kind}.png"
        render_overlay_png(OverlayEvent(kind, 0, 2, "BUILD A BETTER FUTURE", "Keep moving forward"),
                           str(p), 1080, 1920)
        alpha = Image.open(p).convert("RGBA").getchannel("A")
        # No editorial card may cover most of the frame with near-opaque black.
        near_opaque = sum(1 for value in alpha.getdata() if value >= 180)
        assert near_opaque / (1080 * 1920) < 0.08


def test_black_integrity_threshold_rejects_large_blank_intervals():
    from engine.render.ffmpeg_renderer import MAX_BLACK_RATIO
    assert MAX_BLACK_RATIO <= 0.20
