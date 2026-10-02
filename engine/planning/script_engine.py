"""LLM-backed script director for AutoVideoAI v5.

Free-first provider routing:
  Gemini API -> Gemini Web (optional) -> Groq -> Ollama -> OpenAI -> xAI/Grok -> deterministic planner.

The module deliberately uses HTTP APIs through ``requests`` so the core build
has no mandatory vendor SDK dependency. API providers are optional and selected
only when their key is present.
"""
from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from typing import Any

import requests

NATURAL_WORDS_PER_SEC = 2.18


class ScriptProviderError(RuntimeError):
    """Explicitly requested script provider is unavailable or failed."""


class ScriptQualityError(RuntimeError):
    """AI returned a script that still fails publish-quality editorial checks."""



def _is_rate_limited(exc: Exception) -> bool:
    """Return True when a provider failure is an HTTP 429/rate-limit response."""
    resp = getattr(exc, "response", None)
    if resp is not None and getattr(resp, "status_code", None) == 429:
        return True
    msg = str(exc).lower()
    return "429" in msg and ("too many requests" in msg or "rate limit" in msg or "rate-limit" in msg)


def _rate_limit_message(provider: str) -> str:
    return (
        f"{provider} is rate-limited (HTTP 429). "
        "Use --script-provider auto to fail over to another configured AI writer, "
        "or wait for the provider quota/rate window to reset."
    )

_LIST_RE = re.compile(
    r"\b(?P<count>[2-9]|1[0-9]|20)\s+(?P<kind>habits?|tips?|mistakes?|ways?|lessons?|steps?|rules?|principles?|secrets?|ideas?|reasons?|signs?)\b",
    re.I,
)
_ORDINAL_WORDS = [
    "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth",
    "eleventh", "twelfth", "thirteenth", "fourteenth", "fifteenth", "sixteenth", "seventeenth", "eighteenth", "nineteenth", "twentieth",
]
_CARDINAL_WORDS = [
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty",
]


def detect_list_topic(topic: str) -> dict | None:
    """Detect title promises such as '5 habits', '7 mistakes', or '10 tips'."""
    m = _LIST_RE.search(str(topic or ""))
    if not m:
        return None
    count = int(m.group("count"))
    kind = m.group("kind").lower()
    singular = kind[:-1] if kind.endswith("s") else kind
    return {"count": count, "kind": kind, "singular": singular, "match": m.group(0)}


def _topic_phrase_count(text: str, topic: str) -> int:
    phrase = re.sub(r"[^a-z0-9 ]+", " ", str(topic or "").lower())
    phrase = re.sub(r"\s+", " ", phrase).strip()
    body = re.sub(r"[^a-z0-9 ]+", " ", str(text or "").lower())
    body = re.sub(r"\s+", " ", body).strip()
    return body.count(phrase) if phrase and len(phrase.split()) >= 3 else 0



def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    raw = text.strip()
    # Strip Markdown fences without assuming a provider obeyed JSON mode.
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(raw[start:end + 1])
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
    return None


def _provider_available(provider: str) -> bool:
    p = provider.lower()
    if p == "gemini":
        return bool(os.getenv("GEMINI_API_KEY"))
    if p == "gemini-web":
        # Explicit gemini-web is always launchable; auto mode includes it only when enabled.
        return True
    if p == "groq":
        return bool(os.getenv("GROQ_API_KEY"))
    if p == "openai":
        return bool(os.getenv("OPENAI_API_KEY"))
    if p in ("grok", "xai"):
        return bool(os.getenv("XAI_API_KEY"))
    if p == "ollama":
        try:
            return requests.get(os.getenv("OLLAMA_BASE_URL", "http://localhost:11434") + "/api/tags", timeout=1.5).ok
        except Exception:
            return False
    return p == "planner"


def auto_provider_order() -> list[str]:
    # Browser Gemini is opt-in for auto mode because it opens a visible persistent
    # browser. Explicit --script-provider gemini-web always works without this flag.
    order = ["gemini"]
    if str(os.getenv("AUTOVIDEO_ENABLE_GEMINI_WEB", "0")).lower() in {"1", "true", "yes", "on"}:
        order.append("gemini-web")
    order += ["groq", "ollama", "openai", "grok"]
    return order


def _default_model(provider: str) -> str:
    p = provider.lower()
    if p == "gemini":
        return os.getenv("GEMINI_SCRIPT_MODEL", "gemini-3.8-flash")
    if p == "gemini-web":
        return os.getenv("GEMINI_WEB_SCRIPT_MODEL", "gemini-web")
    if p == "groq":
        return os.getenv("GROQ_SCRIPT_MODEL", "openai/gpt-oss-120b")
    if p == "openai":
        return os.getenv("OPENAI_SCRIPT_MODEL", "gpt-6-luna")
    if p in ("grok", "xai"):
        return os.getenv("XAI_SCRIPT_MODEL", "grok-4-fast")
    if p == "ollama":
        return os.getenv("OLLAMA_SCRIPT_MODEL", "llama3.2")
    return "planner"


