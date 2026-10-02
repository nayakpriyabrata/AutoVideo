"""Narration providers for AutoVideoAI v5.

Production routing is free-first and quality-first:
  Gemini 3.8 Flash TTS -> Gemini Flash-Lite TTS -> ElevenLabs (if keyed)
  -> Kokoro local (if installed) -> Edge -> gTTS last resort.

Exact caption text is no longer rediscovered inside a TTS provider.  Providers
return native timing when available; the factory's caption aligner supplies word
boundaries for providers that return audio only.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading

import requests
from ..runtime_log import runtime_print as print


# Permanent account/configuration failures should not be retried for every
# paragraph in one production. Explicit provider selection remains strict.
_AUTO_DISABLED_PROVIDERS: set[str] = set()


def _run_async_blocking(async_fn, *args, **kwargs):
    """Run one coroutine from synchronous code even if this thread already has an event loop.

    Browser-backed providers may temporarily leave an asyncio loop active in the
    calling thread.  ``asyncio.run(coro)`` would then raise *after* the coroutine
    object was created, producing both a failure and an ``unawaited coroutine``
    warning.  In that case, isolate the coroutine in a short worker thread.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(async_fn(*args, **kwargs))

    box = {}
    def runner():
        try:
            box["value"] = asyncio.run(async_fn(*args, **kwargs))
        except BaseException as exc:  # propagate provider/network errors faithfully
            box["error"] = exc

    t = threading.Thread(target=runner, name="autovideo-edge-tts", daemon=False)
    t.start()
    t.join()
    if "error" in box:
        raise box["error"]
    return box.get("value")


class EdgeTTSProvider:
    name = "edge"

    async def _synth_one(self, text: str, voice: str, rate: str, out: str):
        import edge_tts
        words = []
        comm = edge_tts.Communicate(text, voice, rate=rate)
        with open(out, "wb") as f:
            async for ch in comm.stream():
                t = ch.get("type")
                if t == "audio" and ch.get("data"):
                    f.write(ch["data"])
                elif t == "WordBoundary":
                    words.append({"word": ch.get("text", "").strip(),
                                  "start": ch.get("offset", 0) / 1e7,
                                  "end": (ch.get("offset", 0) + ch.get("duration", 0)) / 1e7})
        return words

    def synth(self, text: str, voice: str, out: str, rate: str = "+0%", **kwargs) -> dict:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        sents = re.split(r"(?<=[.!?])\s+", text.strip())
        chunks, cur = [], ""
        for s in sents:
            if len(cur) + len(s) < 800:
                cur = (cur + " " + s).strip()
            else:
                if cur:
                    chunks.append(cur)
                cur = s
        if cur:
            chunks.append(cur)
        tmp = tempfile.mkdtemp(prefix="edge_")
        parts, all_words, offset = [], [], 0.0
        try:
            for i, ch_text in enumerate(chunks):
                p = os.path.join(tmp, f"p{i:03d}.mp3")
                words = _run_async_blocking(self._synth_one, ch_text, voice, rate, p)
                dur = _mp3_len(p)
                for w in words:
                    if w["word"]:
                        all_words.append({"word": w["word"], "start": round(offset + w["start"], 3),
                                          "end": round(offset + w["end"], 3)})
                offset += dur
                parts.append(p)
            _concat_mp3(parts, out)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        dur = _mp3_len(out)
        if not os.path.exists(out) or os.path.getsize(out) < 1024 or dur <= 0:
            raise RuntimeError("Edge TTS returned empty audio (network/endpoint blocked?)")
        return {"audio": out, "words": all_words, "duration": dur, "engine": "edge-native"}


