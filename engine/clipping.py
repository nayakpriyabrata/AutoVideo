"""Rights-aware long-video to short-clips workflow.

The scorer is deliberately explainable: it combines sentence completeness,
hook/question/action language, numbers, speech density and spacing.  Whisper (or
Groq Whisper when configured) supplies word timings; FFmpeg performs all cuts,
vertical reframing and caption burns locally. For public YouTube URLs, Gemini
can propose semantic timestamps; deterministic transcript scoring verifies and
reranks them before any clip is rendered.
"""
from __future__ import annotations

import json
import importlib.util
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import hashlib
from pathlib import Path

import requests


HOOK_WORDS = {
    "secret", "mistake", "never", "why", "how", "best", "worst", "truth",
    "important", "remember", "imagine", "instead", "because", "future",
    "change", "unlock", "discover", "surprising", "problem", "solution",
}
ACTION_WORDS = {
    "start", "stop", "build", "use", "try", "choose", "avoid", "focus",
    "learn", "create", "do", "make", "write", "practice", "protect",
}

SOURCE_RIGHTS = {
    "unknown",
    "own_content",
    "written_permission",
    "licensed_content",
    "creative_commons",
    "public_domain",
    "commentary_or_review",
    "private_draft_only",
}
MUSIC_LICENSES = {
    "none", "own", "youtube_audio_library", "royalty_free_licensed",
    "creative_commons",
}


def _is_url(source: str) -> bool:
    return bool(re.match(r"^https?://", str(source or ""), re.I))


def _rights_policy(source: str, source_rights: str = "unknown",
                   rights_confirmed: bool = False) -> dict:
    """Validate an explicit source-rights declaration and return report metadata.

    ``--rights-confirmed`` remains backward compatible, but new runs should use
    the more specific ``--source-rights`` option. This is a workflow guard, not
    a legal determination.
    """
    rights = str(source_rights or "unknown").strip().lower()
    if rights not in SOURCE_RIGHTS:
        raise RuntimeError(
            "Invalid source rights declaration. Choose one of: " +
            ", ".join(sorted(SOURCE_RIGHTS - {"unknown"})))
    if rights_confirmed and rights == "unknown":
        rights = "written_permission_legacy"
    if _is_url(source) and rights == "unknown":
        raise RuntimeError(
            "URL clipping requires --source-rights (or legacy --rights-confirmed). "
            "Only download videos you own, are licensed/allowed to reuse, or are "
            "using under a valid applicable exception.")
    warnings = []
    public_upload = rights in {
        "own_content", "written_permission", "written_permission_legacy",
        "licensed_content", "creative_commons", "public_domain",
    }
    if rights == "commentary_or_review":
        warnings.append(
            "Commentary/review is context-dependent: minor edits, captions, music, "
            "crop or motion alone do not make a clip transformative.")
    elif rights == "private_draft_only":
        warnings.append("Private-draft mode is not cleared for public upload.")
    elif rights == "creative_commons":
        warnings.append("Preserve the exact licence terms and required attribution.")
    return {
        "declaration": rights,
        "public_upload_cleared_by_declaration": public_upload,
        "warnings": warnings,
        "notice": "AutoVideoAI records your declaration but does not grant or verify legal rights.",
    }


def _run(cmd: list[str], timeout: int = 3600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _duration(path: str) -> float:
    p = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "default=nw=1:nk=1", path], timeout=60)
    try:
        d = float((p.stdout or "").strip())
    except Exception as e:
        raise RuntimeError(f"Cannot read video duration: {path}") from e
    if not math.isfinite(d) or d <= 0:
        raise RuntimeError(f"Invalid video duration: {path}")
    return d


def resolve_input(source: str, work_dir: str, rights_confirmed: bool = False,
                  source_rights: str = "unknown") -> str:
    if os.path.isfile(source):
        return os.path.abspath(source)
    if not _is_url(source):
        raise FileNotFoundError(source)
    _rights_policy(source, source_rights, rights_confirmed)
    exe = shutil.which("yt-dlp")
    if exe:
        downloader = [exe]
    elif importlib.util.find_spec("yt_dlp") is not None:
        # `pip install --user` commonly puts the executable in ~/.local/bin,
        # which is not on PATH in WSL. The module entry point is equivalent and
        # works with the same interpreter that launched AutoVideoAI.
        downloader = [sys.executable, "-m", "yt_dlp"]
    else:
        raise RuntimeError("yt-dlp is required for URL input: pip install yt-dlp")
    out = os.path.join(work_dir, "source.%(ext)s")
    # Prefer AVC/H.264 so OpenCV/WSL does not depend on hardware AV1 decoding.
    # The final fallbacks still accept any playable format when AVC is absent.
    fmt = ("bv*[vcodec^=avc1][ext=mp4]+ba[ext=m4a]/"
           "bv*[vcodec^=avc1]+ba/b[ext=mp4]/b")
    p = _run(downloader + ["--no-playlist", "-f", fmt, "--merge-output-format", "mp4",
              "-o", out, source], timeout=7200)
    if p.returncode != 0:
        raise RuntimeError("Video download failed: " + (p.stderr or p.stdout or "")[-700:])
    files = sorted(Path(work_dir).glob("source.*"), key=lambda q: q.stat().st_mtime, reverse=True)
    if not files:
        raise RuntimeError("Downloader completed but no local source file was found")
    return str(files[0])


