"""Audio: TTS providers with word timing, alignment fallback, sound design."""
from .tts import synthesize_narration, EdgeTTSProvider, GTTSFallback

__all__ = ["synthesize_narration", "EdgeTTSProvider", "GTTSFallback"]