class GeminiTTSProvider:
    name = "gemini"

    def __init__(self, lite: bool = False):
        self.lite = lite

    @staticmethod
    def _audio_data(obj):
        """Find a base64/bytes audio payload across SDK/REST response shapes."""
        if obj is None:
            return None
        if isinstance(obj, (bytes, bytearray)):
            return bytes(obj)
        if isinstance(obj, str):
            # Avoid treating ordinary status text as audio.
            return obj if len(obj) > 256 else None
        if isinstance(obj, dict):
            for key in ("output_audio", "outputAudio", "audio"):
                if key in obj:
                    found = GeminiTTSProvider._audio_data(obj.get(key))
                    if found:
                        return found
            if "data" in obj:
                found = GeminiTTSProvider._audio_data(obj.get("data"))
                if found:
                    return found
            for v in obj.values():
                found = GeminiTTSProvider._audio_data(v)
                if found:
                    return found
            return None
        if isinstance(obj, (list, tuple)):
            for v in obj:
                found = GeminiTTSProvider._audio_data(v)
                if found:
                    return found
            return None
        # SDK objects. Prefer the documented convenience property first.
        for attr in ("output_audio", "outputAudio", "audio", "data"):
            try:
                found = GeminiTTSProvider._audio_data(getattr(obj, attr, None))
                if found:
                    return found
            except Exception:
                pass
        try:
            dump = obj.model_dump()
            return GeminiTTSProvider._audio_data(dump)
        except Exception:
            return None

    def synth(self, text: str, voice: str, out: str, rate: str = "+0%", **kwargs) -> dict:
        key = os.getenv("GEMINI_API_KEY", "")
        if not key:
            raise RuntimeError(
                "GEMINI_API_KEY is not configured. Run 'python3 cli.py v3 env-doctor' "
                "to verify which .env file and provider variables AutoVideoAI detected.")
        model = kwargs.get("model") or (
            "gemini-3.8-flash-lite-tts" if self.lite else "gemini-3.8-flash-tts")
        provider_voice = kwargs.get("provider_voice") or os.getenv("GEMINI_TTS_VOICE", "Kore")
        style = kwargs.get("style") or (
            "warm, confident documentary narrator; conversational and human; medium energy; "
            "natural sentence pauses; never salesy or robotic"
        )
        payload = {
            "model": model,
            "input": [{
                "type": "user_input",
                "content": [{
                    "type": "text", "text": text,
                    "annotations": [{"type": "speech_metadata", "style": style}],
                }],
            }],
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": provider_voice}]},
        }
        audio = None
        errors = []
        # Current google-genai Interactions API.
        try:
            from google import genai
            client = genai.Client(api_key=key)
            interaction = client.interactions.create(**payload)
            audio = self._audio_data(interaction)
        except Exception as e:
            errors.append(f"sdk:{type(e).__name__}:{str(e)[:160]}")

        # REST fallback mirrors the GA Interactions schema.
        if not audio:
            try:
                r = requests.post(
                    "https://generativelanguage.googleapis.com/v1beta/interactions",
                    headers={
                        "x-goog-api-key": key,
                        "Content-Type": "application/json",
                        "Api-Revision": "2026-05-20",
                    },
                    json=payload, timeout=180,
                )
                if r.status_code >= 400:
                    raise RuntimeError(f"HTTP {r.status_code}: {(r.text or '')[:300]}")
                audio = self._audio_data(r.json())
            except Exception as e:
                errors.append(f"rest:{type(e).__name__}:{str(e)[:180]}")

        if not audio:
            detail = " | ".join(errors[-2:])
            raise RuntimeError("Gemini TTS response contained no audio data" + (f" ({detail})" if detail else ""))

        if isinstance(audio, str):
            try:
                raw = base64.b64decode(audio, validate=False)
            except Exception as e:
                raise RuntimeError(f"Gemini TTS audio payload was not valid base64: {e}") from e
        else:
            raw = bytes(audio)
        if len(raw) < 1024:
            raise RuntimeError("Gemini TTS returned an implausibly small audio payload")

        wav = out + ".gemini.wav"
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        # Gemini speech responses may be a WAV container or raw 24 kHz signed
        # 16-bit mono PCM. Detect the container instead of assuming the base64
        # bytes already include a RIFF header.
        if raw[:4] == b"RIFF":
            with open(wav, "wb") as f:
                f.write(raw)
        else:
            import wave
            with wave.open(wav, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)
                wf.writeframes(raw)
        _audio_to_mp3(wav, out)
        try:
            os.remove(wav)
        except Exception:
            pass
        dur = _mp3_len(out)
        if dur <= 0:
            raise RuntimeError("Gemini TTS produced unreadable audio")
        return {"audio": out, "words": [], "duration": dur,
                "engine": "gemini-3.8-flash-lite-tts" if self.lite else "gemini-3.8-flash-tts"}


