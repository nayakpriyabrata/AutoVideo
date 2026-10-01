"""Caption timing and exact-script alignment for AutoVideoAI v5.

The narration script is the source of truth for caption text. Speech recognition
is used primarily to recover *timing*, so ASR mistakes no longer become visible
subtitle mistakes.
"""
from __future__ import annotations

import json
import os
import re
import math
from difflib import SequenceMatcher
from .runtime_log import runtime_print as print


class CaptionProviderError(RuntimeError):
    """Explicitly requested caption timing provider is unavailable or failed."""


def _norm_token(token: str) -> str:
    return re.sub(r"[^\w']+", "", str(token or "").lower(), flags=re.UNICODE)


def _script_tokens(text: str) -> list[str]:
    return [x for x in re.findall(r"\S+", str(text or "")) if _norm_token(x)]


def align_words_to_script(script_text: str, asr_words: list[dict],
                          audio_duration: float | None = None) -> list[dict]:
    """Replace ASR wording with exact script wording while retaining timing.

    Exact/near sequence matches anchor the timeline. Script words missed or
    misrecognized by ASR are interpolated between surrounding anchors.
    """
    src = _script_tokens(script_text)
    if not src:
        return asr_words or []
    clean_asr = []
    for w in asr_words or []:
        n = _norm_token(w.get("word", ""))
        if not n:
            continue
        try:
            st, en = float(w.get("start", 0)), float(w.get("end", 0))
        except Exception:
            continue
        if not math.isfinite(st) or not math.isfinite(en):
            continue
        clean_asr.append({"word": str(w.get("word", "")).strip(), "norm": n,
                          "start": max(0.0, st), "end": max(st, en)})
    if audio_duration is None:
        audio_duration = max([float(w.get("end", 0)) for w in clean_asr] + [0.0])
    audio_duration = max(float(audio_duration or 0), 0.1)

    src_norm = [_norm_token(x) for x in src]
    if not clean_asr:
        # Exact text with estimated uniform timing is still better than invented
        # subtitle words or no captions at all.
        weights = [max(1, len(_norm_token(x))) for x in src]
        total = float(sum(weights))
        cur = 0.0
        out = []
        for token, wt in zip(src, weights):
            span = audio_duration * wt / total
            out.append({"word": token, "start": round(cur, 3),
                        "end": round(min(audio_duration, cur + span), 3)})
            cur += span
        return out

    asr_norm = [x["norm"] for x in clean_asr]
    times: list[tuple[float, float] | None] = [None] * len(src)
    sm = SequenceMatcher(a=src_norm, b=asr_norm, autojunk=False)
    for block in sm.get_matching_blocks():
        for off in range(block.size):
            si, ai = block.a + off, block.b + off
            times[si] = (clean_asr[ai]["start"], clean_asr[ai]["end"])

    # SequenceMatcher anchors preserve word order. The old greedy fallback reused
    # common ASR words across anchors, jumping ahead by minutes and collapsing all
    # following tokens onto that timestamp. Interpolate unmatched spans instead.
    previous = 0.0
    for i, timing in enumerate(times):
        if timing is None:
            continue
        st, en = timing
        if st < previous - 0.02 or en > audio_duration + 0.5:
            times[i] = None
        else:
            previous = en

    # Interpolate every unanchored run between its nearest known neighbors.
    i = 0
    while i < len(src):
        if times[i] is not None:
            i += 1
            continue
        start = i
        while i < len(src) and times[i] is None:
            i += 1
        end = i - 1
        left = times[start - 1][1] if start > 0 and times[start - 1] is not None else 0.0
        right = times[i][0] if i < len(src) and times[i] is not None else audio_duration
        if right <= left:
            right = min(audio_duration, left + max(0.12 * (end - start + 1), 0.12))
        weights = [max(1, len(src_norm[k])) for k in range(start, end + 1)]
        total = float(sum(weights))
        cur = left
        for k, wt in zip(range(start, end + 1), weights):
            span = max(0.04, (right - left) * wt / total)
            times[k] = (cur, min(right, cur + span))
            cur += span

    out = []
    last_end = 0.0
    for token, t in zip(src, times):
        st, en = t or (last_end, last_end + 0.08)
        st = max(last_end, min(float(st), audio_duration))
        en = max(st + 0.04, float(en))
        en = min(en, audio_duration)
        if en < st:
            en = st
        out.append({"word": token, "start": round(st, 3), "end": round(en, 3)})
        last_end = en
    # Repeated/common words can give SequenceMatcher a plausible-looking final
    # anchor very early in a long recording. That left a multi-minute audio tail
    # without timed words and made the director hold one visual for minutes.
    gaps = [max(0.0, out[i]["start"] - out[i-1]["end"]) for i in range(1, len(out))]
    collapsed = sum(w["end"] - w["start"] < 0.015 for w in out)
    long_words = sum(w["end"] - w["start"] > 3 for w in out)
    if out and audio_duration >= 30 and (
            last_end < audio_duration * 0.85 or max(gaps or [0]) > 6
            or collapsed > max(3, len(out) * .05) or long_words > 2
            or max((w["end"] - w["start"] for w in out), default=0) > 6):
        fallback = script_timed_word_timestamps(script_text, audio_duration)
        if fallback:
            print("Caption timing repair: implausible ASR anchors; using estimated script timing. Exact word sync needs review.")
            return fallback
    return out