def _chat_prompt(topic: str, content_type: str, duration_sec: int, tone: str,
                 language: str, target_words: int, quality: str) -> tuple[str, str]:
    list_spec = detect_list_topic(topic)
    system = (
        "You are the senior script director for a publish-ready faceless YouTube channel. "
        "Write for natural spoken delivery, not an essay. Return ONLY valid JSON. "
        "Never invent unverifiable statistics, quotations, studies, or current-news facts. "
        "Never keyword-stuff the title. Never drift into unrelated domains merely to fill runtime. "
        "Every paragraph must earn its place by advancing the viewer's promised outcome."
    )
    structure = ""
    if list_spec:
        n, singular = list_spec["count"], list_spec["singular"]
        structure = f"""
This is a LIST-PROMISE title. The viewer was promised exactly {n} {list_spec['kind']}.
- Return EXACTLY {n} objects in beats. Beats are the {n} promised items only; do not add hook/outro as beats.
- Name them clearly like "{singular.title()} 1: <short actionable title>" through "{singular.title()} {n}: ...".
- The narration must explicitly walk through all {n} items in order so a listener can identify each one.
- Give each item a concrete action/example and a distinct visual_intent.
- Do not repeat the full title phrase more than twice in the entire narration. Use natural pronouns/synonyms after the hook.
- Do not mention software, automation, workflows, managers, delegation, APIs, or engineering unless the topic itself is about those subjects.
"""
    user = f"""
Create a complete narration plan.
Topic: {topic}
Content type: {content_type}
Tone: {tone}
Language: {language}
Target runtime: {duration_sec} seconds
Target narration length: {target_words} words (acceptable range {max(40,target_words-12)}-{target_words+12})
Quality mode: {quality}
{structure}
Requirements:
- Hook must land in the first 2-3 seconds and make a specific promise without clickbait filler.
- Natural spoken sentences, varied rhythm, concise clauses.
- One clear idea per beat; each beat must suggest a visually distinct scene family.
- Use practical, concrete examples. For self-improvement, prefer everyday actions over abstract slogans.
- No fake facts. If the topic is general/self-improvement, use reasoning/examples rather than pretending to cite research.
- Avoid clichés such as: "here's the truth", "your future self", "start today", "stay consistent", "game changer", "this changes everything".
- Do not mechanically repeat the topic wording.
- End with a concise natural takeaway and, for normal YouTube educational content, a soft CTA that invites one specific comment or subscription action.
- The narration must sound like one coherent human voice when read aloud.

Return this exact JSON shape:
{{
  "angle": "specific creative angle",
  "audience": "target audience",
  "hook": "opening line",
  "hooks": ["alt hook 1", "alt hook 2", "alt hook 3"],
  "beats": [
    {{"name":"short beat name", "text":"one concise 1-sentence summary of this beat (do NOT duplicate the full narration)", "visual_intent":"specific thing to show", "emotion":"delivery emotion"}}
  ],
  "narration": "full final narration, including the hook and CTA",
  "cta": "short natural CTA",
  "cta_kind": "soft"
}}
""".strip()
    return system, user


def _gemini(system: str, user: str, model: str) -> str:
    key = os.environ["GEMINI_API_KEY"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "temperature": 0.72,
            "responseMimeType": "application/json",
            "maxOutputTokens": 4096,
        },
    }
    r = requests.post(url, json=payload, timeout=90)
    r.raise_for_status()
    data = r.json()
    return data["candidates"][0]["content"]["parts"][0].get("text", "")


def _openai_compatible(base_url: str, key: str, model: str, system: str, user: str,
                       provider: str) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": 0.7,
        # Long-form publish scripts contain hundreds of narration words plus
        # structural metadata.  Leaving this unset let some OpenAI-compatible
        # providers return a short/incomplete JSON object even though the HTTP
        # call itself succeeded.  Keep a generous ceiling; the provider still
        # stops naturally when the JSON is complete.
        "max_completion_tokens": int(os.getenv("SCRIPT_MAX_OUTPUT_TOKENS", "8192")),
    }
    # JSON object mode is supported by Groq GPT-OSS and by modern OpenAI-style APIs.
    payload["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    endpoint = base_url.rstrip("/") + "/chat/completions"
    r = requests.post(endpoint, headers=headers, json=payload, timeout=120)
    if r.status_code >= 400:
        # Compatibility retry.  Some OpenAI-compatible providers expose JSON
        # mode but not ``max_completion_tokens`` (or vice-versa).  Remove only
        # optional controls; never alter the requested provider/model.
        retry = dict(payload)
        changed = False
        if "response_format" in retry:
            retry.pop("response_format", None)
            changed = True
        if "max_completion_tokens" in retry:
            retry["max_tokens"] = retry.pop("max_completion_tokens")
            changed = True
        if changed:
            r = requests.post(endpoint, headers=headers, json=retry, timeout=120)
    r.raise_for_status()
    data = r.json()
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    content = msg.get("content", "") or ""
    return content


def _ollama(system: str, user: str, model: str) -> str:
    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "options": {"temperature": 0.7},
    }
    r = requests.post(base + "/api/chat", json=payload, timeout=120)
    r.raise_for_status()
    return (r.json().get("message") or {}).get("content", "")