class ElevenLabsTTSProvider:
    name = "elevenlabs"

    def synth(self, text: str, voice: str, out: str, rate: str = "+0%", **kwargs) -> dict:
        key = os.getenv("ELEVENLABS_API_KEY", "")
        if not key:
            raise RuntimeError(
                "ELEVENLABS_API_KEY is not configured. Run 'python3 cli.py v3 env-doctor'.")
        voice_id = kwargs.get("provider_voice") or os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
        model = kwargs.get("model") or os.getenv("ELEVENLABS_TTS_MODEL", "eleven_multilingual_v2")
        r = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128",
            headers={"xi-api-key": key, "Content-Type": "application/json"},
            json={"text": text, "model_id": model}, timeout=180,
        )
        r.raise_for_status()
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "wb") as f:
            f.write(r.content)
        dur = _mp3_len(out)
        if dur <= 0:
            raise RuntimeError("ElevenLabs produced unreadable audio")
        return {"audio": out, "words": [], "duration": dur, "engine": f"elevenlabs:{model}"}


class GroqTTSProvider:
    name = "groq"

    @staticmethod
    def _chunks(text: str, limit: int = 190) -> list[str]:
        # Orpheus currently caps each request at 200 characters. Keep headroom.
        sents = re.split(r"(?<=[.!?])\s+", text.strip())
        out, cur = [], ""
        for sent in sents:
            pieces = [sent]
            if len(sent) > limit:
                words, pieces, part = sent.split(), [], ""
                for w in words:
                    if part and len(part) + len(w) + 1 > limit:
                        pieces.append(part); part = w
                    else:
                        part = (part + " " + w).strip()
                if part:
                    pieces.append(part)
            for piece in pieces:
                piece = piece.strip()
                if not piece:
                    continue
                if cur and len(cur) + len(piece) + 1 > limit:
                    out.append(cur); cur = piece
                else:
                    cur = (cur + " " + piece).strip()
        if cur:
            out.append(cur)
        return [x[:limit] for x in out if x.strip()]

    def synth(self, text: str, voice: str, out: str, rate: str = "+0%", **kwargs) -> dict:
        key = os.getenv("GROQ_API_KEY", "")
        if not key:
            raise RuntimeError(
                "GROQ_API_KEY is not configured. Run 'python3 cli.py v3 env-doctor'.")
        language = str(kwargs.get("language") or "en").lower()
        if not language.startswith("en"):
            raise RuntimeError("Groq Orpheus auto fallback is currently enabled only for English narration")
        model = kwargs.get("model") or os.getenv("GROQ_TTS_MODEL", "canopylabs/orpheus-v1-english")
        provider_voice = kwargs.get("provider_voice") or os.getenv("GROQ_TTS_VOICE", "troy")
        style = str(kwargs.get("style") or "").lower()
        direction = "[professionally] " if any(x in style for x in ("professional", "documentary", "confident")) else ""
        tmp = tempfile.mkdtemp(prefix="groq_tts_")
        parts = []
        try:
            for i, chunk in enumerate(self._chunks(text)):
                spoken = (direction + chunk).strip()
                # Ensure the provider's hard 200-character limit remains respected
                # even after adding an optional delivery direction.
                if len(spoken) > 200:
                    spoken = chunk[:190]
                r = requests.post(
                    "https://api.groq.com/openai/v1/audio/speech",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                        "Accept": "audio/wav",
                    },
                    json={"model": model, "input": spoken, "voice": provider_voice,
                          "response_format": "wav"}, timeout=120,
                )
                if r.status_code >= 400:
                    raise RuntimeError(f"Groq TTS HTTP {r.status_code}: {(r.text or '')[:320]}")
                if len(r.content) < 512:
                    raise RuntimeError("Groq TTS returned an empty/short audio body")
                wav = os.path.join(tmp, f"p{i:03d}.wav")
                mp3 = os.path.join(tmp, f"p{i:03d}.mp3")
                with open(wav, "wb") as f:
                    f.write(r.content)
                _audio_to_mp3(wav, mp3)
                parts.append(mp3)
            _concat_mp3(parts, out)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        dur = _mp3_len(out)
        if dur <= 0:
            raise RuntimeError("Groq Orpheus TTS produced unreadable audio")
        return {"audio": out, "words": [], "duration": dur,
                "engine": f"groq-tts:{model}"}


