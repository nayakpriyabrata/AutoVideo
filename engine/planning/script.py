"""
Content planner (v3) - topic -> angle -> hooks -> beats -> narration.
Topic-specific scaffolds per content_type. No generic "stay consistent" filler.
Optional LLM refinement via Ollama/Gemini/Groq when available (never required).
"""
from __future__ import annotations
import re
import random

WORDS_PER_SEC = 2.45

HOOK_PATTERNS = {
    "education": [
        "You've been lied to about {short}. Here's what's actually true.",
        "Nobody explains {short} correctly. In {dur}, I will.",
        "Stop believing this myth about {short}.",
    ],
    "storytelling": [
        "This is the story of {short} — and it doesn't end how you'd expect.",
        "Nobody saw this coming: {short}.",
    ],
    "cinematic_story": [
        "{short}. A story in {dur} seconds.",
        "Some stories change you. This is one of them: {short}.",
    ],
    "documentary": [
        "The hidden truth behind {short}.",
        "What really happened with {short}? Let's look at the evidence.",
    ],
    "motivation": [
        "If {short} scares you, this is for you.",
        "{short_cap} — and why most people quit right before it works.",
    ],
    "technology": [
        "{short_cap} just changed everything. Here's what matters.",
        "Nobody is talking about this side of {short}.",
    ],
    "history": [
        "In {year}, {short} shocked the world. Here's why it still matters.",
        "The forgotten story of {short}.",
    ],
    "finance": [
        "{short_cap} — the rich do this differently. Here's how.",
        "Stop losing money on {short}. Do this instead.",
    ],
    "kids_story": [
        "Once upon a time, {short} went on a big adventure!",
        "Gather round! The magical tale of {short} begins now.",
    ],
    "advertisement": [
        "Attention: {short} — this changes everything.",
        "What if {short} took 10 seconds? Watch this.",
    ],
    "product_demo": [
        "Watch {short} do in seconds what used to take hours.",
        "Here's {short} — and exactly how it works.",
    ],
    "news_explainer": [
        "Breaking down {short}: what happened, and what it means for you.",
        "{short_cap} — explained in {dur} seconds, no jargon.",
    ],
}

