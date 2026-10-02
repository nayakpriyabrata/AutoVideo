"""
FFmpeg production renderer (primary). MoviePy remains as fallback.
filter_complex: cover-crop -> xfade chain -> ASS burn -> sidechain ducking -> loudnorm.
Auto-selects NVENC / QSV / AMF / x264.
"""
from __future__ import annotations
import os
import json
import math
import re
import shutil
import subprocess
import tempfile
import queue
import threading
import time
from types import SimpleNamespace

QUALITY = {
    "preview": {"preset": "ultrafast", "crf": 28, "nv_preset": "p1", "cq": 30},
    "standard": {"preset": "medium", "crf": 20, "nv_preset": "p5", "cq": 21},
    "high": {"preset": "slow", "crf": 17, "nv_preset": "p7", "cq": 18},
}

# Near-black footage is measured with a very strict 2% pixel threshold.  A
# normal intentionally dark scene does not trip this easily, while the broken
# WSL xfade/tpad output is pure black.  Twenty percent is already unacceptable
# for a finished edit and warrants the deterministic concat recovery.
MAX_BLACK_RATIO = 0.20
MAX_FROZEN_RATIO = 0.20
MAX_SINGLE_FREEZE_SECONDS = 8.0


def ffmpeg_exe() -> str:
    p = shutil.which("ffmpeg")
    if p:
        return p
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _ffmpeg_text(arg: str) -> str:
    try:
        r = subprocess.run([ffmpeg_exe(), "-hide_banner", arg],
                           capture_output=True, text=True, timeout=30)
        return (r.stdout or "") + (r.stderr or "")
    except Exception:
        return ""


def detect_encoder() -> str:
    t = _ffmpeg_text("-encoders")
    if "h264_nvenc" in t:
        return "h264_nvenc"
    if "h264_qsv" in t:
        return "h264_qsv"
    if "h264_amf" in t:
        return "h264_amf"
    return "libx264"


def has_subtitles_filter() -> bool:
    return " subtitles " in (" " + _ffmpeg_text("-filters").replace("\n", " ") + " ") or "subtitles" in _ffmpeg_text("-filters")


def _esc_filter_path(p: str) -> str:
    p = os.path.abspath(p).replace("\\", "/")
    return p.replace(":", "\\:").replace("'", "\\'")


FONTS_DIR_CANDIDATES = (
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets", "fonts"),
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    os.path.expanduser("~/.fonts"),
    os.path.expanduser("~/.local/share/fonts"),
    "/mnt/c/Windows/Fonts",   # WSL: real fonts live on the Windows side
    "C:/Windows/Fonts",
    "/System/Library/Fonts",
)


def _dir_has_font(d: str) -> bool:
    """True if a .ttf/.otf/.ttc exists at top level or one subdir down."""
    try:
        with os.scandir(d) as it:
            entries = [(e.name, e.is_dir()) for e in it]
    except OSError:
        return False
    for name, is_dir in entries:
        if not is_dir and name.lower().endswith((".ttf", ".otf", ".ttc")):
            return True
    for name, is_dir in entries:
        if is_dir and not name.startswith("."):
            try:
                with os.scandir(os.path.join(d, name)) as it2:
                    for e2 in it2:
                        if e2.name.lower().endswith((".ttf", ".otf", ".ttc")):
                            return True
            except OSError:
                continue
    return False


def _fontsdir() -> str | None:
    for d in FONTS_DIR_CANDIDATES:
        if os.path.isdir(d) and _dir_has_font(d):
            return d
    return None


def _checked_seconds(value, label: str, *, minimum: float = 0.0, maximum: float = 6 * 3600) -> float:
    try:
        v = float(value)
    except Exception as e:
        raise ValueError(f"Invalid {label}: {value!r}") from e
    if not math.isfinite(v) or v < minimum or v > maximum:
        raise ValueError(f"Invalid {label}: {value!r}")
    return v