class GTTSFallback:
    name = "gtts"

    def synth(self, text: str, voice: str, out: str, rate: str = "+0%", **kwargs) -> dict:
        from gtts import gTTS
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        lang = "hi" if str(voice).startswith("hi-") else kwargs.get("language", "en") or "en"
        if "-" in lang:
            lang = lang.split("-")[0]
        gTTS(text=text, lang=lang, tld="co.in" if lang == "en" else "com").save(out)
        return {"audio": out, "words": [], "duration": _mp3_len(out), "engine": "gtts-last-resort"}


class MockProvider:
    name = "mock"

    def synth(self, text: str, voice: str, out: str, rate: str = "+0%", **kwargs) -> dict:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        tokens = text.split()
        dur = max(5.0, len(tokens) / 2.18)
        ff = _ffmpeg_bin()
        if not ff:
            raise RuntimeError("ffmpeg is required for mock narration")
        subprocess.run([ff, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                        "-t", str(round(dur, 2)), out], capture_output=True, check=True)
        per = dur / max(1, len(tokens))
        words = [{"word": t, "start": round(i * per, 3), "end": round((i + 1) * per, 3)}
                 for i, t in enumerate(tokens)]
        return {"audio": out, "words": words, "duration": dur, "engine": "mock-silent"}


class KokoroProvider:
    name = "kokoro"

    def synth(self, text: str, voice: str, out: str, rate: str = "+0%", **kwargs) -> dict:
        try:
            from kokoro import KPipeline
            import numpy as np
            import soundfile as sf
        except ImportError:
            raise RuntimeError("Kokoro not installed. Run: pip install 'kokoro>=0.9.4' soundfile")
        language = str(kwargs.get("language") or "en").lower()
        lang_code = {
            "en": "a", "en-us": "a", "en-in": "a", "en-gb": "b",
            "hi": "h", "es": "e", "fr": "f", "it": "i", "pt-br": "p",
            "ja": "j", "zh": "z",
        }.get(language, "a")
        provider_voice = kwargs.get("provider_voice") or os.getenv("KOKORO_VOICE", "af_heart")
        speed = float(os.getenv("KOKORO_SPEED", "1.0"))
        pipe = KPipeline(lang_code=lang_code)
        chunks = []
        for result in pipe(text, voice=provider_voice, speed=speed):
            # kokoro >=0.9 may return a Result object or legacy tuple.
            audio = getattr(result, "audio", None)
            if audio is None and isinstance(result, (tuple, list)) and len(result) >= 3:
                audio = result[2]
            if audio is None:
                continue
            if hasattr(audio, "detach"):
                audio = audio.detach().cpu().numpy()
            chunks.append(np.asarray(audio, dtype=np.float32).reshape(-1))
        if not chunks:
            raise RuntimeError("Kokoro returned no audio")
        audio = np.concatenate(chunks)
        wav = out + ".kokoro.wav"
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        sf.write(wav, audio, 24000)
        _audio_to_mp3(wav, out)
        try:
            os.remove(wav)
        except Exception:
            pass
        return {"audio": out, "words": [], "duration": _mp3_len(out), "engine": "kokoro-local"}