def _compact_groq_prompt(script_text: str, max_words: int = 110) -> str:
    """Return a short Groq Whisper hint safely below the provider prompt cap.

    Groq documents the Whisper prompt as limited to 224 tokens. Older builds
    sent up to 1800 characters of a long-form script, which can exceed that
    limit and produce HTTP 400 before transcription begins. Captions already
    align back to the exact authored script, so the ASR prompt only needs a
    small spelling/context hint rather than the full narration.
    """
    words = re.findall(r"\S+", str(script_text or ""))
    if not words:
        return ""
    # 110 ordinary English words is comfortably below 224 tokens in practice.
    return " ".join(words[:max_words])[:900]


def _segments_to_word_timestamps(segments: list[dict]) -> list[dict] | None:
    """Approximate word timings from Groq segment timestamps.

    This remains a Groq-derived timing path. It is used only if a valid Groq
    verbose-json response contains segments but no word array. Exact visible
    caption wording is still restored later by ``align_words_to_script``.
    """
    out = []
    for seg in segments or []:
        text = str(seg.get("text", "") or "").strip()
        toks = [x for x in re.findall(r"\S+", text) if _norm_token(x)]
        if not toks:
            continue
        try:
            st = max(0.0, float(seg.get("start", 0) or 0))
            en = max(st, float(seg.get("end", st) or st))
        except Exception:
            continue
        span = max(0.04 * len(toks), en - st)
        weights = [max(1, len(_norm_token(x))) for x in toks]
        total = float(sum(weights))
        cur = st
        for token, wt in zip(toks, weights):
            d = span * wt / total
            end = min(en if en > st else st + span, cur + d)
            if end <= cur:
                end = cur + 0.04
            out.append({"word": token, "start": round(cur, 3), "end": round(end, 3)})
            cur = end
    return out or None


def _groq_transcription_request(audio_path: str, key: str, data: list[tuple],
                                timeout: int = 180):
    """Issue one Groq transcription request and preserve the error body."""
    import mimetypes
    import requests
    mime = mimetypes.guess_type(audio_path)[0] or "application/octet-stream"
    with open(audio_path, "rb") as fh:
        r = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {key}"},
            files={"file": (os.path.basename(audio_path), fh, mime)},
            data=data, timeout=timeout,
        )
    if r.status_code >= 400:
        detail = (r.text or "").strip().replace("\n", " ")[:700]
        err = requests.HTTPError(
            f"Groq transcription HTTP {r.status_code}: {detail or 'no response body'}",
            response=r,
        )
        raise err
    return r


