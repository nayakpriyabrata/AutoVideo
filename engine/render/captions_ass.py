"""Eight caption templates with safe zones and narration-driven word timing.

Outputs ASS (burn-in) and SRT (sidecar/upload). Layout is measured using visible
text, never ASS markup, so changing the highlighted word cannot reflow a phrase.
"""
from __future__ import annotations
import math
import os
import re

# ASS colors are &HAABBGGRR
TEMPLATES = {
    "MINIMAL":    {"Fontsize": 64, "Primary": "&H00FFFFFF", "Outline": 1, "Shadow": 1, "Bold": 0, "Back": "&H99000000", "word_events": False},
    "HORMOZI":    {"Fontsize": 84, "Primary": "&H00FFFFFF", "Active": "&H0025D1FF", "Outline": 3, "Shadow": 0, "Bold": 1, "word_events": True},
    "DOCUMENTARY":{"Fontsize": 58, "Primary": "&H00F2E8D5", "Outline": 1, "Shadow": 1, "Bold": 0, "word_events": False},
    "CINEMATIC":  {"Fontsize": 62, "Primary": "&H00E8DCC8", "Outline": 2, "Shadow": 2, "Bold": 0, "word_events": False},
    "KARAOKE":    {"Fontsize": 80, "Primary": "&H00FFFFFF", "Active": "&H0025D1FF", "Outline": 3, "Shadow": 0, "Bold": 1, "karaoke": True},
    "TECH":       {"Fontsize": 66, "Primary": "&H00FFD75A", "Outline": 2, "Shadow": 0, "Bold": 1, "word_events": False},
    "KIDS":       {"Fontsize": 88, "Primary": "&H0033CCFF", "Outline": 4, "Shadow": 2, "Bold": 1, "word_events": True, "Active": "&H0042F587"},
    "OPUS":       {"Fontsize": 88, "Primary": "&H00FFFFFF", "Active": "&H004BE36D", "Outline": 4, "Shadow": 2, "Bold": 1, "word_events": True},
}

SAFE_ZONES = {
    "9:16": {"MarginV": 340, "MarginL": 60, "MarginR": 60},   # clear of Reels/Shorts/TikTok UI
    "16:9": {"MarginV": 110, "MarginL": 80, "MarginR": 80},
}
REFERENCE_SIZE = {"9:16": (1080, 1920), "16:9": (1920, 1080)}
SENTENCE_END = re.compile(r"[.!?…।॥][\"'”’)\]]*$")
ASS_TAG = re.compile(r"\{[^}]*\}")


def _seconds(value, label: str) -> float:
    try:
        if isinstance(value, bool):
            raise ValueError
        seconds = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"Invalid {label}: {value!r}") from exc
    if not math.isfinite(seconds):
        raise ValueError(f"Invalid {label}: {value!r}; timing must be finite")
    return seconds


def _ticks(t: float, precision: int) -> int:
    seconds = max(0.0, _seconds(t, "caption timestamp"))
    scaled = seconds * precision
    if not math.isfinite(scaled):
        raise ValueError(f"Invalid caption timestamp: {t!r}")
    # Round the entire timestamp BEFORE splitting hours/minutes/seconds. Rounding
    # only the seconds field produced invalid stamps such as 0:00:60.00.
    return int(math.floor(scaled + .5))