class ChatterboxProvider:
    name = "chatterbox"

    def synth(self, text, voice, out, rate="+0%", **kwargs):
        raise RuntimeError(
            "Chatterbox is GPU-heavy and optional. Install per README. "
            "Only use voice references you own or are authorized to use.")


def _kokoro_available() -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec("kokoro") is not None and importlib.util.find_spec("soundfile") is not None
    except Exception:
        return False


def synthesize_narration(text: str, voice: str, out: str, provider: str = "auto",
                         rate: str = "+0%", language: str = "en", style: str = "",
                         model: str = "", provider_voice: str = "") -> dict:
    """Synthesize narration with bounded provider fallback.

    ``auto`` is free-first and avoids gTTS until every higher-quality configured
    option has failed. Explicit provider selection is strict except ``edge``,
    which retains a final gTTS compatibility fallback.
    """
    p = str(provider or "auto").lower()
    from ..languages import language_pack, check_tts_language
    language = language_pack(language).code
    check_tts_language(p, language, voice)
    if language == 'or' and p == 'auto':
        if not os.getenv('GEMINI_API_KEY'):
            raise RuntimeError('Odia auto TTS needs a configured Gemini key/model or imported native narration; no English fallback will be used')
        p = 'gemini'
    kwargs = {"language": language, "style": style, "model": model or None,
              "provider_voice": provider_voice or None}
    providers = {
        "gemini": GeminiTTSProvider(False),
        "gemini-lite": GeminiTTSProvider(True),
        "elevenlabs": ElevenLabsTTSProvider(),
        "groq": GroqTTSProvider(),
        "kokoro": KokoroProvider(),
        "edge": EdgeTTSProvider(),
        "gtts": GTTSFallback(),
        "mock": MockProvider(),
        "chatterbox": ChatterboxProvider(),
    }
    if p != "auto":
        if p not in providers:
            raise RuntimeError(f"Unknown TTS provider: {provider}")
        if p == "edge":
            try:
                return providers[p].synth(text, voice, out, rate, **kwargs)
            except Exception as e:
                print(f"Edge TTS failed ({e}) -> gTTS last-resort fallback")
                return providers["gtts"].synth(text, voice, out, rate, **kwargs)
        return providers[p].synth(text, voice, out, rate, **kwargs)

    chain = []
    if os.getenv("GEMINI_API_KEY"):
        chain += ["gemini", "gemini-lite"]
    if (os.getenv("GROQ_API_KEY") and str(language or "en").lower().startswith("en")
            and "groq" not in _AUTO_DISABLED_PROVIDERS):
        chain.append("groq")
    if os.getenv("ELEVENLABS_API_KEY"):
        chain.append("elevenlabs")
    # Kokoro pulls a large local Torch/model stack. Keep it explicit on
    # storage-constrained laptops; cloud/Edge providers remain zero-install.
    # Users who intentionally installed it can opt into auto-routing with
    # AUTOVIDEO_ENABLE_LOCAL_TTS=1, or select --tts-provider kokoro directly.
    enable_local = str(os.getenv("AUTOVIDEO_ENABLE_LOCAL_TTS", "")).strip().lower() in {"1", "true", "yes", "on"}
    if enable_local and _kokoro_available():
        chain.append("kokoro")
    chain += ["edge", "gtts"]
    errors = []
    for name in chain:
        try:
            res = providers[name].synth(text, voice, out, rate, **kwargs)
            if name != chain[0] and errors:
                print(f"TTS recovered with {name} after: " + " | ".join(errors[-2:]))
            return res
        except Exception as e:
            if name == "groq" and "requires terms acceptance" in str(e).lower():
                _AUTO_DISABLED_PROVIDERS.add("groq")
                print("[TTS] Groq model terms have not been accepted; disabling Groq auto-routing "
                      "for the rest of this run. Edge fallback will be used without repeating this error.")
            errors.append(f"{name}: {str(e)[:110]}")
    raise RuntimeError("All narration providers failed: " + " | ".join(errors))