def _groq_word_timestamps(audio_path: str, model: str, language: str,
                          prompt: str = "") -> list[dict] | None:
    import requests
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        return None
    lang = str(language or "en").split("-")[0]
    base = [
        ("model", model),
        ("response_format", "verbose_json"),
        ("timestamp_granularities[]", "word"),
        ("language", lang),
        ("temperature", "0"),
    ]
    short_prompt = _compact_groq_prompt(prompt)

    # First attempt: word timestamps plus a provider-safe compact prompt.
    attempts = []
    data = list(base)
    if short_prompt:
        data.append(("prompt", short_prompt))
    attempts.append(("word+prompt" if short_prompt else "word", data))

    # A 400 is often caused by an optional-field constraint. Retry the exact
    # same Groq model without prompt before giving up.
    if short_prompt:
        attempts.append(("word-no-prompt", list(base)))

    last_error = None
    payload = None
    for label, req_data in attempts:
        try:
            r = _groq_transcription_request(audio_path, key, req_data)
            payload = r.json()
            break
        except requests.HTTPError as e:
            last_error = e
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status != 400:
                raise
            print(f"Groq transcription request '{label}' returned HTTP 400; retrying with a simpler same-provider request...")

    # Final same-provider compatibility path: ask Groq for segment timestamps.
    # Segment timing is documented and sufficient because exact script text is
    # aligned back onto the returned timeline later.
    if payload is None:
        seg_data = [
            ("model", model),
            ("response_format", "verbose_json"),
            ("timestamp_granularities[]", "segment"),
            ("language", lang),
            ("temperature", "0"),
        ]
        try:
            r = _groq_transcription_request(audio_path, key, seg_data)
            payload = r.json()
        except Exception:
            if last_error is not None:
                raise last_error
            raise

    words = payload.get("words") or []
    out = []
    for w in words:
        word = str(w.get("word", "") or "").strip()
        if word:
            out.append({"word": word, "start": round(float(w.get("start", 0)), 3),
                        "end": round(float(w.get("end", w.get("start", 0))), 3)})
    if out:
        return out
    return _segments_to_word_timestamps(payload.get("segments") or [])


