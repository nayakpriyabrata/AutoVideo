"""
Script Generator - 100% FREE
Priority:
1. Ollama local (free, offline) if running
2. Gemini free tier (if GEMINI_API_KEY set)
3. Groq free tier (if GROQ_API_KEY set)
4. Built-in smart templates (always works, zero key) <- default
"""
import os
import re
import random
import requests


def _try_ollama(prompt: str, model: str = "llama3.2") -> str | None:
    """Try local Ollama. Returns None if not available."""
    try:
        r = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=60,
        )
        if r.status_code == 200:
            return r.json().get("response", "").strip() or None
    except Exception:
        pass
    return None


def _try_gemini(prompt: str) -> str | None:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"
        r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
        if r.status_code == 200:
            cands = r.json().get("candidates", [])
            if cands:
                parts = cands[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip() or None
    except Exception:
        pass
    return None


def _try_groq(prompt: str) -> str | None:
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        return None
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "llama-3.1-8b-instant",
                  "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": 2000},
            timeout=30,
        )
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip() or None
    except Exception:
        pass
    return None


# ---------- Built-in template engine (always works, no internet needed) ----------

HOOKS = [
    "Stop scrolling. This will change how you think about {topic}.",
    "Nobody tells you this about {topic} — but I will.",
    "In the next {dur}, you'll learn what took me years about {topic}.",
    "If you care about {topic}, watch till the end.",
    "This one idea about {topic} can save you months of mistakes.",
]

CTAS = [
    "Follow for more videos like this, and share this with one friend who needs it.",
    "Subscribe for daily videos, and comment your biggest takeaway below.",
    "Save this video and follow — part 2 is coming tomorrow.",
    "Like this if it helped you, and follow for more.",
]

def _clean_topic(topic: str) -> str:
    return re.sub(r"\s+", " ", topic.strip()).strip(" .")


def _words_for_duration(duration_sec: int) -> int:
    # English speech ~ 150 wpm = 2.5 words/sec
    return max(60, int(duration_sec * 2.4))