def _audio_to_mp3(src: str, out: str):
    ff = _ffmpeg_bin()
    if not ff:
        raise RuntimeError("ffmpeg is required to normalize TTS audio")
    subprocess.run([ff, "-y", "-i", src, "-codec:a", "libmp3lame", "-q:a", "3", out],
                   capture_output=True, timeout=180, check=True)


def _mp3_len(path: str) -> float:
    # Prefer ffprobe because it is stable across MoviePy 1.x/2.x environments.
    fp = shutil.which("ffprobe")
    if fp:
        try:
            r = subprocess.run([fp, "-v", "error", "-show_entries", "format=duration",
                                "-of", "default=noprint_wrappers=1:nokey=1", path],
                               capture_output=True, text=True, timeout=30)
            if r.returncode == 0 and (r.stdout or "").strip():
                return float(r.stdout.strip())
        except Exception:
            pass
    try:
        from moviepy.editor import AudioFileClip
        c = AudioFileClip(path)
        d = c.duration
        c.close()
        return d
    except Exception:
        pass
    ff = _ffmpeg_bin()
    if ff:
        try:
            r = subprocess.run([ff, "-i", path], capture_output=True, text=True, timeout=30)
            m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
            if m:
                return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        except Exception:
            pass
    return 0.0


def _ffmpeg_bin() -> str | None:
    ff = shutil.which("ffmpeg")
    if ff:
        return ff
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def fit_narration_to_target(voice_path: str, words: list[dict], target_sec: float,
                            max_rate: float = 1.08, tol: float = 0.06,
                            hard_trim: bool = False) -> tuple[list[dict], float]:
    """Apply only a small pitch-preserving timing correction.

    v4 could squeeze ~57 seconds into 45 seconds (1.25x+), which made gTTS sound
    particularly robotic. v5 caps automatic speed-up near natural speech. If a
    narration is much too long, the factory first asks the script director to
    retime/rewrite it and re-synthesizes; this function is the final small trim.
    """
    dur = _mp3_len(voice_path)
    if dur <= 0 or target_sec <= 0 or dur <= target_sec * (1 + tol):
        return words, dur
    rate = min(max(1.0, float(max_rate)), dur / target_sec)
    if rate <= 1.001:
        return words, dur
    ff = _ffmpeg_bin()
    if not ff:
        return words, dur
    tmp = voice_path + ".fit.mp3"
    try:
        subprocess.run([ff, "-y", "-i", voice_path, "-filter:a", f"atempo={rate:.3f}",
                        "-codec:a", "libmp3lame", "-q:a", "3", tmp],
                       capture_output=True, timeout=300, check=True)
        os.replace(tmp, voice_path)
    except Exception:
        return words, dur
    new_dur = _mp3_len(voice_path) or dur / rate
    words = [{**w, "start": round(float(w.get("start", 0)) / rate, 3),
              "end": round(float(w.get("end", 0)) / rate, 3)} for w in (words or [])]
    if hard_trim and new_dur > target_sec * (1 + tol):
        try:
            subprocess.run([ff, "-y", "-i", voice_path, "-t", f"{target_sec:.2f}",
                            "-codec:a", "libmp3lame", "-q:a", "3", tmp],
                           capture_output=True, timeout=300, check=True)
            os.replace(tmp, voice_path)
            words = [w for w in words if float(w.get("start", 0)) < target_sec]
            new_dur = float(target_sec)
        except Exception:
            pass
    return words, round(float(new_dur), 2)


def _concat_mp3(parts: list[str], out: str):
    ff = _ffmpeg_bin()
    if ff and len(parts) > 1:
        lst = out + ".lst"
        with open(lst, "w", encoding="utf-8") as f:
            for p in parts:
                f.write(f"file '{os.path.abspath(p)}'\n")
        subprocess.run([ff, "-y", "-f", "concat", "-safe", "0", "-i", lst,
                        "-c", "copy", out], capture_output=True, check=True)
        os.remove(lst)
    elif len(parts) == 1:
        shutil.copy(parts[0], out)
    else:
        raise RuntimeError("No TTS audio chunks were produced")
