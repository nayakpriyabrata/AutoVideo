"""Conservative local editorial text fallback; never invent a new claim."""
import re

FILLER = {"yeah", "yes", "okay", "ok", "right", "well", "another day", "you know"}
TRAILING = {"and", "or", "but", "with", "for", "of", "to", "our", "your", "the", "a", "an", "its", "is"}
STOP = TRAILING | {"this", "that", "these", "those", "have", "has", "was", "were", "will", "would", "could", "should", "just", "very", "from", "when", "then", "they", "them", "you", "their", "about", "into", "what", "which", "there", "here", "been", "some"}


def clean_text(text):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", text, flags=re.I)


def usable_headline(text):
    words = re.findall(r"[\w']+", clean_text(text).lower())
    return (3 <= len(words) <= 16 and " ".join(words) not in FILLER
            and words[-1] not in TRAILING)


def callout(text, max_words=12):
    """Return a complete short clause, or no card instead of a chopped thought."""
    candidates = []
    if re.search(r"\b(\w+)\s+\1\b", str(text or ""), re.I):
        return ""  # damaged/duplicated narration is not an editorial callout
    for clause in re.split(r"[.!?;:\n]+", clean_text(text)):
        clause = clause.strip(" ,-–—")
        words = clause.split()
        if not (4 <= len(words) <= max_words) or not usable_headline(clause):
            continue
        score = sum(w.lower().strip(",") in {
            "use", "avoid", "choose", "focus", "remember", "build", "create", "start", "stop"
        } for w in words)
        candidates.append((score, clause))
    return max(candidates, key=lambda x: x[0])[1] if candidates else ""


def headline(text):
    title = callout(text)
    if title:
        return title
    # Label this as a topic summary, not an invented quotation or claim.
    content = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", clean_text(text))
               if w.lower() not in STOP | FILLER]
    counts = {w.lower(): sum(x.lower() == w.lower() for x in content) for w in content}
    salient = sorted(dict.fromkeys(w.lower() for w in content), key=lambda w: -counts[w])[:4]
    return "Exploring " + ", ".join(salient) if salient else "Untitled moment — review required"