def _call_provider(provider: str, model: str, system: str, user: str) -> str:
    p = provider.lower()
    if p == "gemini":
        return _gemini(system, user, model)
    if p == "gemini-web":
        from ..providers.gemini_web import (
            GeminiWebAuthNeeded, GeminiWebComposerNotReady, gemini_web_generate,
        )
        try:
            return gemini_web_generate(system, user, model)
        except (GeminiWebAuthNeeded, GeminiWebComposerNotReady) as exc:
            # These failures happen before prompt submission and cannot improve
            # by creating two more fresh chats. Surface the actionable UI state
            # instead of spending the quality-mode retry budget on the same
            # unavailable composer/session.
            raise ScriptProviderError(f"Gemini Web is not ready: {exc}") from exc
    if p == "groq":
        return _openai_compatible("https://api.groq.com/openai/v1",
                                  os.environ["GROQ_API_KEY"], model, system, user, p)
    if p == "openai":
        return _openai_compatible("https://api.openai.com/v1",
                                  os.environ["OPENAI_API_KEY"], model, system, user, p)
    if p in ("grok", "xai"):
        return _openai_compatible("https://api.x.ai/v1",
                                  os.environ["XAI_API_KEY"], model, system, user, p)
    if p == "ollama":
        return _ollama(system, user, model)
    raise RuntimeError(f"Unsupported script provider: {provider}")



def _is_word_count_flag(flag: str) -> bool:
    return str(flag or "").lower().startswith("word count ")


def _length_repair_prompt(plan: dict, topic: str, content_type: str, duration_sec: int,
                          tone: str, language: str, target_words: int) -> tuple[str, str]:
    """Repair only narration length while preserving a good existing draft."""
    narration = str(plan.get("narration", "") or "").strip()
    current_words = len(narration.split())
    delta = target_words - current_words
    spec = detect_list_topic(topic)
    list_rule = ""
    if spec:
        list_rule = (
            f"Preserve exactly {spec['count']} promised {spec['kind']} in the same order. "
            "Do not add another item or merge two items together."
        )
    direction = (
        f"EXPAND by about {max(0, delta)} words" if delta > 0
        else f"TRIM by about {abs(delta)} words"
    )
    system = (
        "You are a precision YouTube narration length editor. Return ONLY valid JSON with keys "
        "narration and cta. Preserve the existing script's meaning, structure, hook, and voice. "
        "Do not replace a good draft with a different concept merely to hit length."
    )
    user = f"""
The script below is editorially useful but the runtime length is wrong.
Topic: {topic}
Content type: {content_type}
Runtime target: {duration_sec} seconds
Tone: {tone}
Language: {language}
Current word count: {current_words}
Required final range: {max(50,target_words-18)}-{target_words+18} words
Task: {direction}.
{list_rule}

Rules for expansion:
- Keep every useful existing idea.
- Add concrete examples, implementation details, brief consequences, and natural transitions INSIDE the existing beats.
- Distribute added words across the whole script instead of bloating one paragraph.
- Never add unrelated filler, fabricated facts, generic motivation, keyword stuffing, software/workflow jargon, or repeated conclusions.
- Keep the CTA short.

Rules for trimming:
- Remove repetition and low-value wording before removing examples or meaning.
- Never cut a promised list item.

EXISTING NARRATION:
{narration}

CTA:
{plan.get('cta', '')}

Return exactly:
{{"narration":"revised full narration","cta":"short natural CTA"}}
""".strip()
    return system, user


def _repair_length_same_provider(plan: dict, provider: str, model: str, topic: str,
                                 content_type: str, duration_sec: int, tone: str,
                                 language: str, target_words: int, max_passes: int = 2) -> dict:
    """Converge a coherent narration toward target length without discarding it."""
    best = dict(plan)
    best_gap = abs(len(str(best.get("narration", "")).split()) - target_words)
    for idx in range(max(1, int(max_passes))):
        current_words = len(str(best.get("narration", "")).split())
        if abs(current_words - target_words) <= max(18, int(target_words * 0.06)):
            break
        print(
            f"[Script] {provider} returned {current_words}/{target_words} words; "
            f"repairing the same narration for runtime length (pass {idx+1}/{max_passes})..."
        )
        system, user = _length_repair_prompt(
            best, topic, content_type, duration_sec, tone, language, target_words
        )
        try:
            raw = _call_provider(provider, model, system, user)
            obj = _extract_json(raw)
        except Exception as error:
            print(f"[Script] Length repair unavailable ({type(error).__name__}); "
                  "retaining the existing draft for editorial and runtime checks.")
            break
        if not isinstance(obj, dict) or not str(obj.get("narration", "")).strip():
            print("[Script] Length repair returned no narration; retaining the existing draft.")
            break
        merged = dict(best)
        merged["narration"] = obj.get("narration", "")
        merged["cta"] = obj.get("cta") or best.get("cta", "")
        candidate = _normalize_plan(
            merged, topic, content_type, target_words,
            f"{provider}:{model}+length-repair"
        )
        if not candidate:
            continue
        gap = abs(len(candidate["narration"].split()) - target_words)
        if gap < best_gap:
            best, best_gap = candidate, gap
        else:
            print("[Script] Length repair made no improvement; keeping the best draft "
                  "for editorial and measured TTS checks.")
            break
    return best