def build_ffmpeg_cmd(segments: list[dict], narration: str | None, out_path: str,
                     W: int = 1080, H: int = 1920, fps: int = 24,
                     ass_path: str | None = None, music: str | None = None,
                     ambience: str | None = None, sfx: list[dict] | None = None,
                     overlays: list[dict] | None = None, music_volume: float = 0.10,
                     stereo_master: bool = True, audio_bitrate: int = 192,
                     quality: str = "standard",
                     encoder: str | None = None,
                     use_fontsdir: bool = True,
                     use_loudnorm: bool = True,
                     safe_concat: bool = False,
                     loop_short_segments: bool = False) -> tuple[list, dict]:
    """Build (cmd, meta). Pure function of inputs -> fully unit-testable."""
    ff = ffmpeg_exe()
    enc = encoder or detect_encoder()
    q = QUALITY.get(quality, QUALITY["standard"])
    burn = bool(ass_path and os.path.exists(ass_path) and has_subtitles_filter())

    cmd = [ff, "-y"]
    # video inputs with fast pre-seek
    for i, s in enumerate(segments):
        seek = _checked_seconds(s.get("in", 0), f"segment[{i}].in", minimum=0.0)
        dur = _checked_seconds(s.get("dur"), f"segment[{i}].dur", minimum=0.05)
        freeze = _checked_seconds(s.get("freeze", 0) or 0,
                                  f"segment[{i}].freeze", minimum=0.0)
        # Integrity recovery must never turn a short source into a minute-long
        # still frame. Repeat its motion instead; this is both faster and much
        # closer to a normal editorial B-roll treatment than tpad/clone.
        if loop_short_segments and freeze > 0:
            cmd += ["-stream_loop", "-1", "-ss", str(seek),
                    "-t", str(dur + freeze), "-i", s["src"]]
        else:
            cmd += ["-ss", str(seek), "-t", str(dur), "-i", s["src"]]
    v_n = len(segments)
    a_voice = None
    next_idx = v_n
    if narration:
        cmd += ["-i", narration]
        a_voice = next_idx
        next_idx += 1
    a_music = a_ambient = None
    if music and os.path.exists(music):
        cmd += ["-stream_loop", "-1", "-i", music]
        a_music = next_idx
        next_idx += 1
    if ambience and os.path.exists(ambience):
        cmd += ["-stream_loop", "-1", "-i", ambience]
        a_ambient = next_idx
        next_idx += 1
    sfx_idx = []
    for e in (sfx or []):
        if e.get("path") and os.path.exists(e["path"]):
            cmd += ["-i", e["path"]]
            sfx_idx.append((next_idx, e))
            next_idx += 1
    overlay_idx = []
    for e in (overlays or []):
        if e.get("path") and os.path.exists(e["path"]):
            # Transparent PNG overlays are looped for the whole render and gated
            # by enable=between(t,start,end) in the filter graph.
            cmd += ["-loop", "1", "-i", e["path"]]
            overlay_idx.append((next_idx, e))
            next_idx += 1

    # ---- video graph ----
    F = []
    eff_durs = []
    for i, s in enumerate(segments):
        fz = _checked_seconds(s.get("freeze", 0) or 0, f"segment[{i}].freeze", minimum=0.0)
        dur = _checked_seconds(s.get("dur"), f"segment[{i}].dur", minimum=0.05)
        eff = dur + fz
        eff_durs.append(eff)
        chain = (f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
                 f"crop={W}:{H},setsar=1,fps={fps},format=yuv420p")
        if safe_concat:
            # concat requires each input to begin at t=0; keep the primary xfade
            # graph untouched because older FFmpeg builds are sensitive to
            # explicit timebase rewrites around xfade.
            chain += ",setpts=PTS-STARTPTS"
        if fz > 0 and not loop_short_segments:
            chain += f",tpad=stop_mode=clone:stop_duration={fz}"
        F.append(chain + f"[v{i}]")
    # xfade chain (dissolve=0.35s, hard cut~=1 frame). Every input is
    # normalized to a zero-based timestamp/timebase above. MoviePy/MP4 edit
    # lists can otherwise leave non-zero PTS and make xfade output black after
    # the first segment even though every source clip is valid.
    xdurs = []
    for i, s in enumerate(segments[:-1]):
        xdurs.append(0.0 if s.get("hard_cut") and safe_concat else
                     (0.35 if s.get("trans_out") == "dissolve" else 0.01))
    total = round(sum(eff_durs) - sum(xdurs), 3) if v_n else 0
    if not math.isfinite(total) or total <= 0 or total > 6 * 3600:
        raise ValueError(f"Invalid rendered timeline duration: {total!r}")

    if safe_concat:
        # Emergency renderer: preserve every visual with deterministic hard
        # cuts and then trim to the narration-aligned xfade duration. This is
        # intentionally simpler than xfade and is used only when post-render
        # QC detects a mostly-black primary output.
        labels = "".join(f"[v{i}]" for i in range(v_n))
        F.append(f"{labels}concat=n={v_n}:v=1:a=0[vcat]")
        F.append(f"[vcat]trim=duration={total},setpts=PTS-STARTPTS[vsafe]")
        cur = "[vsafe]"
    else:
        cur, off_acc, xd_acc = "[v0]", 0.0, 0.0
        for k in range(1, v_n):
            off_acc += eff_durs[k - 1]
            xd_acc += xdurs[k - 1]
            off = round(off_acc - xd_acc, 3)
            F.append(f"{cur}[v{k}]xfade=transition=fade:duration={xdurs[k-1]}:offset={off}[x{k}]")
            cur = f"[x{k}]"
    last = cur
    # global gentle fade in/out
    F.append(f"{last}fade=t=in:st=0:d=0.4,fade=t=out:st={max(0.5, round(total-0.5,3))}:d=0.5[vf]")
    vcur = "[vf]"
    for j, (idx, e) in enumerate(overlay_idx):
        st = _checked_seconds(e.get("start", 0), f"overlay[{j}].start", minimum=0.0)
        en = _checked_seconds(e.get("end", total), f"overlay[{j}].end", minimum=0.0)
        en = min(total, max(st + 0.05, en))
        overlay_filter = f"[{idx}:v]scale={W}:{H},format=rgba"
        fade_in = min((en-st)/2, _checked_seconds(e.get("fade_in", 0), f"overlay[{j}].fade_in"))
        fade_out = min((en-st)/2, _checked_seconds(e.get("fade_out", 0), f"overlay[{j}].fade_out"))
        if fade_in:
            overlay_filter += f",fade=t=in:st={st:.3f}:d={fade_in:.3f}:alpha=1"
        if fade_out:
            overlay_filter += f",fade=t=out:st={en-fade_out:.3f}:d={fade_out:.3f}:alpha=1"
        F.append(overlay_filter + f"[ov{j}]")
        F.append(f"{vcur}[ov{j}]overlay=0:0:enable='between(t,{st:.3f},{en:.3f})'[vg{j}]")
        vcur = f"[vg{j}]"
    if burn:
        fd = _fontsdir() if use_fontsdir else None
        sub = f"subtitles='{_esc_filter_path(ass_path)}'" + (f":fontsdir='{_esc_filter_path(fd)}'" if fd else "")
        F.append(f"{vcur}{sub}[vout]")
        vmap = "[vout]"
    else:
        vmap = vcur

    # ---- audio graph ----
    # Normalize layouts BEFORE mixing. A mono TTS track used as amix's first
    # input otherwise downmixed stereo music/ambience before mastering, even
    # though the final file claimed to be stereo.
    audio_input = "aresample=48000,asetpts=PTS-STARTPTS"
    if stereo_master:
        audio_input += ",aformat=channel_layouts=stereo"
    # Keep both sidechain/mix branches alive while the mixer drains. Ending
    # them simultaneously can drop the music tail on FFmpeg 7. The one-second
    # internal silence guard is removed from the mixed output below.
    has_bed = a_music is not None or a_ambient is not None or bool(sfx_idx)
    has_audio = a_voice is not None or has_bed
    audio_end = round(total + (1.0 if has_bed and a_voice is not None else 0.0), 3)
    if a_voice is not None:
        F.append(f"[{a_voice}:a]{audio_input},atrim=0:{total},apad,atrim=0:{audio_end}[voice]")
    bed_labels = []
    if a_music is not None:
        F.append(f"[{a_music}:a]{audio_input},atrim=0:{total},volume={max(0.0, min(1.0, float(music_volume))):.3f}[mus]")
        bed_labels.append("[mus]")
    if a_ambient is not None:
        F.append(f"[{a_ambient}:a]{audio_input},atrim=0:{total},volume=0.06[amb]")
        bed_labels.append("[amb]")
    for idx, e in sfx_idx:
        ms = int(_checked_seconds(e.get("at", 0), f"sfx[{idx}].at") * 1000)
        F.append(f"[{idx}:a]{audio_input},adelay={ms}:all=1,volume={e.get('vol', 0.5)}[sfx{idx}]")
        bed_labels.append(f"[sfx{idx}]")
    if bed_labels:
        beds = "".join(bed_labels)
        # Keep short SFX/ambience beds alive through the narration timeline;
        # extending silence here does not loop or invent any sound effects.
        F.append(f"{beds}amix=inputs={len(bed_labels)}:duration=longest:dropout_transition=0:normalize=0,apad,atrim=0:{audio_end}[bed]")
        if a_voice is not None:
            # Filter outputs are single-consumer. The sidechain detector and audible
            # narration need separate branches; reusing [voice] made every render
            # with music, ambience, or SFX fail with 'matches no streams'.
            F.append("[voice]asplit=2[voice_mix][voice_sidechain]")
            F.append("[bed][voice_sidechain]sidechaincompress=threshold=0.03:ratio=8:attack=200:release=600[duck]")
            # amix's default normalization halves narration gain just because a bed
            # exists, even when that bed is silent. Keep configured gains intact;
            # the loudness master below handles normal publish-path peak control.
            F.append(f"[voice_mix][duck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,atrim=0:{total}[mix]")
        else:
            # Instrumental edit: no phantom voice, detector, or ducking.
            F.append(f"[bed]atrim=0:{total}[mix]")
    elif a_voice is not None:
        F.append("[voice]anull[mix]")
    if has_audio and use_loudnorm:
        amix_in = "[mix]"
        if stereo_master:
            F.append("[mix]aformat=sample_rates=48000:channel_layouts=stereo[mixst]")
            amix_in = "[mixst]"
        F.append(f"{amix_in}loudnorm=I=-14:TP=-1.5:LRA=11[aout]")
    elif has_audio:
        # Preserve the compatible retry graph without the fragile loudness
        # filter. Input layouts/gains are already correct, so a stereo master
        # remains stereo on this path too; target loudness still needs review.
        F.append("[mix]anull[aout]")

    cmd += ["-filter_complex", ";".join(F), "-map", vmap]
    if has_audio:
        cmd += ["-map", "[aout]"]
    else:
        cmd += ["-an"]  # Intentional silent edit; never retain generated-clip speech.
    if enc == "h264_nvenc":
        cmd += ["-c:v", enc, "-preset", q["nv_preset"], "-cq", str(q["cq"])]
    elif enc == "h264_qsv":
        cmd += ["-c:v", enc, "-preset", "medium", "-global_quality", str(q["crf"])]
    elif enc == "h264_amf":
        cmd += ["-c:v", enc, "-quality", "quality", "-qp_i", str(q["crf"])]
    else:
        cmd += ["-c:v", "libx264", "-preset", q["preset"], "-crf", str(q["crf"])]
    cmd += ["-pix_fmt", "yuv420p", "-profile:v", "high", "-level:v", "4.1",
            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
            ]
    if has_audio:
        cmd += ["-c:a", "aac", "-b:a", f"{int(audio_bitrate)}k", "-ar", "48000"]
    cmd += ["-movflags", "+faststart", "-t", str(total), out_path]
    meta = {"encoder": enc, "quality": quality, "total": total,
            "voiceover_enabled": a_voice is not None, "audio_present": has_audio,
            "audio_mode": "voiceover" if a_voice is not None else ("instrumental" if has_audio else "silent"),
            "captions_requested": bool(ass_path), "burn_captions": burn,
            "segments": len(segments), "use_loudnorm": use_loudnorm,
            "safe_concat": bool(safe_concat), "overlays": len(overlay_idx),
            "loop_short_segments": bool(loop_short_segments),
            "music_volume": float(music_volume), "stereo_master": bool(stereo_master),
            "filter_complex": ";".join(F)}
    return cmd, meta