def _sentences(words: list[dict]) -> list[dict]:
    out, cur = [], []
    for w in words:
        try:
            item = {"word": str(w["word"]).strip(), "start": float(w["start"]),
                    "end": float(w["end"])}
        except Exception:
            continue
        cur.append(item)
        if re.search(r"[.!?]$", item["word"]) or len(cur) >= 30:
            out.append({"start": cur[0]["start"], "end": cur[-1]["end"],
                        "words": cur, "text": " ".join(x["word"] for x in cur)})
            cur = []
    if cur:
        out.append({"start": cur[0]["start"], "end": cur[-1]["end"],
                    "words": cur, "text": " ".join(x["word"] for x in cur)})
    return out


def _score_window(items: list[dict], start: float, end: float) -> tuple[float, list[str]]:
    text = " ".join(x["text"] for x in items)
    toks = set(re.findall(r"[a-z']+", text.lower()))
    reasons, score = [], 0.0
    hooks = len(toks & HOOK_WORDS)
    actions = len(toks & ACTION_WORDS)
    if hooks:
        score += min(18, hooks * 4); reasons.append(f"{hooks} hook terms")
    if actions:
        score += min(12, actions * 3); reasons.append(f"{actions} action terms")
    if "?" in text:
        score += 8; reasons.append("question/hook")
    if re.search(r"\b\d+(?:\.\d+)?\b|\b(first|second|third|three|five|ten)\b", text.lower()):
        score += 6; reasons.append("specific number/list")
    duration = max(0.1, end - start)
    word_count = sum(len(x["words"]) for x in items)
    density = word_count / duration
    score += min(18, density * 8)
    if items and re.search(r"[.!?]$", items[-1]["text"]):
        score += 8; reasons.append("complete ending")
    if 25 <= duration <= 55:
        score += 8
    opening = (items[0]["text"] if items else "").strip().lower()
    if re.match(r"^(and|but|so|because|then|it|this|that|they|he|she)\b", opening):
        score -= 10; reasons.append("context-dependent opening")
    else:
        score += 8; reasons.append("standalone opening")
    if any(x in text.lower() for x in ("for example", "here's how", "the key is", "you can")):
        score += 7; reasons.append("clear takeaway")
    return round(score, 2), reasons


def _short_title(text: str) -> str:
    from .editorial_text import headline
    return headline(text)


def _headline_filename(title: str, index: int, used: set[str] | None = None) -> str:
    """Create a portable, meaningful MP4 name from the editorial headline."""
    ascii_title = unicodedata.normalize("NFKD", str(title or "")).encode(
        "ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")
    slug = slug[:72].rstrip("-") or f"highlight-{index:02d}"
    used = used if used is not None else set()
    candidate = slug
    suffix = 2
    while candidate in used:
        tail = f"-{suffix}"
        candidate = slug[:72-len(tail)].rstrip("-") + tail
        suffix += 1
    used.add(candidate)
    return candidate + ".mp4"


def _clip_qc_report(path: str, expected_duration: float, editorial_score: float,
                    caption_words: int) -> dict:
    """Strict post-render gates plus an explainable Opus-style quality score.

    The score estimates editorial/technical readiness; it is deliberately not
    labelled a virality prediction. Hard stream/decode failures block delivery.
    """
    probe = _run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration:stream=codec_type,codec_name,width,height,duration",
        "-of", "json", path,
    ], timeout=60)
    try:
        data = json.loads(probe.stdout or "{}") if probe.returncode == 0 else {}
    except Exception:
        data = {}
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
    try:
        actual = float((data.get("format") or {}).get("duration") or 0)
    except Exception:
        actual = 0.0
    decode = _run(["ffmpeg", "-v", "error", "-i", path, "-f", "null", "-"],
                  timeout=max(120, min(900, int(max(1.0, expected_duration) * 5))))
    decode_lines = [x.strip() for x in (decode.stderr or "").splitlines() if x.strip()]
    try:
        from .render.ffmpeg_renderer import _black_duration_ratio, _freeze_metrics
        black_ratio = _black_duration_ratio(path, expected_duration=expected_duration)
        freeze = _freeze_metrics(path, expected_duration)
    except Exception:
        black_ratio = None
        freeze = {"ratio": None, "longest": None}

    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    duration_delta = abs(actual - float(expected_duration)) if actual else float(expected_duration)
    checks = {
        "video_stream": bool(video),
        "audio_stream": bool(audio),
        "vertical_1080x1920": width == 1080 and height == 1920,
        "duration_aligned": duration_delta <= max(1.0, float(expected_duration) * 0.04),
        "decodes_cleanly": decode.returncode == 0 and not decode_lines,
        "black_frames_ok": black_ratio is not None and black_ratio < 0.08,
        "motion_ok": (freeze.get("longest") is not None and freeze.get("longest") < 8.0),
        "captions_present": int(caption_words) >= 5,
    }
    technical_score = 100.0
    penalties = {
        "video_stream": 45, "audio_stream": 30, "vertical_1080x1920": 16,
        "duration_aligned": 18, "decodes_cleanly": 35, "black_frames_ok": 30,
        "motion_ok": 20, "captions_present": 10,
    }
    for name, ok in checks.items():
        if not ok:
            technical_score -= penalties[name]
    technical_score = max(0.0, technical_score)
    editorial = max(0.0, min(100.0, float(editorial_score or 0)))
    quality_score = round(editorial * 0.58 + technical_score * 0.42)
    blocking = [name for name in (
        "video_stream", "audio_stream", "duration_aligned", "decodes_cleanly",
        "black_frames_ok", "motion_ok") if not checks[name]]
    review = [name for name, ok in checks.items() if not ok and name not in blocking]
    decision = "BLOCK" if blocking else ("REVIEW" if review else "PASS")
    return {
        "decision": decision, "ready_to_publish": False,
        "technical_passed": decision == "PASS",
        "editorial_review_required": True,
        "quality_score": quality_score,
        "score_label": "editorial + technical readiness (not a virality guarantee)",
        "editorial_score": round(editorial, 1),
        "technical_score": round(technical_score, 1),
        "checks": checks, "blocking_issues": blocking, "review_issues": review,
        "media": {"duration": round(actual, 3), "expected_duration": round(float(expected_duration), 3),
                  "width": width, "height": height,
                  "video_codec": video.get("codec_name"), "audio_codec": audio.get("codec_name"),
                  "black_ratio": black_ratio, "freeze_ratio": freeze.get("ratio"),
                  "longest_freeze": freeze.get("longest"),
                  "decode_errors": decode_lines[:12]},
    }