# Beat scaffolds: (beat_name, sentence_templates). {t}=topic {s}=short form.
BEATS = {
    "education": [
        ("myth", ["Most people think {s} works like this — but that's wrong.", "The common advice about {s} misses the real mechanism."]),
        ("mechanism", ["Here is what actually happens with {s}, step by step.", "The key idea behind {s} is simple once you see it."]),
        ("proof", ["Take a concrete example of {s} in real life.", "Researchers and practitioners of {s} noticed the same pattern."]),
        ("mistake", ["The biggest mistake with {s} is rushing the fundamentals.", "Avoid this trap that ruins most {s} attempts."]),
        ("method", ["Do this instead: a small, correct {s} routine done daily.", "The method is boring but effective — which is why it works."]),
        ("payoff", ["Within weeks of applying this to {s}, results compound.", "That is the whole game of {s}: clarity, then repetition."]),
    ],
    "storytelling": [
        ("setup", ["It started with {s} on an ordinary day.", "Nobody paid attention to {s} at first."]),
        ("inciting", ["Then everything about {s} changed in a single moment.", "One decision turned {s} upside down."]),
        ("rise", ["What followed tested everyone involved with {s}.", "Each step with {s} raised the stakes higher."]),
        ("climax", ["At the breaking point, {s} revealed its true face.", "This was the moment {s} would be remembered for."]),
        ("resolve", ["And that is how {s} finally settled.", "The dust settled — but {s} was never the same again."]),
    ],
    "motivation": [
        ("pain", ["You know the feeling: {s} slipping away while you hesitate.", "{short_cap} demands something most people won't give."]),
        ("truth", ["Here is the uncomfortable truth about {s}.", "Nobody is coming to fix {s} for you."]),
        ("turn", ["But the moment you commit to {s}, the fog lifts.", "One disciplined week with {s} rewires your belief."]),
        ("charge", ["So start {s} today — imperfect, small, now.", "Your future is built by what you do about {s} this week."]),
    ],
    "finance": [
        ("problem", ["Most people handle {s} emotionally — and pay for it.", "The hidden cost of ignoring {s} grows every year."]),
        ("principle", ["The principle is simple: understand {s} before you touch it.", "Wealth with {s} comes from rules, not predictions."]),
        ("system", ["Here is a simple {s} system anyone can follow.", "Automate the boring parts of {s}; review monthly."]),
        ("warning", ["Never risk on {s} what you can't afford to lose.", "If {s} sounds too good to be true, walk away."]),
    ],
    "technology": [
        ("shift", ["Something just shifted in {s} — and it's big.", "{short_cap} is moving faster than anyone predicted."]),
        ("how", ["Here's how the new {s} actually works.", "Under the hood, {s} does three clever things."]),
        ("impact", ["For you, {s} means this: adapt early or catch up later.", "The winners in {s} will be the ones who start now."]),
    ],
    "news_explainer": [
        ("what", ["Here's what happened with {s}.", "The facts of {s}, in order."]),
        ("why", ["Why does {s} matter? Two reasons.", "This affects you because {s} touches everyday life."]),
        ("next", ["What happens next with {s}? Watch these two signals.", "The story of {s} is still unfolding — stay tuned."]),
    ],
    "product_demo": [
        ("problem", ["Old way of handling {s}: slow, painful, expensive.", "Everyone hated dealing with {s} — until now."]),
        ("reveal", ["Meet the new {s}. Watch closely.", "This is {s}, redesigned from zero."]),
        ("proof", ["See {s} handle the hard part in seconds.", "Real test, no edits: {s} just works."]),
    ],
    "advertisement": [
        ("hook2", ["Imagine {s} without the hassle.", "Picture your life with {s} solved."]),
        ("offer", ["For a limited time, {s} comes with a special launch offer.", "Early buyers of {s} get the best deal we'll ever run."]),
    ],
}
BEATS["cinematic_story"] = BEATS["storytelling"]
BEATS["documentary"] = BEATS["education"]
BEATS["history"] = BEATS["storytelling"]
BEATS["kids_story"] = BEATS["storytelling"]

CTA_RULES = {
    "education": "soft", "storytelling": "none", "cinematic_story": "none",
    "documentary": "soft", "motivation": "follow", "technology": "follow",
    "history": "none", "finance": "soft", "kids_story": "none",
    "advertisement": "buy", "product_demo": "try", "news_explainer": "follow",
}


LONGFORM_EXPANSION_PATTERNS = [
    "Make the idea practical: choose one small action that can be repeated without relying on motivation. The point is to make progress easy to start and easy to measure.",
    "A simple example helps. Picture an ordinary day, one clear decision, and one behavior you can actually repeat. That is more useful than a vague promise to do better.",
    "The common failure mode is trying to change everything at once. A smaller action gives you feedback sooner, so you can adjust without abandoning the whole plan.",
    "Notice the difference between intention and evidence. Intention is what you hope to do; evidence is the action you can point to at the end of the day.",
    "Consistency becomes easier when the environment supports the behavior. Prepare the next step in advance, remove one obvious distraction, and make the desired action the easiest option.",
    "Progress also needs reflection. A short weekly review can reveal what worked, what created friction, and what should change before the next week begins.",
    "Keep the standard realistic. Missing once is information, not failure. The useful response is to restart quickly and make the next repetition easier.",
    "The goal is not perfection. The goal is a pattern strong enough to survive busy days, low motivation, and the occasional mistake.",
    "Use a concrete checkpoint. Decide what success looks like for the next seven days, then judge the habit by completed actions rather than by how motivated you felt.",
    "Over time, small choices compound into identity. You begin to trust yourself because your calendar and your actions support the person you say you want to become.",
]