def _probe_av_durations(path: str) -> dict:
    """Return independent container/video/audio durations for render QC.

    MP4 container duration can be driven by the audio stream even when the video
    stream silently terminates early. That exact failure mode looks like a valid
    60-second file to a media player while the picture is black/missing after the
    first few seconds.
    """
    out = {"format": None, "video": None, "audio": None}
    if not path or not os.path.isfile(path) or os.path.getsize(path) < 1024:
        return out
    try:
        pr = subprocess.run([
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration:stream=codec_type,duration",
            "-of", "json", path
        ], capture_output=True, text=True, timeout=60)
        data = json.loads(pr.stdout or "{}") if pr.returncode == 0 else {}
        try:
            v = float((data.get("format") or {}).get("duration"))
            if math.isfinite(v) and v > 0:
                out["format"] = v
        except Exception:
            pass
        for st in data.get("streams") or []:
            kind = str(st.get("codec_type") or "")
            if kind not in ("video", "audio"):
                continue
            try:
                v = float(st.get("duration"))
            except Exception:
                continue
            if math.isfinite(v) and v > 0:
                cur = out.get(kind)
                if cur is None or v > cur:
                    out[kind] = v
    except Exception:
        pass
    return out


def _black_duration_ratio(path: str, pixel_threshold: float = 0.02,
                          expected_duration: float | None = None) -> float | None:
    """Return effective black fraction of the *expected visual timeline*.

    v5.3.1 divided black duration by MP4 container duration. If audio was 56s but
    a broken xfade video stream ended at 28s, a 24s black picture looked like only
    43% black and escaped the 75% guard. We now use the real video-stream duration
    and count a missing video tail as black when ``expected_duration`` is known.
    """
    if not path or not os.path.isfile(path) or os.path.getsize(path) < 1024:
        return None
    try:
        pr = subprocess.run([
            ffmpeg_exe(), "-hide_banner", "-i", path,
            "-vf", f"blackdetect=d=0.35:pix_th={pixel_threshold}",
            "-an", "-f", "null", "-"
        ], capture_output=True, text=True, timeout=300)
        if pr.returncode != 0:
            return None
        text = (pr.stderr or "") + "\n" + (pr.stdout or "")
        import re
        black_seconds = 0.0
        for m in re.finditer(r"black_start:([0-9.eE+-]+)\s+black_end:([0-9.eE+-]+)\s+black_duration:([0-9.eE+-]+)", text):
            try:
                black_seconds += max(0.0, float(m.group(3)))
            except Exception:
                pass
        durs = _probe_av_durations(path)
        video_dur = durs.get("video") or durs.get("format")
        if not video_dur or not math.isfinite(float(video_dur)) or float(video_dur) <= 0:
            return None
        denom = float(video_dur)
        if expected_duration is not None:
            try:
                exp = float(expected_duration)
            except Exception:
                exp = 0.0
            if math.isfinite(exp) and exp > 0:
                # Any tail where audio/timeline continues but the video stream has
                # already ended is visually missing and must count as black.
                black_seconds += max(0.0, exp - float(video_dur))
                denom = exp
        return max(0.0, min(1.0, black_seconds / denom))
    except Exception:
        return None