def _fmt_ass(t: float) -> str:
    h, remaining = divmod(_ticks(t, 100), 360000)
    m, remaining = divmod(remaining, 6000)
    s, cs = divmod(remaining, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _fmt_srt(t: float) -> str:
    h, remaining = divmod(_ticks(t, 1000), 3600000)
    m, remaining = divmod(remaining, 60000)
    s, ms = divmod(remaining, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _validated_words(words: list[dict], duration: float | None = None) -> list[dict]:
    """Preserve authored order and wording; reject broken timing rather than sort it."""
    result, previous_start = [], -1.0
    for i, word in enumerate(words):
        if not isinstance(word, dict) or not isinstance(word.get("word"), str):
            raise ValueError(f"Invalid caption word[{i}]: expected word/start/end")
        text = " ".join(word["word"].split())
        if not text:
            continue
        start = _seconds(word.get("start"), f"word[{i}].start")
        end = _seconds(word.get("end"), f"word[{i}].end")
        if start < 0 or end < start or start < previous_start:
            raise ValueError(f"Invalid caption word[{i}]: expected 0 <= start <= end and ordered starts")
        previous_start = start
        if duration is not None:
            if start >= duration:
                continue
            end = min(end, duration)
        result.append({**word, "word": text, "start": start, "end": end})
    return result


def words_to_phrases(words: list[dict], max_chars: int = 34, max_gap: float = .5,
                     max_duration: float = 3.0) -> list[dict]:
    """Punctuation-, pause-, and reading-duration-aware grouping.

    A single long word is kept intact, even if it exceeds max_chars/duration.
    Grouping never changes the source word timestamps.
    """
    if max_chars < 1 or not math.isfinite(max_gap) or max_gap < 0:
        raise ValueError("Invalid caption phrase character/gap limit")
    if not math.isfinite(max_duration) or max_duration <= 0:
        raise ValueError("Invalid caption phrase duration limit")
    phrases, cur = [], []
    for word in _validated_words(words):
        if cur and (
            word["start"] - cur[-1]["end"] > max_gap
            or len(" ".join(x["word"] for x in cur)) + 1 + len(word["word"]) > max_chars
            or max(word["end"], max(x["end"] for x in cur)) - cur[0]["start"] > max_duration
            or SENTENCE_END.search(cur[-1]["word"])
        ):
            phrases.append(_pack(cur))
            cur = []
        cur.append(word)
    if cur:
        phrases.append(_pack(cur))
    return phrases


def _pack(cur):
    return {"words": cur, "start": cur[0]["start"], "end": max(x["end"] for x in cur),
            "text": " ".join(x["word"] for x in cur)}


def _wrap2(text: str, width: int = 18) -> str:
    parts = text.split()
    plain = [ASS_TAG.sub("", part) for part in parts]
    if len(parts) < 2 or len(" ".join(plain)) <= width:
        return text

    def score(i):
        left, right = len(" ".join(plain[:i])), len(" ".join(plain[i:]))
        return (max(0, left - width) + max(0, right - width), abs(left - right))

    split = min(range(1, len(parts)), key=score)
    return " ".join(parts[:split]) + r"\N" + " ".join(parts[split:])


def build_captions(words: list[dict], out_base: str, template: str = "HORMOZI",
                   aspect: str = "9:16", W: int = 1080, H: int = 1920,
                   keyword_color: str | None = None,
                   duration: float | None = None) -> dict:
    """Write ASS/SRT and return paths, event count, and timing warnings.

    ``duration`` optionally clamps all cues and caption holds to the actual
    narration/clip length. ASS has 10ms precision: unrepresentable events are
    omitted and reported, never stretched over the next word or written inverted.
    """
    if duration is not None:
        duration = _seconds(duration, "caption duration")
        if duration <= 0:
            raise ValueError("Caption duration must be positive")
    if (not isinstance(W, int) or isinstance(W, bool) or W <= 0
            or not isinstance(H, int) or isinstance(H, bool) or H <= 0):
        raise ValueError("Caption output dimensions must be positive integers")
    words = _validated_words(words or [], duration)
    phrases = words_to_phrases(words)
    T = TEMPLATES.get(template.upper(), TEMPLATES["HORMOZI"])
    zone = aspect if aspect in SAFE_ZONES else "9:16"
    rw, rh = REFERENCE_SIZE[zone]
    scale = min(W / rw, H / rh)
    sz = {"MarginL": round(SAFE_ZONES[zone]["MarginL"] * W / rw),
          "MarginR": round(SAFE_ZONES[zone]["MarginR"] * W / rw),
          "MarginV": round(SAFE_ZONES[zone]["MarginV"] * H / rh)}
    fontsize = max(8, round(T["Fontsize"] * scale))
    outline = max(1, round(T.get("Outline", 2) * scale))
    shadow = max(1, round(T["Shadow"] * scale)) if T.get("Shadow") else 0
    active = T.get("Active", "&H0025D1FF")
    primary = active if T.get("karaoke") else T["Primary"]
    secondary = T["Primary"] if T.get("karaoke") else "&H000000FF"

    # ASS v4+ requires exactly 23 fields in the Style row. Keep their order
    # aligned with Format; libass can otherwise reject or misinterpret the style.
    style = (f"Style: Cap,DejaVu Sans,{fontsize},{primary},{secondary},"
             f"&H00000000,{T.get('Back','&H00000000')},{-1 if T.get('Bold') else 0},0,0,0,100,100,"
             f"0,0,1,{outline},{shadow},2,"
             f"{sz['MarginL']},{sz['MarginR']},{sz['MarginV']},1")
    head = ("[Script Info]\nScriptType: v4.00+\nPlayResX: %d\nPlayResY: %d\nWrapStyle: 2\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, "
            "Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n%s\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            % (W, H, style))
    events, srt = [], []
    skipped_events = 0

    def add_event(start, end, text):
        nonlocal skipped_events
        start_tick, end_tick = _ticks(start, 100), _ticks(end, 100)
        if duration is not None:
            end_tick = min(end_tick, int(math.floor(duration * 100 + 1e-9)))
        if end_tick <= start_tick:
            skipped_events += 1
            return
        events.append((_fmt_ass(start_tick / 100), _fmt_ass(end_tick / 100), _wrap2(text)))

    for pi, phrase in enumerate(phrases):
        next_start = phrases[pi + 1]["start"] if pi + 1 < len(phrases) else phrase["end"] + .4
        hard_end = min(next_start, duration) if duration is not None else next_start
        if T.get("word_events"):
            for j, word in enumerate(phrase["words"]):
                end = (phrase["words"][j + 1]["start"] if j + 1 < len(phrase["words"])
                       else phrase["end"] + .15)
                parts = [f"{{\\c{active if k == j else T['Primary']}}}{x['word']}"
                         for k, x in enumerate(phrase["words"])]
                add_event(word["start"], min(end, hard_end), " ".join(parts))
        elif T.get("karaoke"):
            parts = []
            for j, word in enumerate(phrase["words"]):
                # Include inter-word silence in the preceding tag. Using only
                # word.end-word.start shifted all subsequent highlights early.
                end = (phrase["words"][j + 1]["start"] if j + 1 < len(phrase["words"])
                       else min(phrase["end"], hard_end))
                ticks = max(0, _ticks(end, 100) - _ticks(word["start"], 100))
                parts.append(f"{{\\k{ticks}}}{word['word']}")
            add_event(phrase["start"], min(phrase["end"] + .15, hard_end), " ".join(parts))
        else:
            text = phrase["text"]
            if keyword_color:
                for keyword in re.findall(r"[A-Za-z]{5,}", text)[:2]:
                    text = text.replace(keyword, f"{{\\c{keyword_color}}}{keyword}{{\\c{T['Primary']}}}", 1)
            add_event(phrase["start"], min(phrase["end"] + .2, hard_end), text)

        # The sidecar gets the same non-overlap guard as burn-in captions, but
        # retains the exact phrase text without color/karaoke markup or holds.
        end = min(phrase["end"], hard_end)
        if _ticks(end, 1000) > _ticks(phrase["start"], 1000):
            srt.append((phrase["start"], end, phrase["text"]))

    os.makedirs(os.path.dirname(os.path.abspath(out_base)), exist_ok=True)
    with open(out_base + ".ass", "w", encoding="utf-8") as fh:
        fh.write(head)
        for start, end, text in events:
            fh.write(f"Dialogue: 0,{start},{end},Cap,,0,0,0,,{text}\n")
    with open(out_base + ".srt", "w", encoding="utf-8") as fh:
        for i, (start, end, text) in enumerate(srt, 1):
            fh.write(f"{i}\n{_fmt_srt(start)} --> {_fmt_srt(end)}\n{text}\n\n")
    warnings = ([f"{skipped_events} caption event(s) are shorter than ASS's 10ms precision; review word timing."]
                if skipped_events else [])
    return {"ass": out_base + ".ass", "srt": out_base + ".srt",
            "events": len(events), "warnings": warnings}