def _normalize_plan(obj: dict, topic: str, content_type: str, target_words: int,
                    source: str) -> dict | None:
    narration = re.sub(r"\s+", " ", str(obj.get("narration", "") or "")).strip()
    if len(narration.split()) < max(35, int(target_words * 0.62)):
        return None
    beats_in = obj.get("beats") or []
    beats = []
    if isinstance(beats_in, list):
        for i, b in enumerate(beats_in):
            if isinstance(b, dict):
                text = re.sub(r"\s+", " ", str(b.get("text", "") or "")).strip()
                if text:
                    beats.append({
                        "name": str(b.get("name") or f"beat_{i+1}"),
                        "text": text,
                        "visual_intent": str(b.get("visual_intent") or ""),
                        "emotion": str(b.get("emotion") or ""),
                    })
    if not beats:
        # Derive visual beats from the actual narration, rather than throwing away
        # an otherwise good provider response.
        sents = [x.strip() for x in re.split(r"(?<=[.!?])\s+", narration) if x.strip()]
        beats = [{"name": f"beat_{i+1}", "text": s,
                  "visual_intent": "", "emotion": ""} for i, s in enumerate(sents[:10])]
    hook = re.sub(r"\s+", " ", str(obj.get("hook", "") or "")).strip()
    if not hook:
        hook = beats[0]["text"] if beats else narration.split(".")[0].strip() + "."
    hooks = obj.get("hooks") if isinstance(obj.get("hooks"), list) else []
    hooks = [str(x).strip() for x in hooks if str(x).strip()][:5]
    if hook and hook not in hooks:
        hooks.insert(0, hook)
    return {
        "angle": str(obj.get("angle") or f"{content_type}: {topic}"),
        "audience": str(obj.get("audience") or "general 18-44"),
        "hooks": hooks or [hook],
        "hook": hook,
        "beats": beats,
        "narration": narration,
        "words": len(narration.split()),
        "cta": str(obj.get("cta") or ""),
        "cta_kind": str(obj.get("cta_kind") or "none"),
        "source": source,
    }


def _quality_flags(plan: dict, target_words: int, topic: str = "",
                   content_type: str = "education", duration_sec: int = 0) -> list[str]:
    text = re.sub(r"\s+", " ", str(plan.get("narration") or "")).strip().lower()
    flags: list[str] = []
    words = len(text.split())
    tolerance = max(12, int(target_words * 0.035))
    if words < target_words - tolerance or words > target_words + tolerance:
        flags.append(f"word count {words}, target {target_words}")
    cliches = ["here's the truth", "your future self", "start today", "stay consistent",
               "game changer", "this changes everything"]
    present = [x for x in cliches if x in text]
    if present:
        flags.append("cliches: " + ", ".join(present))
    sents = [re.sub(r"\W+", " ", x.lower()).strip() for x in re.split(r"[.!?]+", text)]
    seen = set()
    if any(x and len(x.split()) >= 5 and (x in seen or seen.add(x)) for x in sents):
        flags.append("repeated sentence")
    repeats = _topic_phrase_count(text, topic)
    if repeats > 2:
        flags.append(f"keyword stuffing: full topic phrase repeated {repeats} times")

    list_spec = detect_list_topic(topic)
    beats = list(plan.get("beats") or [])
    if list_spec:
        n = list_spec["count"]
        if len(beats) != n:
            flags.append(f"list promise requires exactly {n} beats, got {len(beats)}")
        names = [str(b.get("name", "")).strip().lower() for b in beats if isinstance(b, dict)]
        if len(set(names)) != len(names):
            flags.append("list beat titles are not unique")
        # Require each promised item to be visibly enumerable in the narration.
        hits = 0
        for i in range(1, n + 1):
            ordinal = _ORDINAL_WORDS[i-1] if i <= len(_ORDINAL_WORDS) else str(i)
            cardinal = _CARDINAL_WORDS[i-1] if i <= len(_CARDINAL_WORDS) else str(i)
            patterns = [rf"\b{re.escape(list_spec['singular'])}\s+{i}\b",
                        rf"\b{re.escape(list_spec['singular'])}\s+{cardinal}\b",
                        rf"\b{re.escape(list_spec['singular'])}\s+{ordinal}\b",
                        rf"\b{ordinal}\s+{re.escape(list_spec['singular'])}\b",
                        rf"\bnumber\s+{i}\b",
                        rf"\b{ordinal}\b"]
            if any(re.search(p, text) for p in patterns):
                hits += 1
        if hits < max(1, n - 1):
            flags.append(f"list narration does not clearly enumerate all {n} promised items")

    tech_topic = bool(re.search(r"\b(ai|software|automation|workflow|api|coding|developer|manager|business|engineering|tech)\b",
                                str(topic or "").lower()))
    if not tech_topic:
        drift_terms = ["automation", "workflow", "manager", "delegation", "delegate",
                       "software pipeline", "orchestrating systems", "api"]
        bad = []
        for term in drift_terms:
            pat = r"\b" + r"\s+".join(re.escape(x) for x in term.split()) + r"s?\b"
            if re.search(pat, text):
                bad.append(term)
        if bad:
            flags.append("off-topic technical/workflow drift: " + ", ".join(sorted(set(bad))))

    # Long educational/list videos should not end without a clear takeaway.
    if duration_sec >= 45 and content_type not in {"storytelling", "cinematic_story", "kids_story"}:
        cta = str(plan.get("cta") or "").strip()
        if not cta:
            flags.append("missing natural closing CTA")
    return flags


def script_quality_report(plan: dict, topic: str, content_type: str,
                          duration_sec: int, target_words: int | None = None) -> dict:
    tw = target_words or max(50, int(round(duration_sec * NATURAL_WORDS_PER_SEC)))
    flags = _quality_flags(plan, tw, topic, content_type, duration_sec)
    return {
        "passed": not flags,
        "flags": flags,
        "topic": topic,
        "target_words": tw,
        "actual_words": len(str(plan.get("narration") or "").split()),
        "source": str(plan.get("source") or "unknown"),
        "list_spec": detect_list_topic(topic),
    }