def _video_coverage_ratio(path: str, expected_duration: float) -> float | None:
    """Fraction of expected timeline covered by the actual video stream."""
    try:
        exp = float(expected_duration)
    except Exception:
        return None
    if not math.isfinite(exp) or exp <= 0:
        return None
    d = _probe_av_durations(path).get("video")
    if d is None:
        return None
    return max(0.0, min(2.0, float(d) / exp))


def _freeze_metrics(path: str, expected_duration: float | None = None) -> dict:
    """Measure frozen picture time; a valid video stream can still be stuck."""
    out = {"ratio": None, "longest": None}
    if not path or not os.path.isfile(path) or os.path.getsize(path) < 1024:
        return out
    try:
        cp = subprocess.run([
            ffmpeg_exe(), "-hide_banner", "-i", path,
            "-vf", "freezedetect=n=-45dB:d=1.0", "-an", "-f", "null", "-"
        ], capture_output=True, text=True, timeout=900)
        report = (cp.stdout or "") + "\n" + (cp.stderr or "")
        if cp.returncode != 0:
            return out
        durations = [float(x) for x in re.findall(
            r"freeze_duration:\s*([0-9.eE+-]+)", report)]
        total = float(expected_duration or 0) or float(
            _probe_av_durations(path).get("video") or 0)
        # A freeze continuing to EOF has no freeze_duration event.
        starts = re.findall(r"freeze_start:\s*([0-9.eE+-]+)", report)
        ends = re.findall(r"freeze_end:\s*([0-9.eE+-]+)", report)
        if len(starts) > len(ends) and total > 0:
            durations.append(max(0.0, total - float(starts[-1])))
        if total > 0:
            out["ratio"] = min(1.0, sum(durations) / total)
        out["longest"] = max(durations) if durations else 0.0
    except Exception:
        pass
    return out


