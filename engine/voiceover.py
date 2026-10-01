"""
Voiceover - 100% FREE, no API key
1. edge-tts (Microsoft, free unlimited) <- best quality
2. gTTS (Google, free) <- fallback
"""
import asyncio
import os

# Popular free voices (edge-tts)
VOICES = {
    "English India Female": "en-IN-NeerjaNeural",
    "English India Male": "en-IN-PrabhatNeural",
    "English US Female": "en-US-AriaNeural",
    "English US Male": "en-US-GuyNeural",
    "English UK Female": "en-GB-SoniaNeural",
    "English UK Male": "en-GB-RyanNeural",
    "Hindi Female": "hi-IN-SwaraNeural",
    "Hindi Male": "hi-IN-MadhurNeural",
}


def _chunk_text(text: str, max_chars: int = 900) -> list:
    """Split long text into chunks at sentence boundaries."""
    import re
    sents = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks, cur = [], ""
    for s in sents:
        if len(cur) + len(s) + 1 <= max_chars:
            cur = (cur + " " + s).strip()
        else:
            if cur:
                chunks.append(cur)
            cur = s
    if cur:
        chunks.append(cur)
    return chunks or [text]


async def _edge_save(text: str, voice: str, out: str, rate: str = "+0%"):
    import edge_tts
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(out)


def _gtts_save(text: str, out: str, lang: str = "en"):
    from gtts import gTTS
    tld = "co.in" if lang == "en" else "com"
    gTTS(text=text, lang=lang, tld=tld).save(out)


def text_to_speech(text: str, output_path: str,
                   voice: str = "en-IN-NeerjaNeural",
                   rate: str = "+5%") -> dict:
    """
    Returns {"audio": path, "engine": "edge-tts"|"gtts", "duration": sec|None}
    Handles long scripts by chunking + merging with moviepy.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    chunks = _chunk_text(text)

    # Single chunk fast path
    if len(chunks) == 1:
        try:
            asyncio.run(_edge_save(chunks[0], voice, output_path, rate))
            return {"audio": output_path, "engine": "edge-tts",
                    "duration": _audio_len(output_path)}
        except Exception as e:
            print(f"edge-tts failed ({e}), trying gTTS...")
            lang = "hi" if voice.startswith("hi-") else "en"
            _gtts_save(chunks[0], output_path, lang)
            return {"audio": output_path, "engine": "gtts",
                    "duration": _audio_len(output_path)}

    # Multi-chunk: synthesize parts then merge
    import tempfile
    tmpdir = tempfile.mkdtemp(prefix="tts_")
    parts = []
    engine = "edge-tts"
    for i, ch in enumerate(chunks):
        p = os.path.join(tmpdir, f"part{i:03d}.mp3")
        try:
            asyncio.run(_edge_save(ch, voice, p, rate))
        except Exception:
            lang = "hi" if voice.startswith("hi-") else "en"
            _gtts_save(ch, p, lang)
            engine = "gtts-mixed"
        parts.append(p)

    # Merge with moviepy
    from moviepy.editor import AudioFileClip, concatenate_audioclips
    clips = [AudioFileClip(p) for p in parts]
    final = concatenate_audioclips(clips)
    final.write_audiofile(output_path, logger=None)
    dur = final.duration
    for c in clips:
        c.close()
    final.close()
    return {"audio": output_path, "engine": engine, "duration": dur}


def _audio_len(path: str):
    try:
        from moviepy.editor import AudioFileClip
        c = AudioFileClip(path)
        d = c.duration
        c.close()
        return d
    except Exception:
        return None
