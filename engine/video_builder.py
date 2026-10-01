"""
Video Builder - MoviePy (free, offline)
- Ken Burns zoom on images
- Audio + auto subtitles from script
- Title card, watermark, progress bar
- 9:16 vertical (shorts) or 16:9 horizontal (youtube)
"""
import os
import re
import numpy as np
from PIL import Image, ImageDraw, ImageFont


EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]+",
    flags=re.UNICODE,
)


def _strip_emoji(text: str) -> str:
    """Remove emojis (DejaVu has no emoji glyphs -> tofu boxes)."""
    text = EMOJI_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _load_font(size: int):
    """Try common fonts, fallback to default."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "arial.ttf",
    ]
    for p in candidates:
        try:
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _ken_burns(clip, W: int, H: int, per: float, zoom_in: bool = True,
               pan: tuple[float, float] = (0.0, 0.0), zoom_range: float = 0.22):
    """Zoom + drift each frame then crop back to exactly W,H (never any bars).

    pan=(px,py): fraction of the available crop margin to sweep across the clip
    (e.g. (0.8,-0.5) drifts right and up). zoom_range: total zoom travel.
    """
    px, py = (pan or (0.0, 0.0))[:2]

    def make_frame(gf, t):
        t = max(0.0, min(t, per))
        k = (t / per) if per > 0 else 0
        # v5 cinematic easing: linear Ken Burns motion looks mechanical. Smoothstep
        # gives a gentle acceleration/deceleration while keeping deterministic framing.
        k = k * k * (3.0 - 2.0 * k)
        top = 1.06 + zoom_range
        s = (1.06 + zoom_range * k) if zoom_in else (top - zoom_range * k)
        img = Image.fromarray(gf(t))
        nw, nh = int(W * s), int(H * s)
        img = img.resize((nw, nh), Image.BILINEAR)
        mx, my = nw - W, nh - H
        x = int(mx * min(1.0, max(0.0, 0.5 + px * (k - 0.5))))
        y = int(my * min(1.0, max(0.0, 0.5 + py * (k - 0.5))))
        return np.asarray(img.crop((x, y, x + W, y + H)))
    return clip.fl(make_frame, keep_duration=True)


def _wrap(text: str, width: int = 22) -> str:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= width:
            cur = (cur + " " + w).strip()
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return "\n".join(lines[:4])


def _subtitle_png(text: str, path: str, W: int, fontsize: int = 44):
    """Render wrapped subtitle with black bg bar."""
    text = _strip_emoji(text)
    wrapped = _wrap(text, 20 if W < 800 else 34)
    font = _load_font(fontsize)
    # measure
    tmp = Image.new("RGB", (10, 10))
    d = ImageDraw.Draw(tmp)
    bbox = d.multiline_textbbox((0, 0), wrapped, font=font, spacing=6)
    tw, th = bbox[2] - bbox[0] + 50, bbox[3] - bbox[1] + 36
    img = Image.new("RGBA", (tw, th), (0, 0, 0, 190))
    d = ImageDraw.Draw(img)
    d.multiline_text((25, 16), wrapped, font=font, fill=(255, 255, 255),
                     align="center", spacing=6)
    img.save(path)


def _title_png(title: str, path: str, W: int, H: int):
    title = _strip_emoji(title)
    wrapped = _wrap(title, 16 if W < 800 else 28)
    font = _load_font(64 if W < 800 else 80)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bbox = d.multiline_textbbox((0, 0), wrapped, font=font, spacing=8)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x, y = (W - tw) // 2, int(H * 0.18)
    # shadow + text
    d.multiline_text((x + 4, y + 4), wrapped, font=font, fill=(0, 0, 0, 220),
                     align="center", spacing=8)
    d.multiline_text((x, y), wrapped, font=font, fill=(255, 210, 40),
                     align="center", spacing=8)
    img.save(path)


def build_video(images: list, audio_path: str, script: str, scenes: list,
                output_path: str, title: str = "My Video",
                vertical: bool = True, watermark: str = "",
                subtitle_style: str = "word-pop") -> dict:
    from moviepy.editor import (AudioFileClip, ImageClip, TextClip,
                                CompositeVideoClip, concatenate_videoclips,
                                ColorClip)

    W, H = (1080, 1920) if vertical else (1920, 1080)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    workdir = os.path.dirname(os.path.abspath(output_path))

    audio = AudioFileClip(audio_path)
    total = audio.duration

    # --- Ken Burns clips ---
    per = total / max(1, len(images))
    clips = []
    for i, img_path in enumerate(images):
        # resize/crop to exact W,H with PIL first
        im = Image.open(img_path).convert("RGB")
        im = _cover_resize(im, W, H)
        resized = os.path.join(workdir, f"_rz{i:02d}.jpg")
        im.save(resized, quality=88)

        clip = ImageClip(resized, duration=per)
        # alternate zoom in / zoom out; every frame stays exactly W,H
        clip = _ken_burns(clip, W, H, per, zoom_in=(i % 2 == 0),
                          pan=(0.7 if i % 4 < 2 else -0.7, 0.4 if i % 2 == 0 else -0.4))
        clip = clip.set_duration(per)
        clips.append(clip)

    video = concatenate_videoclips(clips, method="chain")
    video = video.set_duration(total).set_fps(24)
    # ensure exact size
    if video.w != W or video.h != H:
        video = video.resize((W, H))

    overlays = [video]

    # --- Subtitles (one per scene, timed evenly) ---
    for i, scene in enumerate(scenes):
        start = i * (total / max(1, len(scenes)))
        dur = total / max(1, len(scenes))
        sub_png = os.path.join(workdir, f"_sub{i:02d}.png")
        # chunk long scenes into shorter text
        short = scene[:160]
        _subtitle_png(short, sub_png, W, fontsize=40 if vertical else 44)
        sc = (ImageClip(sub_png)
              .set_start(start).set_duration(dur)
              .set_position(("center", H * 0.72 if vertical else H * 0.78)))
        overlays.append(sc)

    # --- Title card (first 3 sec) ---
    title_png = os.path.join(workdir, "_title.png")
    _title_png(title, title_png, W, H)
    tc = (ImageClip(title_png).set_start(0).set_duration(min(3.2, total))
          .set_position("center"))
    overlays.append(tc)

    # --- Progress bar (bottom) ---
    try:
        bar_h = 8
        bar_bg = (ColorClip(size=(W, bar_h), color=(60, 60, 60))
                  .set_position((0, H - bar_h)).set_duration(total))
        overlays.append(bar_bg)
        # animated fill via mask trick: use resized clip
        # Simple static full bar with opacity looks fine; do cropped growing bar:
        from moviepy.editor import ImageClip as IC
        import numpy as np
        bar_img = os.path.join(workdir, "_bar.png")
        Image.new("RGB", (W, bar_h), (255, 60, 60)).save(bar_img)
        # growing width: we fake with resize lambda on X only via cropping each frame is complex;
        # use a plain full bar at low opacity — clean look
        bar = (IC(bar_img).set_position((0, H - bar_h)).set_duration(total).set_opacity(0.9))
        overlays.append(bar)
    except Exception:
        pass

    # --- Watermark ---
    if watermark:
        try:
            wm = (TextClip(watermark, fontsize=28, color="white",
                           font="DejaVu-Sans-Bold")
                  .set_position(("right", "top"))
                  .set_duration(total).set_opacity(0.7).margin(right=16, top=16))
            overlays.append(wm)
        except Exception:
            pass  # ImageMagick missing -> skip text watermark

    final = CompositeVideoClip(overlays, size=(W, H)).set_duration(total)
    final = final.set_audio(audio)

    final.write_videofile(output_path, fps=24, codec="libx264",
                          audio_codec="aac", preset="medium",
                          logger=None, threads=2)
    # cleanup temp
    for f in os.listdir(workdir):
        if f.startswith("_rz") or f.startswith("_sub") or f in ("_title.png", "_bar.png"):
            try:
                os.remove(os.path.join(workdir, f))
            except Exception:
                pass
    audio.close()
    final.close()
    return {"video": output_path, "duration": total,
            "size": f"{W}x{H}", "scenes": len(scenes)}


def _cover_resize(im: Image.Image, W: int, H: int) -> Image.Image:
    """Resize + center-crop to cover W,H."""
    iw, ih = im.size
    scale = max(W / iw, H / ih)
    nw, nh = int(iw * scale) + 1, int(ih * scale) + 1
    im = im.resize((nw, nh), Image.LANCZOS)
    x, y = (nw - W) // 2, (nh - H) // 2
    return im.crop((x, y, x + W, y + H))


# ==================== v2: motion clips + word captions + music ====================

def _video_cover_clip(path: str, W: int, H: int):
    """Load a video file and cover-crop to exactly W,H."""
    from moviepy.editor import VideoFileClip
    c = VideoFileClip(path)
    if not c.w or not c.h:
        raise RuntimeError(f"Unreadable clip: {path}")
    scale = max(W / c.w, H / c.h)
    c = c.resize(scale)
    c = c.crop(x_center=c.w / 2, y_center=c.h / 2, width=W, height=H)
    return c


def _wordpop_png(words: list, active: int, path: str, W: int):
    """CapCut-style caption PNG with one active word and a soft background.

    v5.0 used separate transparent word overlays with no group background. When
    ASR timings touched/overlapped, two complete phrases could briefly render on
    top of one another. v5.1 renders a single self-contained phrase card and the
    event scheduler guarantees non-overlapping display windows.
    """
    words = [_strip_emoji(w) or w for w in words]
    for fontsize in (58, 52, 46, 40, 34):
        font = _load_font(fontsize)
        lines, cur, cur_w = [], [], 0
        tmp = Image.new("RGB", (10, 10))
        d = ImageDraw.Draw(tmp)
        space = d.textlength(" ", font=font)
        for w in words:
            ww = d.textlength(w, font=font)
            if cur and cur_w + space + ww > W - 150:
                lines.append(cur)
                cur, cur_w = [], 0
            cur.append(w)
            cur_w += (space if cur_w else 0) + ww
        if cur:
            lines.append(cur)
        if len(lines) <= 2:
            break
    lh = int(fontsize * 1.32)
    card_h = lh * len(lines) + 34
    img = Image.new("RGBA", (W, card_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Subtle translucent pill/card; avoids text disappearing on bright footage.
    d.rounded_rectangle((35, 2, W - 35, card_h - 4), radius=22, fill=(0, 0, 0, 118))
    flat_idx = 0
    for li, line in enumerate(lines):
        widths = [d.textlength(w, font=font) for w in line]
        total = sum(widths) + space * (len(line) - 1)
        x = (W - total) // 2
        y = 13 + li * lh
        for w, ww in zip(line, widths):
            color = (255, 209, 37, 255) if flat_idx == active else (255, 255, 255, 255)
            d.text((x, y), w, font=font, fill=color,
                   stroke_width=2, stroke_fill=(0, 0, 0, 255))
            x += ww + space
            flat_idx += 1
    img.save(path)


def _wordpop_events(words: list, total: float) -> list[dict]:
    """Build strictly non-overlapping word-pop events."""
    from .captions import group_words
    events = []
    groups = list(group_words(words or []))
    for gi, g in enumerate(groups):
        ws = list(g.get("words") or [])
        labels = [str(w.get("word", "")) for w in ws]
        next_group_start = (float(groups[gi + 1]["start"]) if gi + 1 < len(groups) else float(total))
        for j, w in enumerate(ws):
            start = max(0.0, float(w.get("start", 0.0)))
            next_word = float(ws[j + 1].get("start", total)) if j + 1 < len(ws) else next_group_start
            end = min(float(total), next_word - 0.012, float(g.get("end", total)) + 0.12)
            if end <= start + 0.04:
                end = min(float(total), start + 0.12)
            # Guard against ASR overlap/out-of-order timestamps.
            if events and start < events[-1]["end"]:
                start = events[-1]["end"]
            if end <= start + 0.03:
                continue
            events.append({"start": start, "end": end, "labels": labels, "active": j})
    return events


def burn_wordpop_captions(video_path: str, words: list, output_path: str,
                          vertical: bool = True) -> dict:
    """Burn captions onto an already-finished FFmpeg render.

    This is the libass-independent v5.1 fallback. Only the caption compositing
    pass uses MoviePy; timeline, transitions, sound mix and duration remain the
    FFmpeg master render.
    """
    from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
    import tempfile, shutil as _shutil
    base = VideoFileClip(video_path)
    W, H = int(base.w), int(base.h)
    total = float(base.duration or 0)
    tmp = tempfile.mkdtemp(prefix="autovideo_caps_")
    overlays = [base]
    try:
        events = _wordpop_events(words or [], total)
        for i, ev in enumerate(events):
            png = os.path.join(tmp, f"cap_{i:04d}.png")
            _wordpop_png(ev["labels"], ev["active"], png, W)
            overlays.append(
                ImageClip(png).set_start(ev["start"]).set_duration(ev["end"] - ev["start"])
                .set_position(("center", H * (0.64 if vertical else 0.73))))
        final = CompositeVideoClip(overlays, size=(W, H)).set_duration(total).set_audio(base.audio)
        final.write_videofile(output_path, fps=getattr(base, "fps", 24) or 24,
                              codec="libx264", audio_codec="aac", preset="veryfast",
                              ffmpeg_params=["-crf", "18", "-movflags", "+faststart"],
                              logger=None, threads=2)
        final.close()
    finally:
        try:
            base.close()
        except Exception:
            pass
        _shutil.rmtree(tmp, ignore_errors=True)
    return {"video": output_path, "events": len(_wordpop_events(words or [], total)),
            "caption_engine": "moviepy-pillow-overlay"}


def build_video_from_clips(clips: list, audio_path: str, script: str, scenes: list,
                           output_path: str, title: str = "My Video",
                           vertical: bool = True, watermark: str = "",
                           music_path: str | None = None,
                           words: list | None = None,
                           caption_style: str = "wordpop") -> dict:
    """v2 builder: motion clips + crossfades + punch zoom + word captions + music bed."""
    from moviepy.editor import (AudioFileClip, ImageClip, TextClip,
                                CompositeVideoClip, CompositeAudioClip,
                                concatenate_videoclips, concatenate_audioclips,
                                ColorClip)
    from moviepy.audio.fx.all import volumex, audio_fadein, audio_fadeout

    if not clips:
        raise ValueError("No motion clips provided.")
    W, H = (1080, 1920) if vertical else (1920, 1080)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    workdir = os.path.dirname(os.path.abspath(output_path))

    audio = AudioFileClip(audio_path)
    total = audio.duration
    n = max(1, len(scenes))
    overlap = 0.45 if n > 1 else 0.0
    per = (total + overlap * (n - 1)) / n

    # --- scene segments: cover-crop, trim/loop, punch zoom ---
    segs = []
    for i in range(n):
        base = _video_cover_clip(clips[i % len(clips)], W, H)
        dur = base.duration or per
        if dur < per - 0.05:
            reps = int(per // dur) + 1
            base = concatenate_videoclips([base] * reps).subclip(0, per)
        else:
            max_start = max(0.0, dur - per)
            start = ((i * 1.618) % 1.0) * max_start if max_start > 0 else 0
            base = base.subclip(start, start + per)
        base = _ken_burns(base, W, H, per, zoom_in=(i % 2 == 0))
        segs.append(base.set_duration(per).set_fps(24))

    # --- crossfade assembly ---
    positioned, t = [], 0.0
    for i, s in enumerate(segs):
        s = s.set_start(t)
        if i > 0 and overlap > 0:
            s = s.crossfadein(overlap)
        positioned.append(s)
        t += per - overlap
    video = CompositeVideoClip(positioned, size=(W, H)).set_duration(total)
    overlays = [video]

    # --- captions ---
    if words and caption_style == "wordpop":
        # Use the same strictly non-overlapping scheduler as the v5.1
        # caption-only fallback. This prevents adjacent ASR words/groups from
        # rendering two full phrase cards on top of each other.
        for k, ev in enumerate(_wordpop_events(words, total)):
            png = os.path.join(workdir, f"_cap{k:04d}.png")
            _wordpop_png(ev["labels"], ev["active"], png, W)
            overlays.append(
                ImageClip(png).set_start(ev["start"]).set_duration(ev["end"] - ev["start"])
                .set_position(("center", H * 0.64 if vertical else H * 0.74)))
    else:  # classic scene captions
        for i, scene in enumerate(scenes):
            start = i * (total / n)
            dur = total / n
            png = os.path.join(workdir, f"_sub{i:02d}.png")
            _subtitle_png(scene[:160], png, W, fontsize=40 if vertical else 44)
            overlays.append(
                ImageClip(png).set_start(start).set_duration(dur)
                .set_position(("center", H * 0.72 if vertical else H * 0.78)))

    # --- title card ---
    title_png = os.path.join(workdir, "_title.png")
    _title_png(title, title_png, W, H)
    overlays.append(ImageClip(title_png).set_start(0)
                    .set_duration(min(3.2, total)).set_position("center"))

    # --- progress bar ---
    try:
        bar_h = 8
        overlays.append(ColorClip(size=(W, bar_h), color=(60, 60, 60))
                        .set_position((0, H - bar_h)).set_duration(total))
        bar_img = os.path.join(workdir, "_bar.png")
        Image.new("RGB", (W, bar_h), (255, 60, 60)).save(bar_img)
        overlays.append(ImageClip(bar_img).set_position((0, H - bar_h))
                        .set_duration(total).set_opacity(0.9))
    except Exception:
        pass

    # --- watermark ---
    if watermark:
        try:
            overlays.append(TextClip(watermark, fontsize=28, color="white",
                                     font="DejaVu-Sans-Bold")
                            .set_position(("right", "top")).set_duration(total)
                            .set_opacity(0.7).margin(right=16, top=16))
        except Exception:
            pass

    # --- music bed (ducked low under voice) ---
    final_audio = audio
    if music_path and os.path.exists(music_path):
        try:
            m = AudioFileClip(music_path)
            reps = int(total // (m.duration or total)) + 2
            bed = (concatenate_audioclips([m] * reps).subclip(0, total)
                   .fx(volumex, 0.10).fx(audio_fadein, 1.0).fx(audio_fadeout, 2.0))
            final_audio = CompositeAudioClip([audio, bed])
        except Exception as e:
            print(f"Music bed skipped: {e}")

    final = CompositeVideoClip(overlays, size=(W, H)).set_duration(total)
    final = final.set_audio(final_audio)
    final.write_videofile(output_path, fps=24, codec="libx264",
                          audio_codec="aac", preset="medium",
                          logger=None, threads=2)
    for f in os.listdir(workdir):
        if f.startswith(("_rz", "_sub", "_cap")) or f in ("_title.png", "_bar.png"):
            try:
                os.remove(os.path.join(workdir, f))
            except Exception:
                pass
    audio.close()
    final.close()
    return {"video": output_path, "duration": total,
            "size": f"{W}x{H}", "scenes": n,
            "captions": "wordpop" if words else "classic",
            "music": bool(music_path and os.path.exists(music_path or ""))}