def _critic_prompt(plan: dict, topic: str, duration_sec: int, target_words: int,
                   flags: list[str]) -> tuple[str, str]:
    list_spec = detect_list_topic(topic)
    structure = ""
    if list_spec:
        structure = (f" Preserve EXACTLY {list_spec['count']} main beats matching the title promise. "
                     "Keep them clearly numbered/named and make every item actionable.")
    system = (
        "You are a ruthless YouTube spoken-script editor. Return ONLY valid JSON in the same shape. "
        "Preserve factual scope while fixing every detected issue. Never add unrelated filler." + structure
    )
    user = f"""
Edit this narration plan for a {duration_sec}-second faceless video about {topic}.
Final narration must be {max(40,target_words-10)}-{target_words+10} words.
Problems detected: {', '.join(flags) if flags else 'final publish-quality polish requested'}.
Remove keyword stuffing, generic filler, clichés, repetition, topic drift, and essay-like phrasing.
Use concrete everyday examples and natural transitions.
Every beat should be visually distinct and its text should be spoken narration, not production notes.
Do not repeat the full topic phrase more than twice.

PLAN:
{json.dumps(plan, ensure_ascii=False)}
""".strip()
    return system, user



def _incomplete_plan_diagnostic(obj: dict | None, raw: str, target_words: int) -> str:
    """Short safe diagnostic for malformed/truncated provider output.

    Never includes the actual script text or API secrets; only shape/size data.
    """
    keys = sorted(obj.keys()) if isinstance(obj, dict) else []
    narration = str((obj or {}).get("narration", "") or "") if isinstance(obj, dict) else ""
    return (f"chars={len(raw or '')}, keys={keys[:12]}, "
            f"narration_words={len(narration.split())}, target_words={target_words}")


def _outline_prompt(topic: str, content_type: str, duration_sec: int, tone: str,
                    language: str, quality: str) -> tuple[str, str]:
    """Small JSON outline request used for long-form scripts.

    Long-form one-shot JSON used to duplicate hundreds of narration words in
    both ``beats[].text`` and ``narration``.  Groq could therefore return a
    syntactically valid but incomplete object.  The outline pass deliberately
    stays compact; narration is generated separately.
    """
    spec = detect_list_topic(topic)
    system = (
        "You are the senior YouTube story editor. Return ONLY a compact valid JSON outline. "
        "Do not write the full narration yet. Never keyword-stuff or drift off topic."
    )
    if spec:
        structure = (
            f"Return EXACTLY {spec['count']} beats because the title promises {spec['count']} {spec['kind']}. "
            f"Name them '{spec['singular'].title()} 1: ...' through "
            f"'{spec['singular'].title()} {spec['count']}: ...'."
        )
    else:
        structure = "Return 5-8 distinct beats appropriate to the topic and runtime."
    user = f"""
Build a publish-quality outline.
Topic: {topic}
Content type: {content_type}
Runtime: {duration_sec} seconds
Tone: {tone}
Language: {language}
Quality: {quality}
{structure}
Requirements:
- Hook: one specific spoken opening line.
- Every beat must be concrete, non-overlapping, actionable, and visually distinct.
- Beat text is only a 1-sentence summary (roughly 10-25 words), not full narration.
- For non-technical topics, do not mention automation, workflows, managers, APIs, software pipelines, delegation, or engineering.
- CTA: one short natural YouTube CTA.
Return exactly this JSON shape:
{{
  "angle":"specific angle",
  "audience":"target audience",
  "hook":"opening line",
  "hooks":["alt hook 1","alt hook 2","alt hook 3"],
  "beats":[
    {{"name":"beat title","text":"one-sentence beat summary","visual_intent":"specific visual","emotion":"delivery emotion"}}
  ],
  "cta":"short CTA",
  "cta_kind":"soft"
}}
""".strip()
    return system, user


def _narration_prompt(outline: dict, topic: str, content_type: str, duration_sec: int,
                      tone: str, language: str, target_words: int,
                      problems: list[str] | None = None) -> tuple[str, str]:
    """Narration-only request: small JSON envelope, no duplicated beat prose."""
    spec = detect_list_topic(topic)
    system = (
        "You are a publish-ready YouTube narration writer. Return ONLY valid JSON with keys "
        "narration and cta. Write natural spoken English, not an essay. Never add unrelated filler."
    )
    list_rule = ""
    if spec:
        list_rule = (
            f"The narration MUST clearly walk through exactly {spec['count']} {spec['kind']} in order. "
            f"Use natural markers such as '{spec['singular'].title()} 1', 'Habit two', 'Third', etc. "
            "Do not repeat the full video title more than twice."
        )
    repair = ""
    if problems:
        repair = "Fix these problems from the prior draft: " + "; ".join(problems) + "."
    # Only send compact outline fields, never an earlier full narration.
    compact = {
        "angle": outline.get("angle", ""),
        "audience": outline.get("audience", ""),
        "hook": outline.get("hook", ""),
        "beats": outline.get("beats", []),
        "cta": outline.get("cta", ""),
    }
    user = f"""
Write the COMPLETE narration for this outline.
Topic: {topic}
Content type: {content_type}
Runtime: {duration_sec} seconds
Tone: {tone}
Language: {language}
Target length: {max(50,target_words-12)}-{target_words+12} words.
{list_rule}
{repair}
Requirements:
- Start with the outline hook or a stronger equivalent in the first 2-3 seconds.
- Keep each promised beat distinct and actionable, with one concrete everyday example.
- Use transitions that sound natural when spoken aloud.
- No keyword stuffing, clichés, essay filler, fabricated statistics, or topic drift.
- End with a concise takeaway and the outline CTA.
OUTLINE:
{json.dumps(compact, ensure_ascii=False)}
Return exactly:
{{"narration":"full final narration","cta":"short natural CTA"}}
""".strip()
    return system, user