def _template_shorts(topic: str, duration_sec: int, tone: str) -> dict:
    topic = _clean_topic(topic)
    target_words = _words_for_duration(duration_sec)
    hook = random.choice(HOOKS).format(topic=topic.lower(), dur=f"{duration_sec} seconds")
    # Split target into 3 beats
    body = (
        f"Here's the truth. Most people get {topic} completely wrong. "
        f"They focus on complicated tricks, but the real secret is simple. "
        f"First, understand the basics of {topic} — what it is, and why it matters right now. "
        f"Second, take one small action today. Don't wait for the perfect moment. "
        f"Small steps, done daily, beat big plans done never. "
        f"Third, stay consistent for thirty days. Track your progress, learn from mistakes, and keep going. "
        f"Remember, success with {topic} is not about luck. It's about clarity, action, and patience. "
        f"Start today, and your future self will thank you."
    )
    cta = random.choice(CTAS)
    full = f"{hook} {body} {cta}"
    # Trim / pad to target words approx
    words = full.split()
    if len(words) > target_words + 10:
        words = words[:target_words + 10]
        full = " ".join(words) + "."
    title = f"{topic} in {duration_sec} seconds! 🔥"  # emoji kept for YouTube; auto-stripped on video render
    scenes = _split_scenes(full, n=max(4, duration_sec // 8))
    return {"title": title, "script": full, "scenes": scenes, "hook": hook, "cta": cta, "source": "template"}


def _template_faceless(topic: str, duration_sec: int, tone: str) -> dict:
    topic = _clean_topic(topic)
    hook = random.choice(HOOKS).format(topic=topic.lower(), dur=f"{duration_sec//60} minutes")
    chapters = [
        f"Chapter one. Why {topic} matters more than ever. The world is changing fast, and understanding {topic} gives you a real advantage.",
        f"Chapter two. The three biggest mistakes people make with {topic}. Mistake one is starting without a plan. Mistake two is quitting too early. Mistake three is copying others instead of finding your own way.",
        f"Chapter three. A simple step-by-step system for {topic}. Step one, learn the fundamentals for one week. Step two, take daily action for thirty days. Step three, review, improve, and scale what works.",
        f"Chapter four. Real examples and inspiration. Ordinary people with no special advantage succeeded with {topic} by staying consistent. You can do the same.",
        f"Final chapter. Your action plan for the next seven days. Day one, define your goal clearly. Day two to six, execute one task daily. Day seven, review and plan the next week.",
    ]
    body = " ".join(chapters)
    cta = "If this video helped you, subscribe and turn on the bell, because next week I'll share the advanced guide. " + random.choice(CTAS)
    full = f"{hook} {body} {cta}"
    target_words = _words_for_duration(duration_sec)
    words = full.split()
    if len(words) > target_words + 40:
        words = words[:target_words + 40]
        full = " ".join(words) + "."
    title = f"{topic} — Complete Guide ({duration_sec//60} min)"
    scenes = _split_scenes(full, n=max(6, duration_sec // 45))
    return {"title": title, "script": full, "scenes": scenes, "hook": hook, "cta": cta, "source": "template"}


def _template_explainer(topic: str, duration_sec: int, tone: str) -> dict:
    topic = _clean_topic(topic)
    hook = f"Confused about {topic}? In this video, I'll explain it so simply that anyone can understand."
    body = (
        f"Let's start with the basics. {topic} sounds complicated, but it's actually simple. "
        f"Think of it like this. Imagine you're learning to ride a bicycle. At first it feels hard, then it becomes natural. {topic} works the same way. "
        f"Here's how it works, step by step. First, you understand the core idea. Second, you see a real example. Third, you try it yourself. "
        f"Let's look at an example. Suppose you apply {topic} in your daily life. Within a few weeks, you start seeing small results. Within a few months, those results compound. "
        f"Now, the common questions. Is it risky? Only if you rush without learning. How much time does it need? Just twenty minutes a day. When will you see results? Faster than you think, if you stay consistent. "
        f"So here's the summary. {topic} is simple, practical, and powerful — if you start small and stay consistent."
    )
    cta = random.choice(CTAS)
    full = f"{hook} {body} {cta}"
    target_words = _words_for_duration(duration_sec)
    words = full.split()
    if len(words) > target_words + 20:
        words = words[:target_words + 20]
        full = " ".join(words) + "."
    title = f"{topic} Explained Simply"
    scenes = _split_scenes(full, n=max(5, duration_sec // 40))
    return {"title": title, "script": full, "scenes": scenes, "hook": hook, "cta": cta, "source": "template"}


def _template_marketing(topic: str, duration_sec: int, tone: str) -> dict:
    topic = _clean_topic(topic)
    hook = f"Attention! If you want {topic}, this is for you."
    body = (
        f"Introducing something special. {topic}. Made with care, designed for people like you. "
        f"Why is it different? First, premium quality you can feel. Second, honest pricing with no hidden costs. Third, loved and trusted by happy customers. "
        f"Here's what you get. Great quality, fast delivery, and full support. And for a limited time, there's a special offer just for viewers of this video. "
        f"Don't wait. Stock is limited, and this offer ends soon."
    )
    cta = "Order now, or message us today. Your satisfaction is guaranteed."
    full = f"{hook} {body} {cta}"
    title = f"{topic} — Special Offer 🎁"
    scenes = _split_scenes(full, n=4)
    return {"title": title, "script": full, "scenes": scenes, "hook": hook, "cta": cta, "source": "template"}


def _split_scenes(script: str, n: int) -> list:
    """Split script into n visual scenes (sentence-grouped)."""
    sentences = re.split(r"(?<=[.!?])\s+", script.strip())
    sentences = [s for s in sentences if s]
    if not sentences:
        return [script]
    n = max(1, min(n, len(sentences)))
    chunk = max(1, len(sentences) // n)
    scenes, cur = [], []
    for s in sentences:
        cur.append(s)
        if len(cur) >= chunk and len(scenes) < n - 1:
            scenes.append(" ".join(cur))
            cur = []
    if cur:
        scenes.append(" ".join(cur))
    return scenes


def _ai_prompt(topic: str, video_type: str, duration_sec: int, tone: str) -> str:
    words = _words_for_duration(duration_sec)
    return (
        f"Write a {tone} voiceover script for a {video_type} video about: {topic}.\n"
        f"Duration: {duration_sec} seconds (~{words} words). Spoken English, simple words.\n"
        f"Structure: strong hook in first 3 seconds, 3-5 clear points, motivational close + call to subscribe/follow.\n"
        f"Output ONLY the script text, no titles or brackets."
    )


def generate_script(topic: str, video_type: str = "shorts",
                    duration_sec: int = 45, tone: str = "exciting") -> dict:
    """
    Returns {"title", "script", "scenes", "hook", "cta", "source"}
    source = ollama | gemini | groq | template
    """
    topic = _clean_topic(topic)
    prompt = _ai_prompt(topic, video_type, duration_sec, tone)

    for name, fn in (("ollama", lambda: _try_ollama(prompt)),
                     ("gemini", lambda: _try_gemini(prompt)),
                     ("groq", lambda: _try_groq(prompt))):
        try:
            text = fn()
        except Exception:
            text = None
        if text and len(text.split()) > 30:
            n = max(4, duration_sec // 10) if video_type in ("shorts", "marketing") else max(6, duration_sec // 45)
            return {"title": topic[:60], "script": text,
                    "scenes": _split_scenes(text, n),
                    "hook": text[:150], "cta": text[-150:], "source": name}

    # Fallback: built-in templates (always works)
    if video_type == "faceless_youtube":
        return _template_faceless(topic, duration_sec, tone)
    if video_type == "explainer":
        return _template_explainer(topic, duration_sec, tone)
    if video_type == "marketing":
        return _template_marketing(topic, duration_sec, tone)
    return _template_shorts(topic, duration_sec, tone)