def _run_ffmpeg_progress(cmd: list, total: float, progress_cb=None,
                         timeout: int = 3600):
    """Run FFmpeg while parsing its machine-readable timeline progress."""
    # Preserve the simple execution path for library callers that do not need
    # progress (and for older integrations that monkeypatch subprocess.run).
    if progress_cb is None:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    run_cmd = list(cmd[:-1]) + ["-progress", "pipe:1", "-nostats", cmd[-1]]
    last = -1
    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as err:
        proc = subprocess.Popen(run_cmd, stdout=subprocess.PIPE, stderr=err,
                                text=True, bufsize=1)
        events: queue.Queue = queue.Queue()

        def _read_stdout():
            try:
                for line in iter(proc.stdout.readline, ""):
                    events.put(line)
            finally:
                events.put(None)

        reader = threading.Thread(target=_read_stdout, daemon=True)
        reader.start()
        started = time.monotonic()
        last_update = started
        last_motion = started
        last_seconds = -1.0
        stall_timeout = max(30, int(os.getenv("AUTOVIDEO_ENCODER_STALL_SECONDS", "180")))
        try:
            while True:
                elapsed = time.monotonic() - started
                if elapsed > timeout:
                    raise subprocess.TimeoutExpired(run_cmd, timeout)
                if time.monotonic() - last_motion > stall_timeout:
                    raise RuntimeError(f"Encoder stalled: no output-time advance for {stall_timeout}s; stopped without restarting generation")
                if time.monotonic() - last_update >= 15:
                    progress_cb(max(0, last), f"encoder running; {int(elapsed)}s elapsed, "
                                f"{int(time.monotonic()-last_motion)}s since output advanced")
                    last_update = time.monotonic()
                try:
                    raw = events.get(timeout=5.0)
                except queue.Empty:
                    if progress_cb and time.monotonic() - last_update >= 15:
                        progress_cb(max(0, last),
                                    f"encoder active; waiting for next frame update ({int(elapsed)}s elapsed)")
                        last_update = time.monotonic()
                    if proc.poll() is not None:
                        break
                    continue
                if raw is None:
                    break
                key, _, value = raw.strip().partition("=")
                if key in ("out_time_ms", "out_time_us"):
                    try:
                        seconds = float(value) / 1_000_000.0
                        if seconds > last_seconds:
                            last_motion = time.monotonic()
                            last_seconds = seconds
                        pct = max(0, min(99, int(seconds * 100 / max(0.001, float(total)))))
                        if pct != last and progress_cb:
                            progress_cb(pct, f"{seconds:.1f}s / {float(total):.1f}s")
                            last_update = time.monotonic()
                        last = pct
                    except Exception:
                        pass
                elif key == "progress" and value == "end" and progress_cb:
                    progress_cb(100, f"{float(total):.1f}s encoded")
            proc.wait(timeout=max(1, timeout - (time.monotonic() - started)))
        except Exception:
            proc.kill()
            proc.wait()
            raise
        finally:
            if proc.stdout:
                proc.stdout.close()
        err.seek(0)
        return SimpleNamespace(returncode=proc.returncode, stderr=err.read(), stdout="")