def _generate_longform_two_stage(provider: str, model: str, topic: str,
                                 content_type: str, duration_sec: int, tone: str,
                                 language: str, target_words: int, quality: str,
                                 problems: list[str] | None = None) -> tuple[dict | None, str]:
    """Reliable long-form generation without duplicating narration in JSON.

    Returns ``(plan, diagnostic)``.  It always stays on the same requested AI
    provider; this is not a planner fallback.
    """
    osys, ouser = _outline_prompt(topic, content_type, duration_sec, tone, language, quality)
    raw_outline = _call_provider(provider, model, osys, ouser)
    outline = _extract_json(raw_outline)
    if not isinstance(outline, dict) or not isinstance(outline.get("beats"), list):
        return None, "outline invalid: " + _incomplete_plan_diagnostic(outline, raw_outline, target_words)

    # Structural list promise is validated before asking for the expensive long narration.
    spec = detect_list_topic(topic)
    if spec and len(outline.get("beats") or []) != spec["count"]:
        return None, f"outline returned {len(outline.get('beats') or [])} beats; expected {spec['count']}"

    nsys, nuser = _narration_prompt(outline, topic, content_type, duration_sec,
                                    tone, language, target_words, problems)
    raw_narr = _call_provider(provider, model, nsys, nuser)
    narr_obj = _extract_json(raw_narr)
    if not isinstance(narr_obj, dict) or not str(narr_obj.get("narration", "")).strip():
        return None, "narration invalid: " + _incomplete_plan_diagnostic(narr_obj, raw_narr, target_words)

    merged = dict(outline)
    merged["narration"] = narr_obj.get("narration", "")
    merged["cta"] = narr_obj.get("cta") or outline.get("cta", "")
    merged["cta_kind"] = outline.get("cta_kind", "soft")
    plan = _normalize_plan(merged, topic, content_type, target_words,
                           f"{provider}:{model}+two-stage")
    if not plan:
        return None, "merged plan incomplete: " + _incomplete_plan_diagnostic(merged, json.dumps(merged), target_words)
    return plan, ""