def _timestamp_seconds(value) -> float | None:
    """Parse Gemini timestamps expressed as seconds, MM:SS or HH:MM:SS."""
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return max(0.0, float(value))
    raw = str(value or "").strip().lower().removesuffix("s")
    if not raw:
        return None
    try:
        if ":" not in raw:
            return max(0.0, float(raw))
        parts = [float(x) for x in raw.split(":")]
        if len(parts) == 2:
            return max(0.0, parts[0] * 60 + parts[1])
        if len(parts) == 3:
            return max(0.0, parts[0] * 3600 + parts[1] * 60 + parts[2])
    except Exception:
        return None
    return None


def _gemini_youtube_candidates(source_url: str, total: float, count: int,
                               min_seconds: float, max_seconds: float,
                               model: str | None = None, progress_cb=None) -> list[dict]:
    """Ask Gemini's documented YouTube video input for timestamped candidates."""
    key = str(os.getenv("GEMINI_API_KEY", "") or "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    model = str(model or os.getenv("GEMINI_CLIP_MODEL") or os.getenv("GEMINI_SCRIPT_MODEL") or "").strip()
    if not model:
        raise RuntimeError("Select --gemini-model or GEMINI_CLIP_MODEL from python3 -m engine.providers.gemini_models; no model ID is assumed")
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', model):
        raise ValueError('Invalid Gemini model ID')
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    wanted = max(6, min(20, int(count) * 4))
    prompt = f"""
Act as a rigorous short-form video editor. Analyse both the spoken content and
visual stream of this entire video. Propose {wanted} candidate clips for a
vertical educational/social reel. Each must be {min_seconds:.0f}-{max_seconds:.0f}
seconds, understandable without earlier context, begin with an immediate spoken
hook, contain one coherent idea and payoff, and finish on a complete sentence.
Reject greetings, sponsor messages, housekeeping, repetition, unfinished setup,
copyright/music-only moments, and candidates whose opening pronoun depends on an
earlier statement. Scores are editorial estimates, never promises of virality.
Video duration is approximately {total:.1f} seconds.

Return ONLY valid JSON:
{{"candidates":[{{"start":"MM:SS","end":"MM:SS","score":0,
"title":"short headline","hook":"opening idea","payoff":"viewer value",
"reason":"why this is self-contained","requires_context":false}}]}}
""".strip()
    payload = {
        "contents": [{"role": "user", "parts": [
            {"file_data": {"file_uri": source_url}},
            {"text": prompt},
        ]}],
        "generationConfig": {
            "temperature": 0.25,
            "responseMimeType": "application/json",
            "maxOutputTokens": 4096,
        },
    }
    response = None
    retry_delays = [2, 5, 10]
    for attempt in range(1, len(retry_delays) + 2):
        try:
            response = requests.post(
                url, headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json=payload, timeout=int(os.getenv("GEMINI_CLIP_TIMEOUT", "60")))
            response.raise_for_status()
            break
        except requests.RequestException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            transient = status in (429, 500, 502, 503, 504) or status is None
            if not transient or attempt > len(retry_delays):
                raise
            delay = retry_delays[attempt - 1]
            message = (f"Gemini API attempt {attempt} returned HTTP {status or 'network error'}; "
                       f"retrying in {delay}s")
            if progress_cb:
                progress_cb(message)
            else:
                print("[Gemini API] " + message)
            time.sleep(delay)
    if response is None:
        raise RuntimeError("Gemini API returned no response")
    data = response.json()
    parts = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
    text = "\n".join(str(p.get("text") or "") for p in parts
                     if p.get("text") and not p.get("thought"))
    return _parse_gemini_clip_candidates(text, total, min_seconds, max_seconds)


def _parse_gemini_clip_candidates(text: str, total: float,
                                  min_seconds: float, max_seconds: float) -> list[dict]:
    from .planning.script_engine import _extract_json
    parsed = _extract_json(text) or {}
    candidates = []
    for item in parsed.get("candidates") or []:
        if not isinstance(item, dict):
            continue
        start = _timestamp_seconds(item.get("start"))
        end = _timestamp_seconds(item.get("end"))
        if start is None or end is None:
            continue
        start, end = max(0.0, start), min(float(total), end)
        duration = end - start
        if duration < max(8.0, min_seconds * 0.72) or duration > max_seconds * 1.28:
            continue
        if item.get("requires_context") is True:
            continue
        try:
            gemini_score = max(0.0, min(100.0, float(item.get("score", 0))))
        except Exception:
            gemini_score = 0.0
        candidates.append({
            "start": round(start, 3), "end": round(end, 3),
            "duration": round(duration, 3), "gemini_score": gemini_score,
            "title": str(item.get("title") or "")[:100],
            "hook": str(item.get("hook") or "")[:240],
            "payoff": str(item.get("payoff") or "")[:240],
            "editorial_reason": str(item.get("reason") or "")[:320],
        })
    if not candidates:
        raise RuntimeError("Gemini returned no valid timestamp candidates")
    return candidates


def _gemini_web_youtube_candidates(source_url: str, total: float, count: int,
                                   min_seconds: float, max_seconds: float,
                                   cleanup: str = "delete-after-read") -> list[dict]:
    """Use the signed-in visible Gemini UI when the API is unavailable.

    Gemini Web access to a public YouTube URL depends on the user's account and
    current Gemini UI capabilities. Any failure returns to the deterministic
    Groq/local path rather than aborting the clip job.
    """
    from .providers.gemini_web import gemini_web_generate

    wanted = max(6, min(20, int(count) * 4))
    system = (
        "You are a rigorous short-form video editor. Analyse the linked public "
        "YouTube video's spoken and visual content. Return ONLY valid JSON and "
        "never claim that an editorial score guarantees virality.")
    user = f"""
Public YouTube video: {source_url}
Approximate duration: {total:.1f} seconds.

Propose {wanted} standalone vertical-reel candidates, each {min_seconds:.0f}-
{max_seconds:.0f} seconds. Every candidate must begin with an immediate spoken
hook, contain one coherent idea and payoff, and end on a complete sentence.
Reject greetings, sponsor messages, housekeeping, repetition, music-only
moments, unfinished setup, and openings that depend on earlier context.

Return exactly:
{{"candidates":[{{"start":"MM:SS","end":"MM:SS","score":0,
"title":"short headline","hook":"opening idea","payoff":"viewer value",
"reason":"why this is self-contained","requires_context":false}}]}}
""".strip()
    old_cleanup = os.environ.get("AUTOVIDEO_GEMINI_CHAT_CLEANUP")
    os.environ["AUTOVIDEO_GEMINI_CHAT_CLEANUP"] = cleanup
    try:
        raw = gemini_web_generate(system, user, model="gemini-web")
    finally:
        if old_cleanup is None:
            os.environ.pop("AUTOVIDEO_GEMINI_CHAT_CLEANUP", None)
        else:
            os.environ["AUTOVIDEO_GEMINI_CHAT_CLEANUP"] = old_cleanup
    return _parse_gemini_clip_candidates(raw, total, min_seconds, max_seconds)


def _transcript_for_window(words: list[dict], start: float, end: float) -> str:
    return " ".join(str(w.get("word") or "").strip() for w in words
                    if float(w.get("end", 0)) > start and float(w.get("start", 0)) < end).strip()


def _verify_gemini_candidates(proposals: list[dict], words: list[dict], total: float,
                              min_seconds: float, max_seconds: float) -> list[dict]:
    """Snap proposals to transcript sentence boundaries and compute hybrid score."""
    sentences = _sentences(words)
    verified = []
    for proposal in proposals:
        start, end = float(proposal["start"]), float(proposal["end"])
        selected = [s for s in sentences if s["end"] > start and s["start"] < end]
        if not selected:
            continue
        # Keep Gemini's semantic region but use complete local sentence edges.
        snapped_start = max(0.0, selected[0]["start"] - 0.25)
        snapped_end = min(total, selected[-1]["end"] + 0.25)
        duration = snapped_end - snapped_start
        if duration > max_seconds:
            # Drop trailing sentences until the clip fits; never hard-cut words.
            while len(selected) > 1 and selected[-1]["end"] - snapped_start > max_seconds:
                selected.pop()
            snapped_end = min(total, selected[-1]["end"] + 0.25)
            duration = snapped_end - snapped_start
        if duration < min_seconds or duration > max_seconds:
            continue
        local_score, reasons = _score_window(selected, snapped_start, snapped_end)
        gemini_score = float(proposal.get("gemini_score", 0))
        hybrid = round(gemini_score * 0.62 + max(0.0, min(100.0, local_score)) * 0.38, 2)
        item = dict(proposal)
        item.update({
            "start": round(snapped_start, 3), "end": round(snapped_end, 3),
            "duration": round(duration, 3), "local_score": local_score,
            "score": hybrid, "ai_score": hybrid, "reasons": reasons,
            "text": " ".join(s["text"] for s in selected),
            "ranking": "gemini-hybrid",
        })
        item["title"] = item.get("title") or _short_title(item["text"])
        verified.append(item)
    return sorted(verified, key=lambda x: x.get("score", 0), reverse=True)


def _choose_non_overlapping(candidates: list[dict], count: int) -> list[dict]:
    chosen = []
    for candidate in candidates:
        if any(max(0.0, min(candidate["end"], old["end"]) -
                   max(candidate["start"], old["start"])) > 0 for old in chosen):
            continue
        chosen.append(dict(candidate))
        if len(chosen) >= max(1, count):
            break
    return sorted(chosen, key=lambda x: x["start"])


def _groq_rerank(candidates: list[dict], count: int) -> list[dict] | None:
    """Use the configured Groq chat model as an editorial judge, with local fallback."""
    if not os.getenv("GROQ_API_KEY") or not candidates:
        return None
    try:
        from .planning.script_engine import _call_provider, _extract_json
        rows = [{"id": i, "start": c["start"], "end": c["end"],
                 "transcript": c["text"][:900]} for i, c in enumerate(candidates)]
        system = (
            "You are a short-form video editor. Select standalone moments that need no prior context. "
            "Reward an immediate spoken hook, one coherent idea, a useful or surprising payoff, emotional "
            "clarity, and a clean ending. Reject greetings, housekeeping, unfinished setup, repetition, "
            "and clips that begin with pronouns or conjunctions referring backward. Return only JSON.")
        user = (
            f"Choose up to {max(1, count)} non-overlapping highlights from these candidates. "
            "Return {\"selections\":[{\"id\":0,\"score\":95,\"title\":\"short headline\","
            "\"reason\":\"why it works\"}]}. Candidates:\n" + json.dumps(rows, ensure_ascii=False))
        raw = _call_provider("groq", os.getenv("GROQ_SCRIPT_MODEL", "openai/gpt-oss-120b"),
                             system, user)
        data = _extract_json(raw) or {}
        ranked = []
        for item in data.get("selections") or []:
            idx = int(item.get("id", -1))
            if 0 <= idx < len(candidates):
                c = dict(candidates[idx])
                c["ai_score"] = float(item.get("score", c["score"]))
                c["title"] = str(item.get("title") or _short_title(c["text"]))[:100]
                c["editorial_reason"] = str(item.get("reason") or "")[:240]
                c["ranking"] = "groq-editorial"
                ranked.append(c)
        return sorted(ranked, key=lambda x: x.get("ai_score", 0), reverse=True) or None
    except Exception:
        return None


def rank_highlights(words: list[dict], total: float, count: int = 3,
                    min_seconds: float = 25, max_seconds: float = 55,
                    ranking_provider: str = "auto") -> list[dict]:
    sentences = _sentences(words)
    candidates = []
    for i in range(len(sentences)):
        start = max(0.0, sentences[i]["start"] - 0.25)
        group = []
        for j in range(i, len(sentences)):
            group.append(sentences[j])
            end = min(total, sentences[j]["end"] + 0.25)
            dur = end - start
            if min_seconds <= dur <= max_seconds:
                score, reasons = _score_window(group, start, end)
                candidates.append({"start": round(start, 3), "end": round(end, 3),
                                   "duration": round(dur, 3), "score": score,
                                   "text": " ".join(x["text"] for x in group),
                                   "reasons": reasons})
            if dur >= max_seconds:
                break
    candidates.sort(key=lambda x: x["score"], reverse=True)
    pool = candidates
    if ranking_provider in ("auto", "groq"):
        # Send only the strongest diverse-enough local candidates to control
        # latency/token use. Explicit groq still falls back safely if unavailable.
        reranked = _groq_rerank(candidates[:max(12, count * 8)], count)
        if reranked:
            pool = reranked + [c for c in candidates if c not in reranked]
    for candidate in pool:
        candidate.setdefault("title", _short_title(candidate["text"]))
        candidate.setdefault("ranking", "local-editorial")
    return _choose_non_overlapping(pool, count)


def _face_crop_x(path: str, start: float, duration: float) -> float:
    """Return normalized horizontal face center, or 0.5 without a detector hit."""
    try:
        import cv2
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        centers = []
        # FFmpeg has reliable software AV1/VP9 decoders; OpenCV in WSL often
        # tries unavailable hardware acceleration and emits Missing Sequence
        # Header errors. Extract nine small analysis frames with FFmpeg instead.
        with tempfile.TemporaryDirectory(prefix="autovideo_faces_") as td:
            rate = 9.0 / max(0.1, duration)
            pattern = os.path.join(td, "frame_%02d.jpg")
            cp = _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(start),
                       "-t", str(duration), "-i", path, "-vf",
                       f"fps={rate:.6f},scale=640:-2", "-frames:v", "9", pattern], timeout=180)
            frames = sorted(Path(td).glob("frame_*.jpg")) if cp.returncode == 0 else []
            for fp in frames:
                frame = cv2.imread(str(fp))
                if frame is None:
                    continue
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = cascade.detectMultiScale(gray, 1.15, 5, minSize=(35, 35))
                if len(faces):
                    x, y, w, h = max(faces, key=lambda q: q[2] * q[3])
                    centers.append((x + w / 2) / frame.shape[1])
        if centers:
            centers.sort()
            return max(0.15, min(0.85, centers[len(centers)//2]))
    except Exception:
        pass
    return 0.5


def _transcribe_in_chunks(local: str, work: str, total: float,
                          provider: str, emit, language: str = 'en') -> list[dict]:
    """Transcribe compact audio chunks and restore source-relative timestamps.

    Sending a long MP4 directly can exceed Groq's multipart request limit even
    when its audio track is small. Five-minute mono 16 kHz/32 kbps MP3 chunks
    stay tiny, upload quickly and also avoid decoding video in the API request.
    """
    from .captions import get_word_timestamps

    chunk_seconds = 300.0
    count = max(1, int(math.ceil(total / chunk_seconds)))
    combined: list[dict] = []
    for i in range(count):
        offset = i * chunk_seconds
        duration = min(chunk_seconds, max(0.0, total - offset))
        if duration <= 0.05:
            continue
        audio = os.path.join(work, f"speech_{i+1:03d}.mp3")
        extract = _run([
            "ffmpeg", "-y", "-ss", str(offset), "-t", str(duration),
            "-i", local, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k", audio,
        ], timeout=max(300, int(duration * 3)))
        if extract.returncode != 0 or not os.path.isfile(audio) or os.path.getsize(audio) < 512:
            raise RuntimeError("Could not extract speech audio: " + (extract.stderr or "")[-500:])
        emit(f"Transcribing speech chunk {i+1}/{count}", 18 + int(6 * i / count))
        try:
            words = get_word_timestamps(
                audio, provider=provider, align_script=False, force=True, language=language) or []
        except Exception as exc:
            msg = str(exc)
            if "tokenizers" in msg and "Tokenizer" in msg:
                raise RuntimeError(
                    "Local faster-whisper has a broken tokenizers installation. "
                    "Use --caption-provider groq, or reinstall tokenizers and faster-whisper. "
                    f"Original error: {msg[:220]}") from exc
            raise
        for w in words:
            try:
                start = max(0.0, float(w.get("start", 0))) + offset
                end = max(float(w.get("end", w.get("start", 0))),
                          float(w.get("start", 0)) + 0.02) + offset
            except Exception:
                continue
            combined.append({"word": str(w.get("word", "")).strip(),
                             "start": round(start, 3), "end": round(min(total, end), 3)})
    return [w for w in combined if w["word"]]


def framing_filter(mode, face_x=.5):
    if mode == "fit":
        return ("scale=1080:1920:force_original_aspect_ratio=decrease:force_divisible_by=2,"
                "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0x18202b,setsar=1")
    if mode != "face-crop":
        raise ValueError("framing must be fit or face-crop")
    return ("crop='min(iw,ih*9/16)':ih:"
            f"'min(max(0,iw*{face_x:.5f}-min(iw,ih*9/16)/2),iw-min(iw,ih*9/16))':0,"
            "scale=1080:1920:flags=lanczos,setsar=1")


def soft_music_filter(duration, volume=.08):
    """Keep source speech at unity gain; stereo, gentle bed and sidechain ducking."""
    if type(volume) not in (int,float) or not math.isfinite(volume) or not 0 <= volume <= .35:
        raise ValueError('Soft music gain must be finite 0..0.35')
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Invalid clip audio duration')
    end=duration+1
    normal='aresample=48000,asetpts=PTS-STARTPTS,aformat=channel_layouts=stereo'
    return (f"[0:a]{normal},atrim=0:{duration:.3f},apad,atrim=0:{end:.3f},asplit=2[speech][detector];"
            f"[1:a]{normal},volume={volume:.4f},atrim=0:{duration:.3f},apad,atrim=0:{end:.3f}[bed];"
            "[bed][detector]sidechaincompress=threshold=.03:ratio=8:attack=200:release=600[duck];"
            f"[speech][duck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,atrim=0:{duration:.3f}[aout]")


def create_highlight_clips(source: str, output_dir: str, count: int = 3,
                           min_seconds: float = 25, max_seconds: float = 55,
                           caption_provider: str = "auto", rights_confirmed: bool = False,
                           progress_cb=None, ranking_provider: str = "auto",
                           source_rights: str = "unknown",
                           background_music: str = "",
                           music_license: str = "none",
                           music_volume: float = 0.08,
                           gemini_model: str = "",
                           gemini_chat_cleanup: str = "delete-after-read",
                           framing: str = "face-crop", background_music_enabled: bool | None = None,
                           language: str = "en") -> dict:
    from .languages import language_pack
    language = language_pack(language).code
    if language == 'or':
        raise ValueError('Odia source transcription is not verified by this Whisper clip route. Use a reviewed Odia transcript in AI RECREATE instead.')
    if background_music_enabled is not None and type(background_music_enabled) is not bool:
        raise ValueError('background_music_enabled must be true or false')
    if background_music_enabled is False:
        background_music = ''
    elif background_music_enabled is True and not str(background_music).strip():
        raise ValueError('Choose a licensed local music file or disable background music')
    if type(music_volume) not in (int,float) or not math.isfinite(music_volume) or not 0 <= music_volume <= .35:
        raise ValueError('Soft background music gain must be finite and between 0 and 0.35')
    framing_filter(framing)  # Validate before downloads or paid providers.
    if count < 1 or count > 100 or not (0 < min_seconds <= max_seconds):
        raise ValueError("Require count 1–100 and 0 < min_seconds <= max_seconds")
    os.makedirs(output_dir, exist_ok=True)
    # Different source URLs must never share a downloaded source.* cache.
    source_key = hashlib.sha256(str(source).encode("utf-8")).hexdigest()[:16]
    work = os.path.join(output_dir, "_clip_work", source_key)
    os.makedirs(work, exist_ok=True)
    from .progress import JobProgress
    progress = JobProgress(output_dir, progress_cb)
    def emit(message, pct, info=""):
        progress.emit(message, pct, info)
    rights = _rights_policy(source, source_rights, rights_confirmed)
    for warning in rights["warnings"]:
        emit("Rights notice", 1, warning)
    music_license = str(music_license or "none").strip().lower()
    if music_license not in MUSIC_LICENSES:
        raise RuntimeError("Invalid --music-license: " + music_license)
    background_music = str(background_music or "").strip()
    if background_music:
        if not os.path.isfile(background_music):
            raise FileNotFoundError(background_music)
        if music_license == "none":
            raise RuntimeError(
                "--background-music requires --music-license. Use only music you own "
                "or have permission/licence to publish.")
    music_volume = float(music_volume)
    emit("Preparing source", 5)
    local = resolve_input(source, work, rights_confirmed=rights_confirmed,
                          source_rights=source_rights)
    total = _duration(local)
    emit("Transcribing and timing speech", 18)
    words = (_transcribe_in_chunks(local, work, total, caption_provider, emit) if language == 'en'
             else _transcribe_in_chunks(local, work, total, caption_provider, emit, language=language))
    if not words:
        raise RuntimeError("No speech timings were produced; install faster-whisper or configure GROQ_API_KEY")
    emit("Ranking standalone moments", 24)
    requested_ranking = str(ranking_provider or "auto").lower()
    use_gemini_api = requested_ranking in (
        "gemini", "gemini-hybrid", "gemini-api-hybrid") or (
        requested_ranking == "auto" and _is_url(source) and bool(os.getenv("GEMINI_API_KEY")))
    use_gemini_web = requested_ranking in ("gemini", "gemini-hybrid", "gemini-web-hybrid")
    if requested_ranking == "auto" and str(os.getenv(
            "AUTOVIDEO_CLIP_BROWSER_FALLBACK", "0")).lower() in {"1", "true", "yes", "on"}:
        use_gemini_web = True
    fallback_events = []
    highlights = []
    if use_gemini_api and _is_url(source):
        try:
            emit("Gemini API analysing the full YouTube video", 24)
            proposals = _gemini_youtube_candidates(
                source, total, count, min_seconds, max_seconds,
                model=gemini_model or None,
                progress_cb=lambda message: emit(message, 24))
            verified = _verify_gemini_candidates(
                proposals, words, total, min_seconds, max_seconds)
            highlights = _choose_non_overlapping(verified, count)
            if not highlights:
                raise RuntimeError("no non-overlapping verified Gemini candidates")
        except Exception as exc:
            detail = f"Gemini API {type(exc).__name__}: {str(exc)[:300]}"
            fallback_events.append(detail)
            emit("Gemini API unavailable", 24, detail)
            highlights = []
    elif use_gemini_api:
        fallback_events.append(
            "Gemini API direct video analysis requires a public YouTube URL")

    if not highlights and use_gemini_web and _is_url(source):
        try:
            emit("Opening signed-in Gemini browser for YouTube analysis", 24)
            proposals = _gemini_web_youtube_candidates(
                source, total, count, min_seconds, max_seconds,
                cleanup=gemini_chat_cleanup)
            verified = _verify_gemini_candidates(
                proposals, words, total, min_seconds, max_seconds)
            highlights = _choose_non_overlapping(verified, count)
            if not highlights:
                raise RuntimeError("no non-overlapping verified browser candidates")
        except Exception as exc:
            detail = f"Gemini browser {type(exc).__name__}: {str(exc)[:300]}"
            fallback_events.append(detail)
            emit("Gemini browser unavailable; using Groq/local fallback", 24, detail)
            highlights = []
    elif not highlights and use_gemini_web:
        fallback_events.append(
            "Gemini browser YouTube analysis requires a public YouTube URL")

    if not highlights:
        fallback_provider = "groq" if requested_ranking == "groq" else "auto"
        if requested_ranking == "local":
            fallback_provider = "local"
        highlights = rank_highlights(
            words, total, count, min_seconds, max_seconds,
            ranking_provider=fallback_provider)
    ranking_fallback = " | ".join(fallback_events)
    if not highlights:
        raise RuntimeError("No complete highlight windows were found in the source")
    shortfall = max(0, count - len(highlights))
    shortfall_reason = (f"Requested {count}; found {len(highlights)} verified, non-overlapping moments. "
                        "Kept the valid selections; did not pad with weaker clips." if shortfall else "")
    if shortfall:
        emit("Partial selection", 24, shortfall_reason)
    # Save selection BEFORE rendering so failures do not lose editorial choices.
    selection_path = os.path.join(work, f"selection-{time.time_ns()}.json")
    with open(selection_path, "w", encoding="utf-8") as f:
        json.dump({"requested": count, "selected": len(highlights), "shortfall_reason": shortfall_reason,
                   "highlights": highlights, "fallback_events": fallback_events}, f, indent=2)
    from .render.captions_ass import build_captions
    outputs = []
    used_names: set[str] = {p.stem for p in Path(output_dir).glob("*.mp4")}
    for i, h in enumerate(highlights, 1):
        emit(f"Rendering highlight {i}/{len(highlights)}", 25 + int(70 * (i-1) / len(highlights)))
        clip_words = [{**w, "start": max(0.0, float(w["start"]) - h["start"]),
                       "end": max(0.04, float(w["end"]) - h["start"])}
                      for w in words if float(w.get("end", 0)) > h["start"] and float(w.get("start", 0)) < h["end"]]
        cap = build_captions(clip_words, os.path.join(work, f"clip_{i:02d}"),
                             template="OPUS", aspect="9:16", W=1080, H=1920,
                             duration=h["duration"])
        if cap.get("warnings"):
            h["caption_warnings"] = cap["warnings"]
            emit("Caption timing needs review", 25 + int(70 * (i-1) / len(highlights)),
                 "; ".join(cap["warnings"]))
        face_x = _face_crop_x(local, h["start"], h["duration"]) if framing == "face-crop" else .5
        # Crop to 9:16 around the median detected speaker position.  Clamp x so
        # FFmpeg never requests pixels outside the source frame.
        vf = framing_filter(framing, face_x)
        ass = os.path.abspath(cap["ass"]).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        from .render.ffmpeg_renderer import _fontsdir, _esc_filter_path
        font_dir = _fontsdir()
        vf += f",subtitles='{ass}'" + (f":fontsdir='{_esc_filter_path(font_dir)}'" if font_dir else '')
        title = str(h.get("title") or _short_title(h.get("text", ""))).strip()
        from .editorial_text import usable_headline
        if not usable_headline(title):
            title = _short_title(h.get("text", ""))
        h["title"] = title
        out = os.path.join(output_dir, _headline_filename(title, i, used_names))
        cmd = ["ffmpeg", "-y", "-ss", str(h["start"]), "-t", str(h["duration"]),
               "-i", local]
        if background_music:
            cmd += ["-stream_loop", "-1", "-i", os.path.abspath(background_music),
                    "-filter_complex",
                    soft_music_filter(float(h['duration']), music_volume)]
        cmd += ["-vf", vf, "-map", "0:v:0"]
        cmd += ["-map", "[aout]"] if background_music else ["-map", "0:a?"]
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-r", "30", "-movflags", "+faststart", out]
        from .render.ffmpeg_renderer import _run_ffmpeg_progress
        base_percent = 25 + 70 * (i-1) / len(highlights)
        p = _run_ffmpeg_progress(cmd, h["duration"],
            progress_cb=lambda pct, detail: emit(
                f"Rendering highlight {i}/{len(highlights)}",
                base_percent + (70 / len(highlights)) * .65 * pct / 100, detail),
            timeout=max(180, int(h["duration"] * 30)))
        if p.returncode != 0:
            raise RuntimeError("FFmpeg clip render failed: " + (p.stderr or "")[-900:])
        emit(f"Quality checking highlight {i}/{len(highlights)}",
             25 + int(70 * (i-.35) / len(highlights)), os.path.basename(out))
        qc = _clip_qc_report(out, h["duration"], h.get("score", 0), len(clip_words))
        qc_path = os.path.splitext(out)[0] + ".qc.json"
        with open(qc_path, "w", encoding="utf-8") as qf:
            json.dump(qc, qf, indent=2, ensure_ascii=False)
        from .production import save, digest
        sidecar = Path(out).with_suffix('.transcript.json')
        save(sidecar, {'schema_version':1,'clip_sha256':digest(out),'language':language,
                       'text':' '.join(w['word'] for w in clip_words),'words':clip_words,
                       'source_start':h['start'],'source_end':h['end'],
                       'rights':rights,'adaptation_confirmed':False,
                       'notice':'Review transcription and adaptation rights before AI recreation'})
        h['transcript_sidecar'] = str(sidecar)
        h["output"] = out
        h["output_filename"] = os.path.basename(out)
        h["caption_ass_path"] = os.path.abspath(cap["ass"]) if cap.get("ass") else ""
        h["face_center_x"] = round(face_x, 3)
        h["framing"] = framing
        h["quality_score"] = qc["quality_score"]
        h["qc"] = qc
        if qc["decision"] == "BLOCK":
            raise RuntimeError(
                f"Clip QC blocked {os.path.basename(out)}: " +
                ", ".join(qc["blocking_issues"]) +
                f". Inspect {qc_path}; the clip was not marked ready for upload.")
        outputs.append(out)
    method = ("Gemini YouTube analysis + transcript verification + local hybrid scoring"
              if highlights and highlights[0].get("ranking") == "gemini-hybrid"
              else "speech timing + Groq/local editorial ranking")
    report = {"source": local, "source_input": source,
              "requested_count": count, "actual_count": len(outputs),
              "partial_result": bool(shortfall), "shortfall_reason": shortfall_reason,
              "selection_report": selection_path, "editorial_review_required": True,
              "source_duration": round(total, 3), "rights": rights,
              "ranking_requested": requested_ranking,
              "ranking_fallback_reason": ranking_fallback,
              "method": method,
              "music": {"path": background_music or None,
                        "license_declaration": music_license,
                        "volume": music_volume if background_music else 0},
              "highlights": highlights, "outputs": outputs}
    with open(os.path.join(output_dir, "highlights.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    emit(f"Rendered {len(outputs)}/{count} clips — editorial review required", 100, shortfall_reason)
    return report