def _local_word_timestamps(audio_path: str, model_size: str, language: str) -> list[dict] | None:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    print(f"Transcribing timing with faster-whisper ({model_size})...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    lang = str(language or "en").split("-")[0]
    segments, _ = model.transcribe(audio_path, word_timestamps=True,
                                   language=lang if lang else None, vad_filter=True)
    words = []
    for seg in segments:
        for w in (seg.words or []):
            t = (w.word or "").strip()
            if t:
                words.append({"word": t, "start": round(float(w.start), 3),
                              "end": round(float(w.end), 3)})
    return words or None


def _audio_duration(path: str) -> float:
    try:
        from .audio.tts import _mp3_len
        return float(_mp3_len(path) or 0)
    except Exception:
        return 0.0




def script_timed_word_timestamps(script_text: str, audio_duration: float) -> list[dict] | None:
    """Create deterministic timings from the exact authored script and audio length.

    This removes ASR from the critical path.  Words get speech-time weights and
    punctuation contributes pause weight, then the whole schedule is scaled to
    the measured narration duration.  It is intentionally phrase-friendly rather
    than pretending to be frame-accurate forced alignment.
    """
    tokens = [x for x in re.findall(r"\S+", str(script_text or "")) if _norm_token(x)]
    dur = max(0.0, float(audio_duration or 0))
    if not tokens or dur <= 0:
        return None

    speech = []
    pause_after = []
    for tok in tokens:
        clean = _norm_token(tok)
        # Slightly longer words receive more time, but cap the effect so long
        # orthographic words do not dominate the narration schedule.
        wt = 0.82 + min(0.72, max(0, len(clean) - 3) * 0.055)
        speech.append(wt)
        if re.search(r"[.!?][\"')\]]*$", tok):
            pause_after.append(0.46)
        elif re.search(r"[;:][\"')\]]*$", tok):
            pause_after.append(0.30)
        elif re.search(r",[\"')\]]*$", tok):
            pause_after.append(0.19)
        else:
            pause_after.append(0.035)

    total_units = sum(speech) + sum(pause_after[:-1])
    scale = dur / max(total_units, 1e-6)
    cur = 0.0
    out = []
    for i, (tok, wt) in enumerate(zip(tokens, speech)):
        st = cur
        en = min(dur, st + wt * scale)
        out.append({"word": tok, "start": round(st, 3), "end": round(en, 3)})
        cur = en
        if i < len(tokens) - 1:
            cur = min(dur, cur + pause_after[i] * scale)
    if out:
        out[-1]["end"] = round(dur, 3)
    return out or None

def get_word_timestamps(audio_path: str, model_size: str = "small",
                        provider: str = "auto", script_text: str = "",
                        language: str = "en", groq_model: str = "whisper-large-v3-turbo",
                        align_script: bool = True, force: bool = False) -> list | None:
    """Return production word timestamps.

    ``script-timed`` derives stable phrase-friendly timing directly from the
    authored script and measured narration duration, with no transcription API.
    ``auto`` may fall back from Groq to local faster-whisper and finally to
    script-estimated timing. Explicit ``groq``/``local`` selections are strict:
    a broken provider aborts before expensive visual generation instead of
    silently using a different engine.
    """
    cache = audio_path + ".words.json"
    if os.path.exists(cache) and not force:
        try:
            words = json.load(open(cache, encoding="utf-8"))
            if words:
                if script_text and align_script:
                    words = align_words_to_script(script_text, words, _audio_duration(audio_path))
                    with open(cache, "w", encoding="utf-8") as f:
                        json.dump(words, f)
                return words
        except Exception:
            pass

    p = str(provider or "auto").lower()
    words = None
    engine = ""
    if p in ("script-timed", "script", "none"):
        if not script_text:
            raise CaptionProviderError("--caption-provider script-timed requires the authored script text")
        words = script_timed_word_timestamps(script_text, _audio_duration(audio_path))
        engine = "script-timed"
    if p == "groq" and not os.getenv("GROQ_API_KEY"):
        raise CaptionProviderError("--caption-provider groq was requested but GROQ_API_KEY is not configured")

    if words is None and p in ("auto", "groq") and os.getenv("GROQ_API_KEY"):
        try:
            print(f"Transcribing timing with Groq {groq_model}...")
            words = _groq_word_timestamps(audio_path, groq_model, language, script_text)
            engine = f"groq:{groq_model}"
        except Exception as e:
            if p == "groq":
                raise CaptionProviderError(f"Groq transcription failed: {str(e)[:220]}") from e
            print(f"Groq transcription failed ({str(e)[:130]}) -> local Whisper fallback")
            words = None

    if words is None and p in ("auto", "local", "faster-whisper"):
        try:
            words = _local_word_timestamps(audio_path, model_size, language)
            if words:
                engine = f"faster-whisper:{model_size}"
        except Exception as e:
            if p in ("local", "faster-whisper"):
                raise CaptionProviderError(f"Local Whisper failed: {str(e)[:220]}") from e
            print(f"Local Whisper failed ({str(e)[:130]})")
            words = None

    dur = _audio_duration(audio_path)
    if script_text and align_script:
        words = align_words_to_script(script_text, words or [], dur)
        engine = (engine + "+script-align") if engine else "script-estimated"

    if not words:
        if p in ("groq", "local", "faster-whisper", "script-timed", "script", "none"):
            raise CaptionProviderError(f"Explicit caption provider '{p}' produced no usable word timings")
        print("No word timings available -> classic captions.")
        return None
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(words, f)
    try:
        with open(audio_path + ".words.meta.json", "w", encoding="utf-8") as f:
            json.dump({"engine": engine, "script_aligned": bool(script_text and align_script)}, f)
    except Exception:
        pass
    return words


def group_words(words: list, max_words: int = 7, max_gap: float = 0.50,
                max_duration: float = 2.8) -> list:
    """Phrase-aware caption grouping for mobile/YouTube readability.

    Old builds cut every four words, producing fragments such as "In 5 minutes, /
    I will". This scheduler prefers punctuation/clause boundaries, allows 5-7
    word phrases, and caps on-screen duration.
    """
    groups, cur = [], []

    def flush():
        nonlocal cur
        if cur:
            groups.append({"words": cur, "start": cur[0]["start"], "end": cur[-1]["end"]})
            cur = []

    for w in words or []:
        if cur:
            gap = float(w.get("start", 0)) - float(cur[-1].get("end", 0))
            span = float(cur[-1].get("end", 0)) - float(cur[0].get("start", 0))
            prev = str(cur[-1].get("word", ""))
            punct_break = bool(re.search(r"[.!?;:]$", prev)) and len(cur) >= 3
            comma_break = bool(re.search(r"[,]$", prev)) and len(cur) >= 5
            if (len(cur) >= max_words or gap > max_gap or span >= max_duration
                    or punct_break or comma_break):
                flush()
        cur.append(w)
    flush()
    return groups