def generate_script_plan(topic: str, content_type: str, duration_sec: int,
                         tone: str, language: str, provider: str = "auto",
                         model: str = "auto", quality: str = "high",
                         target_words: int | None = None) -> dict | None:
    from ..languages import language_pack
    pack = language_pack(language)
    rate = NATURAL_WORDS_PER_SEC if pack.code == 'en' else pack.words_per_second
    target_words = target_words or max(50, int(round(duration_sec * rate)))
    requested = (provider or "auto").lower()
    qmode = str(quality or "high").lower()
    publish = qmode == "publish"
    providers = auto_provider_order() if requested == "auto" else [requested]
    errors: list[str] = []
    available = [p for p in providers if p != "planner" and _provider_available(p)]
    if requested not in ("auto", "planner") and not available:
        raise ScriptProviderError(
            f"Requested script provider '{requested}' is unavailable. Configure its API key/service; "
            "AutoVideoAI will not silently replace an explicitly requested AI writer with the planner."
        )
    if requested == "planner":
        return None
    if publish and not available:
        raise ScriptProviderError(
            "Publish-quality script generation requires an available AI writer (Gemini API/Web, Groq, OpenAI, Grok, or Ollama)."
        )

    # Long-form publish JSON used to be unreliable because the provider had to
    # duplicate hundreds of narration words inside beats and again inside the
    # narration field.  v5.4.1 uses outline -> narration by default for >=2 min.
    prefer_two_stage = duration_sec >= 120 or target_words >= 300

    for p in providers:
        if p == "planner" or not _provider_available(p):
            continue
        mdl = _default_model(p) if not model or model == "auto" else model
        rejection_context = ""
        attempts = 3 if qmode in {"high", "publish"} else 2

        for attempt in range(1, attempts + 1):
            try:
                plan = None
                # For long form, make the reliable compact two-stage route the
                # primary path.  On subsequent attempts feed QC failures back
                # into the narration pass while preserving the outline structure.
                if prefer_two_stage:
                    problems = [rejection_context] if rejection_context else None
                    plan, diag = _generate_longform_two_stage(
                        p, mdl, topic, content_type, duration_sec, tone,
                        language, target_words, quality, problems=problems,
                    )
                    if not plan:
                        raise RuntimeError(diag or "two-stage provider output was incomplete")
                else:
                    system, user = _chat_prompt(topic, content_type, duration_sec, tone,
                                                language, target_words, quality)
                    if rejection_context:
                        user += ("\n\nPrevious draft was rejected for: " + rejection_context +
                                 "\nWrite a genuinely new corrected draft.")
                    raw = _call_provider(p, mdl, system, user)
                    obj = _extract_json(raw)
                    plan = _normalize_plan(obj or {}, topic, content_type, target_words, f"{p}:{mdl}")
                    if not plan:
                        raise RuntimeError(
                            "provider returned incomplete narration JSON (" +
                            _incomplete_plan_diagnostic(obj, raw, target_words) + ")"
                        )

                flags = _quality_flags(plan, target_words, topic, content_type, duration_sec)

                # v5.5.3: if the browser LLM wrote a coherent but short/long
                # narration, preserve it and repair that same draft before
                # opening another unrelated generation attempt.
                if any(_is_word_count_flag(f) for f in flags):
                    try:
                        plan = _repair_length_same_provider(
                            plan, p, mdl, topic, content_type, duration_sec,
                            tone, language, target_words, max_passes=2,
                        )
                        flags = _quality_flags(
                            plan, target_words, topic, content_type, duration_sec)
                    except Exception as length_error:
                        errors.append(
                            f"{p}:length-repair:{type(length_error).__name__}:"
                            f"{str(length_error)[:140]}"
                        )

                if qmode == "standard":
                    plan["editorial_qc"] = script_quality_report(
                        plan, topic, content_type, duration_sec, target_words)
                    return plan

                # If the draft already passes deterministic editorial QC, do
                # not make it fail merely because an optional critic response is
                # malformed.  Publish mode still *tries* a compact polish pass,
                # but the known-good draft remains a safe fallback.
                if not flags:
                    if publish:
                        try:
                            nsys, nuser = _narration_prompt(
                                plan, topic, content_type, duration_sec, tone,
                                language, target_words,
                                problems=["final publish-quality polish only; preserve structure and meaning"],
                            )
                            raw_polish = _call_provider(p, mdl, nsys, nuser)
                            pobj = _extract_json(raw_polish)
                            if isinstance(pobj, dict) and str(pobj.get("narration", "")).strip():
                                merged = dict(plan)
                                merged["narration"] = pobj.get("narration", "")
                                merged["cta"] = pobj.get("cta") or plan.get("cta", "")
                                polished = _normalize_plan(
                                    merged, topic, content_type, target_words,
                                    f"{p}:{mdl}+publish-polish")
                                if polished and not _quality_flags(
                                        polished, target_words, topic, content_type, duration_sec):
                                    plan = polished
                        except Exception:
                            # Optional polish cannot invalidate a draft that has
                            # already passed all publish gates.
                            pass
                    plan["editorial_qc"] = script_quality_report(
                        plan, topic, content_type, duration_sec, target_words)
                    return plan

                # If only approximate planning length remains, let measured
                # TTS duration be the source of truth. The factory now expands
                # as well as shortens narration after synthesis.
                non_length_flags = [f for f in flags if not _is_word_count_flag(f)]
                current_words = len(str(plan.get("narration", "")).split())
                if (flags and not non_length_flags and
                        current_words >= max(80, int(target_words * 0.65)) and
                        current_words <= int(target_words * 1.35)):
                    plan["editorial_qc"] = {
                        "passed": True,
                        "flags": [],
                        "warnings": [
                            f"Planning narration is {current_words} words vs target {target_words}; "
                            "final runtime will be corrected after measured TTS duration."
                        ],
                        "topic": topic,
                        "target_words": target_words,
                        "actual_words": current_words,
                        "source": str(plan.get("source") or f"{p}:{mdl}"),
                        "list_spec": detect_list_topic(topic),
                        "timing_retime_required": True,
                    }
                    return plan

                # Quality failure: use a compact narration-only repair rather
                # than asking the provider to echo the entire long JSON object.
                rejection_context = "; ".join(flags)
                errors.append(f"{p}:quality:{rejection_context[:220]}")
                try:
                    nsys, nuser = _narration_prompt(
                        plan, topic, content_type, duration_sec, tone, language,
                        target_words, problems=flags,
                    )
                    raw_fix = _call_provider(p, mdl, nsys, nuser)
                    fix_obj = _extract_json(raw_fix)
                    if isinstance(fix_obj, dict) and str(fix_obj.get("narration", "")).strip():
                        merged = dict(plan)
                        merged["narration"] = fix_obj.get("narration", "")
                        merged["cta"] = fix_obj.get("cta") or plan.get("cta", "")
                        improved = _normalize_plan(
                            merged, topic, content_type, target_words,
                            f"{p}:{mdl}+critic")
                        if improved:
                            fix_flags = _quality_flags(
                                improved, target_words, topic, content_type, duration_sec)
                            if not fix_flags:
                                improved["editorial_qc"] = script_quality_report(
                                    improved, topic, content_type, duration_sec, target_words)
                                return improved
                            rejection_context = "; ".join(fix_flags)
                except Exception as critic_error:
                    errors.append(f"{p}:critic:{type(critic_error).__name__}:{str(critic_error)[:140]}")
                continue

            except Exception as e:
                if isinstance(e, ScriptQualityError):
                    raise
                if isinstance(e, ScriptProviderError):
                    if requested == "auto":
                        errors.append(f"{p}:provider_error:{str(e)[:220]}")
                        break
                    raise
                if _is_rate_limited(e):
                    errors.append(f"{p}:rate_limited:HTTP429")
                    rejection_context = _rate_limit_message(p)
                    if requested != "auto":
                        raise ScriptProviderError(rejection_context) from e
                    print(f"[Script] {p} hit HTTP 429; skipping further retries on this provider and trying the next configured AI writer...")
                    break
                errors.append(f"{p}:{type(e).__name__}:{str(e)[:220]}")
                rejection_context = str(e)[:260]
                continue

        # Auto mode may try the next AI provider; explicit mode must fail now.
        if requested != "auto":
            detail = rejection_context or (errors[-1] if errors else "unknown quality failure")
            raise ScriptQualityError(
                f"{p} could not produce a publishable script after {attempts} attempts: {detail}"
            )

    if publish:
        raise ScriptProviderError("No AI script provider produced a publishable draft: " + " | ".join(errors[-8:]))
    if requested != "auto":
        raise ScriptProviderError("Requested script provider failed: " + " | ".join(errors[-6:]))
    if errors:
        print("Script AI providers unavailable/failed -> deterministic planner: " + " | ".join(errors))
    return None