def _expand_to_target(parts: list[str], beats: list[dict], topic: str, target_words: int) -> list[str]:
    """Deterministically extend a no-API script to near the requested duration.

    The previous planner stopped after six filler sentences, so a requested five-minute
    video often produced only ~170 words.  This fallback deliberately stays
    explanatory rather than inventing topic-specific facts.
    """
    s = _short(topic).lower()
    floor = max(50, int(target_words * 0.96))
    if sum(len(x.split()) for x in parts) >= floor:
        return parts
    i = 0
    # Add beat-specific transitions and varied explanatory modules until we are
    # close to the requested word count.  The hard ceiling prevents runaway text.
    while sum(len(x.split()) for x in parts) < floor and i < 80:
        b = beats[i % len(beats)] if beats else {"name": "story", "text": ""}
        label = b.get("name", "story").replace("_", " ")
        if i % 3 == 0:
            parts.append(
                f"Now connect that to the {label} part of the idea. "
                "Turn the principle into one observable action, one realistic example, and one checkpoint you can review later."
            )
        parts.append(LONGFORM_EXPANSION_PATTERNS[i % len(LONGFORM_EXPANSION_PATTERNS)].format(s=s))
        i += 1
    return parts

CTA_TEXT = {
    "soft": "If this helped, share it with one person who needs it.",
    "follow": "Follow for part two — it gets even better.",
    "buy": "Tap the link and get yours before the offer ends.",
    "try": "Try it free — link below.",
}


def _short(topic: str) -> str:
    t = re.sub(r"^(why|what|how|the)\s+", "", topic.strip(), flags=re.I)
    return t[:60]


def plan_content(topic: str, content_type: str = "education", duration_sec: int = 45,
                 tone: str = "cinematic", language: str = "en",
                 use_llm: bool = True, script_provider: str = "auto",
                 script_model: str = "auto", script_quality: str = "high") -> dict:
    """Return a complete spoken narration plan.

    v5 uses a free-first full-script director (Gemini/Groq/Ollama) when available,
    with OpenAI/xAI as optional keyed providers.  The deterministic planner below
    remains the no-network/no-key fallback.
    """
    topic = re.sub(r"\s+", " ", topic.strip())
    requested_provider = str(script_provider or "auto").lower()
    quality_mode = str(script_quality or "high").lower()
    if use_llm and requested_provider != "planner":
        try:
            from .script_engine import generate_script_plan
            ai = generate_script_plan(topic, content_type, duration_sec, tone, language,
                                      provider=script_provider, model=script_model,
                                      quality=script_quality)
            if ai:
                return ai
        except Exception as e:
            # An explicitly requested writer is a contract. Silently replacing
            # Groq/Gemini/GPT/Grok with a generic planner previously produced
            # hours of expensive media for an unusable script. Publish mode is
            # strict even when provider=auto.
            if requested_provider != "auto" or quality_mode == "publish":
                raise
            print(f"AI script director failed ({str(e)[:140]}) -> deterministic planner")
    if quality_mode == "publish":
        raise RuntimeError("Publish-quality script generation requires a working AI script provider; planner fallback is disabled.")
    s, cap = _short(topic).lower(), _short(topic).capitalize()
    dur_label = f"{duration_sec} seconds" if duration_sec < 90 else f"{duration_sec//60} minutes"
    target_words = max(50, int(duration_sec * WORDS_PER_SEC))

    pats = HOOK_PATTERNS.get(content_type, HOOK_PATTERNS["education"])
    hooks = [p.format(short=s, short_cap=cap, dur=dur_label,
                      year=random.choice(["1969", "1989", "2008", "2019"])) for p in pats]
    # add 2 generated variants for selection depth
    hooks += [f"{cap}: the truth in {dur_label}.", f"What if everything you knew about {s} was backwards?"]
    hook = max(hooks, key=lambda h: (len(h.split()) >= 6, -abs(len(h.split()) - 12)))

    scaff = BEATS.get(content_type, BEATS["education"])
    beats, picked = [], set()
    for name, templates in scaff:
        t = random.choice([x for x in templates if x not in picked] or templates)
        picked.add(t)
        beats.append({"name": name, "text": t.format(t=topic, s=s, short=cap)})

    # Deterministic fallback is intentionally self-contained. The v5 full-script
    # provider router runs before this path, so a failed cloud/local LLM does not
    # trigger a second, beat-only API pass that can make narration inconsistent.
    source = "planner"

    cta_kind = CTA_RULES.get(content_type, "soft")
    cta = CTA_TEXT.get(cta_kind, "")
    parts = [hook] + [b["text"] for b in beats]
    # Expand short scripts first, then guarantee long-form coverage.
    i = 0
    while sum(len(p.split()) for p in parts) < min(target_words, 220) and i < 12:
        b = beats[i % len(beats)]
        parts.insert(1 + (i % len(beats)), _expand(b["name"], s, cap))
        i += 1
    parts = _expand_to_target(parts, beats, topic, target_words)
    if cta and cta_kind in ("soft", "follow"):
        parts.append(cta)
    if cta_kind in ("buy", "try") and cta:
        parts.append(cta)
    narration = " ".join(parts)
    words = narration.split()
    if len(words) > target_words + 15:
        narration = " ".join(words[:target_words + 15]) + "."
    return {
        "angle": f"{content_type}: {cap}",
        "audience": {"kids_story": "children 5-10 + parents"}.get(content_type, "general 18-44"),
        "hooks": hooks, "hook": hook, "beats": beats,
        "narration": narration, "words": len(narration.split()),
        "cta": cta, "cta_kind": cta_kind, "source": source,
    }


