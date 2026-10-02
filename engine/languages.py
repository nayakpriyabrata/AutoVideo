"""Explicit English/Hindi/Odia language packs; never silently speak another language."""
from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True)
class LanguagePack:
    code: str
    locale: str
    label: str
    font_family: str
    font_file: str
    words_per_second: float
    edge_voice: str | None


LANGUAGES = {
    'en': LanguagePack('en', 'en-IN', 'English', 'DejaVu Sans', '', 2.45, 'en-IN-PrabhatNeural'),
    'hi': LanguagePack('hi', 'hi-IN', 'Hindi', 'Noto Sans Devanagari', 'NotoSansDevanagari-Variable.ttf', 2.25, 'hi-IN-MadhurNeural'),
    'or': LanguagePack('or', 'or-IN', 'Odia', 'Noto Sans Oriya', 'NotoSansOriya-Variable.ttf', 2.10, None),
}


def language_pack(value='en'):
    code = str(value or 'en').lower().replace('_', '-').split('-')[0]
    code = {'odia':'or', 'oriya':'or', 'english':'en', 'hindi':'hi'}.get(code, code)
    if code not in LANGUAGES:
        raise ValueError('Supported languages are English (en), Hindi (hi) and Odia (or)')
    return LANGUAGES[code]


def script_language(text):
    if any('\u0b00' <= c <= '\u0b7f' for c in str(text)):
        return 'or'
    if any('\u0900' <= c <= '\u097f' for c in str(text)):
        return 'hi'
    return 'en'


def text_tokens(text):
    """Unicode words retaining Indic combining marks; no ASCII-only keyword gate."""
    normalized = unicodedata.normalize('NFC', str(text))
    return [word for word in re.findall(r'\S+', normalized) if any(c.isalnum() for c in word)]


def default_voice(language):
    return language_pack(language).edge_voice or 'gemini-native-odia'


def check_tts_language(provider, language, voice=''):
    code = language_pack(language).code
    if code == 'or' and provider not in ('auto', 'gemini', 'gemini-lite', 'import', 'mock'):
        raise ValueError('Odia requires a verified Gemini TTS model or an imported native narration; this provider has not been validated for Odia')
    if code == 'hi' and provider == 'groq':
        raise ValueError('The configured Groq TTS route is English-only; choose a Hindi-capable provider')
    if provider == 'edge' and code in ('en', 'hi') and voice and not voice.startswith(code+'-'):
        raise ValueError('Selected Edge voice does not match the narration language')