def retime_script_plan(plan: dict, topic: str, content_type: str, duration_sec: int,
                       tone: str, language: str, target_words: int,
                       provider: str = "auto", model: str = "auto") -> dict | None:
    """Rewrite an already-good plan shorter/longer after actual TTS timing is known.

    v5.4.1 asks providers for narration-only JSON.  Older builds asked the LLM
    to echo the entire long plan (including all beat text) during retiming,
    which could reproduce the same truncation/incomplete-JSON failure that the
    initial long-form script path had just avoided.
    """
    requested = (provider or "auto").lower()
    providers = auto_provider_order() if requested == "auto" else [requested]
    if requested not in ("auto", "planner") and not _provider_available(requested):
        raise ScriptProviderError(f"Requested script provider '{requested}' is unavailable during retiming")
    last_error = None
    for p in providers:
        if p == "planner" or not _provider_available(p):
            continue
        mdl = _default_model(p) if not model or model == "auto" else model
        try:
            system, user = _narration_prompt(
                plan, topic, content_type, duration_sec, tone, language,
                target_words,
                problems=[
                    f"retime the narration to {max(40,target_words-4)}-{target_words+4} words",
                    "preserve every existing beat and list item",
                    "remove low-value filler before removing meaning",
                    "do not cut a sentence halfway",
                ],
            )
            raw = _call_provider(p, mdl, system, user)
            obj = _extract_json(raw)
            if not isinstance(obj, dict) or not str(obj.get("narration", "")).strip():
                raise RuntimeError("retime returned incomplete narration JSON (" +
                                   _incomplete_plan_diagnostic(obj, raw, target_words) + ")")
            merged = deepcopy(plan)
            merged["narration"] = obj.get("narration", "")
            merged["cta"] = obj.get("cta") or plan.get("cta", "")
            out = _normalize_plan(merged, topic, content_type, target_words,
                                  f"{p}:{mdl}+retime")
            if out:
                flags = _quality_flags(out, target_words, topic, content_type, duration_sec)
                if any(_is_word_count_flag(f) for f in flags):
                    out = _repair_length_same_provider(
                        out, p, mdl, topic, content_type, duration_sec,
                        tone, language, target_words, max_passes=2,
                    )
                    flags = _quality_flags(
                        out, target_words, topic, content_type, duration_sec)
                if not flags:
                    out["editorial_qc"] = script_quality_report(
                        out, topic, content_type, duration_sec, target_words)
                    return out
                non_length = [f for f in flags if not _is_word_count_flag(f)]
                if not non_length and len(str(out.get("narration", "")).split()) >= int(target_words * 0.80):
                    out["editorial_qc"] = {
                        "passed": True, "flags": [],
                        "warnings": ["Runtime retime remains approximate; validate measured TTS duration."],
                        "topic": topic, "target_words": target_words,
                        "actual_words": len(str(out.get("narration", "")).split()),
                        "source": str(out.get("source") or f"{p}:{mdl}"),
                        "list_spec": detect_list_topic(topic),
                        "timing_retime_required": True,
                    }
                    return out
                if requested != "auto":
                    raise ScriptQualityError(
                        "Retimed script failed editorial QC: " + "; ".join(flags)
                    )
        except Exception as e:
            last_error = e
            if _is_rate_limited(e):
                if requested != "auto":
                    raise ScriptProviderError(_rate_limit_message(p)) from e
                print(f"[Script] {p} hit HTTP 429 during retiming; trying the next configured AI writer...")
                continue
            if requested != "auto":
                if isinstance(e, ScriptQualityError):
                    raise
                raise ScriptProviderError(
                    f"Requested script provider '{p}' failed during retiming: {str(e)[:260]}"
                ) from e
            continue

    # No AI provider available: sentence-safe deterministic retime. This is only
    # a runtime safety net after actual TTS proved the script too long; unlike v4,
    # it never truncates the spoken audio in the middle of a sentence.
    narration = str(plan.get("narration", "") or "").strip()
    sents = [x.strip() for x in re.split(r"(?<=[.!?])\s+", narration) if x.strip()]
    chosen, count = [], 0
    for sent in sents:
        n = len(sent.split())
        if chosen and count + n > target_words + 3:
            break
        chosen.append(sent)
        count += n
        if count >= target_words - 4:
            break
    if not chosen:
        return None
    text = " ".join(chosen)
    if len(text.split()) < target_words - 12 and len(chosen) < len(sents):
        cand = text + " " + sents[len(chosen)]
        if len(cand.split()) <= target_words + 12:
            text = cand
    out = deepcopy(plan)
    out["narration"] = text
    out["words"] = len(text.split())
    out["source"] = str(plan.get("source", "planner")) + "+sentence-retime"
    out["beats"] = deepcopy(plan.get("beats") or [])
    return out