def render_ffmpeg(segments, narration, out_path, render_dir: str = "render",
                  progress_cb=None, **kwargs) -> dict:
    """Render with FFmpeg and degrade only the fragile filter, not the whole edit.

    On some WSL installs libass/subtitles is present but crashes at runtime. v5.0
    then rebuilt the *entire* movie with MoviePy. v5.1 retries the exact FFmpeg
    timeline without ASS captions and returns a flag so the caller can add
    captions in a lightweight second pass.
    """
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    effective_kwargs = dict(kwargs)
    cmd, meta = build_ffmpeg_cmd(segments, narration, out_path, **effective_kwargs)
    r = _run_ffmpeg_progress(cmd, meta.get("total", 1), progress_cb)
    first_stderr = r.stderr or ""
    retried_software_encoder = False
    retried_without_fontsdir = False
    retried_without_loudnorm = False
    retried_without_ass = False
    ass_failure_tail = ""

    # FFmpeg can list NVENC/QSV/AMF even when the current machine/container has
    # no usable hardware device. Retry the exact graph with libx264 before
    # abandoning the primary renderer.
    if r.returncode != 0 and meta.get("encoder") not in (None, "libx264"):
        effective_kwargs["encoder"] = "libx264"
        cmd, meta = build_ffmpeg_cmd(segments, narration, out_path, **effective_kwargs)
        r = _run_ffmpeg_progress(cmd, meta.get("total", 1), progress_cb)
        retried_software_encoder = True

    if r.returncode != 0 and ":fontsdir=" in meta.get("filter_complex", ""):
        effective_kwargs["use_fontsdir"] = False
        cmd, meta = build_ffmpeg_cmd(segments, narration, out_path, **effective_kwargs)
        r = _run_ffmpeg_progress(cmd, meta.get("total", 1), progress_cb)
        retried_without_fontsdir = True

    err_lower = (r.stderr or "").lower()
    if r.returncode != 0 and (
            "nan/+-inf" in err_lower or "input contains (near) nan" in err_lower
            or "error submitting audio frame" in err_lower):
        effective_kwargs["use_loudnorm"] = False
        cmd, meta = build_ffmpeg_cmd(segments, narration, out_path, **effective_kwargs)
        r = _run_ffmpeg_progress(cmd, meta.get("total", 1), progress_cb)
        retried_without_loudnorm = True

    # Final primary-render rescue: if ASS/libass is the remaining failure, keep
    # FFmpeg for all video/audio/timeline work and omit only the subtitle filter.
    if r.returncode != 0 and kwargs.get("ass_path"):
        ass_failure_tail = (r.stderr or "")[-1800:]
        no_ass = dict(effective_kwargs)
        no_ass["ass_path"] = None
        cmd2, meta2 = build_ffmpeg_cmd(segments, narration, out_path, **no_ass)
        r2 = _run_ffmpeg_progress(cmd2, meta2.get("total", 1), progress_cb)
        if r2.returncode == 0:
            cmd, meta, r = cmd2, meta2, r2
            retried_without_ass = True
            # Preserve the original request state for the caller.
            meta["captions_requested"] = True
            meta["burn_captions"] = False
        else:
            # Keep the more useful final error from the caption-free attempt.
            cmd, meta, r = cmd2, meta2, r2

    # A successful FFmpeg exit is not sufficient: on some WSL/MP4 combinations
    # xfade can emit valid H.264 whose picture becomes black after the first
    # scene. Detect that exact failure mode and automatically rerender with the
    # safe hard-cut concat graph instead of shipping a blank video.
    output_black_ratio = None
    output_video_coverage = None
    output_freeze_ratio = None
    output_longest_freeze = None
    retried_safe_concat = False
    if r.returncode == 0:
        expected_total = float(meta.get("total") or 0)
        output_black_ratio = _black_duration_ratio(out_path, expected_duration=expected_total)
        output_video_coverage = _video_coverage_ratio(out_path, expected_total)
        freeze = _freeze_metrics(out_path, expected_total)
        output_freeze_ratio = freeze["ratio"]
        output_longest_freeze = freeze["longest"]
        visually_broken = (
            (output_black_ratio is not None and output_black_ratio >= MAX_BLACK_RATIO)
            or (output_video_coverage is not None and output_video_coverage < 0.95)
            or (output_freeze_ratio is not None and output_freeze_ratio >= MAX_FROZEN_RATIO)
            or (output_longest_freeze is not None and output_longest_freeze >= MAX_SINGLE_FREEZE_SECONDS)
        )
        if (visually_broken and len(segments) > 1
                and not effective_kwargs.get("safe_concat")):
            details = []
            if output_black_ratio is not None:
                details.append(f"black/missing={output_black_ratio:.0%}")
            if output_video_coverage is not None:
                details.append(f"video_coverage={output_video_coverage:.0%}")
            if output_freeze_ratio is not None:
                details.append(f"frozen={output_freeze_ratio:.0%}")
            if output_longest_freeze is not None:
                details.append(f"longest_freeze={output_longest_freeze:.1f}s")
            print("[Render] Primary FFmpeg output failed visual integrity QC "
                  f"({' '.join(details)}); rerendering with safe concat...")
            safe_kwargs = dict(effective_kwargs)
            safe_kwargs["safe_concat"] = True
            safe_kwargs["loop_short_segments"] = True
            # Keep captions/audio settings identical; only the visual transition
            # graph changes. Force software x264 for maximum compatibility. Use
            # the standard preset so a recovery pass remains bounded on WSL CPU.
            safe_kwargs["encoder"] = "libx264"
            safe_kwargs["quality"] = "standard"
            safe_out = out_path + ".safe.mp4"
            try:
                if os.path.exists(safe_out):
                    os.remove(safe_out)
            except Exception:
                pass
            cmd3, meta3 = build_ffmpeg_cmd(segments, narration, safe_out, **safe_kwargs)
            if progress_cb:
                progress_cb(0, "Primary visual QC failed; starting bounded safe recovery render")
            recovery_timeout = max(300, min(2400, int(float(meta3.get("total", 1)) * 6)))
            recovery_cb = None
            if progress_cb:
                recovery_cb = lambda pct, detail="": progress_cb(
                    pct, f"Safe recovery: {detail}")
            try:
                r3 = _run_ffmpeg_progress(
                    cmd3, meta3.get("total", 1), recovery_cb,
                    timeout=recovery_timeout)
            except subprocess.TimeoutExpired:
                r3 = SimpleNamespace(
                    returncode=124, stdout="",
                    stderr=(f"Safe recovery watchdog stopped FFmpeg after "
                            f"{recovery_timeout}s without completion"))
            safe_expected = float(meta3.get("total") or expected_total)
            safe_ratio = _black_duration_ratio(safe_out, expected_duration=safe_expected) if r3.returncode == 0 else None
            safe_coverage = _video_coverage_ratio(safe_out, safe_expected) if r3.returncode == 0 else None
            safe_freeze = (_freeze_metrics(safe_out, safe_expected) if r3.returncode == 0
                           else {"ratio": None, "longest": None})
            safe_ok = (
                r3.returncode == 0
                and (safe_ratio is None or safe_ratio < MAX_BLACK_RATIO)
                and (safe_coverage is None or safe_coverage >= 0.95)
                and (safe_freeze["ratio"] is None or safe_freeze["ratio"] < MAX_FROZEN_RATIO)
                and (safe_freeze["longest"] is None or safe_freeze["longest"] < MAX_SINGLE_FREEZE_SECONDS)
            )
            if safe_ok:
                os.replace(safe_out, out_path)
                cmd, meta, r = cmd3, meta3, r3
                effective_kwargs = safe_kwargs
                retried_safe_concat = True
                output_black_ratio = safe_ratio
                output_video_coverage = safe_coverage
                output_freeze_ratio = safe_freeze["ratio"]
                output_longest_freeze = safe_freeze["longest"]
                print("[Render] Safe-concat recovery passed visual integrity QC; using repaired final video.")
            else:
                try:
                    if os.path.exists(safe_out):
                        os.remove(safe_out)
                except Exception:
                    pass

    with open(os.path.join(os.path.dirname(os.path.abspath(out_path)), "render_settings.json"),
              "w", encoding="utf-8") as f:
        json.dump({**meta, "cmd": " ".join(cmd)[:5000], "returncode": r.returncode,
                   "retried_software_encoder": retried_software_encoder,
                   "retried_without_fontsdir": retried_without_fontsdir,
                   "retried_without_loudnorm": retried_without_loudnorm,
                   "retried_without_ass": retried_without_ass,
                   "retried_safe_concat": retried_safe_concat,
                   "output_black_ratio": output_black_ratio,
                   "output_video_coverage": output_video_coverage,
                   "output_freeze_ratio": output_freeze_ratio,
                   "output_longest_freeze": output_longest_freeze,
                   "ass_failure_tail": ass_failure_tail,
                   "first_stderr_tail": first_stderr[-1200:],
                   "stderr_tail": (r.stderr or "")[-1800:]}, f, indent=2)
    if r.returncode != 0:
        raise RuntimeError(f"FFmpeg render failed: {(r.stderr or '')[-900:]}")
    if output_black_ratio is not None and output_black_ratio >= MAX_BLACK_RATIO:
        raise RuntimeError(
            f"FFmpeg render completed but visual QC detected {output_black_ratio:.0%} mostly-black/missing visual duration; "
            "refusing to publish a blank render")
    if output_video_coverage is not None and output_video_coverage < 0.95:
        raise RuntimeError(
            f"FFmpeg render completed but video stream covers only {output_video_coverage:.0%} of the expected timeline; "
            "refusing to publish a truncated/blank render")
    if ((output_freeze_ratio is not None and output_freeze_ratio >= MAX_FROZEN_RATIO)
            or (output_longest_freeze is not None and output_longest_freeze >= MAX_SINGLE_FREEZE_SECONDS)):
        raise RuntimeError(
            f"FFmpeg render completed but motion QC detected frozen={output_freeze_ratio or 0:.0%}, "
            f"longest freeze={output_longest_freeze or 0:.1f}s; refusing to publish a stuck render")
    return {"video": out_path, **meta,
            "caption_fallback_required": bool(meta.get("captions_requested") and not meta.get("burn_captions")),
            "retried_software_encoder": retried_software_encoder,
            "retried_without_fontsdir": retried_without_fontsdir,
            "retried_without_loudnorm": retried_without_loudnorm,
            "retried_without_ass": retried_without_ass,
            "retried_safe_concat": retried_safe_concat,
            "output_black_ratio": output_black_ratio,
            "output_video_coverage": output_video_coverage,
            "output_freeze_ratio": output_freeze_ratio,
            "output_longest_freeze": output_longest_freeze}