def _expand(beat: str, s: str, cap: str) -> str:
    bank = {
        "myth": f"Look closer at {s} and the old story falls apart.",
        "mechanism": f"Once you grasp this, {s} becomes predictable.",
        "proof": f"The pattern repeats everywhere in {s}.",
        "mistake": f"Fix this one thing and {s} gets dramatically easier.",
        "method": f"Small steps with {s}, done daily, beat intensity.",
        "payoff": f"Patience with {s} pays more than talent.",
        "setup": f"The world of {s} felt normal — for now.",
        "inciting": f"Nothing about {s} would stay the same.",
        "rise": f"Pressure around {s} kept building.",
        "climax": f"Everything hinged on this instant of {s}.",
        "resolve": f"{cap} found its ending — mostly.",
    }
    return bank.get(beat, f"And {s} kept moving forward.")


def _try_llm_deepen(topic, content_type, beats):
    """Optional: rewrite beat texts with local/free LLM. Returns beats or None."""
    try:
        import os, requests
        prompt = (f"Rewrite these {content_type} narration beats about '{topic}' to be specific, "
                  f"vivid, non-generic. Keep {len(beats)} lines, one per beat, same order, no numbering:\n" +
                  "\n".join(b["text"] for b in beats))
        text = None
        try:  # Ollama first (free, local)
            r = requests.post("http://localhost:11434/api/generate",
                              json={"model": "llama3.2", "prompt": prompt, "stream": False}, timeout=90)
            if r.status_code == 200:
                text = r.json().get("response", "")
        except Exception:
            pass
        if not text:
            key = os.getenv("GEMINI_API_KEY", "")
            if key:
                try:
                    r = requests.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}",
                        json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60)
                    c = r.json().get("candidates", [])
                    if c:
                        text = c[0]["content"]["parts"][0].get("text", "")
                except Exception:
                    pass
        if not text:
            return None
        lines = [l.strip("- 0123456789.)") for l in text.strip().split("\n") if l.strip()]
        if len(lines) >= len(beats) - 1:
            for b, l in zip(beats, lines):
                if len(l.split()) > 3:
                    b["text"] = l.strip()
            return beats
    except Exception:
        pass
    return None
