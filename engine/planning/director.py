"""
Director Engine - idea -> structured production plan with voice-timed shots.
Narration timing drives shot boundaries (NOT equal splits, NOT 1 para = 1 shot).
"""
from __future__ import annotations
import re
import math
from ..project.manifest import ProductionManifest, Shot

COVERAGE_CYCLE = ["primary", "closeup", "insert", "primary", "broll", "closeup"]
FRAMING = {"hook": "extreme close-up", "primary": "medium shot", "closeup": "close-up",
           "insert": "macro insert", "broll": "wide establishing", "hero_outro": "slow wide reveal"}
MOVES = {"hook": "fast push-in", "primary": "very slow dolly-in", "closeup": "subtle lateral drift",
         "insert": "locked-off with rack focus feel", "broll": "smooth aerial-style drift",
         "hero_outro": "slow crane-up reveal"}


def _scene_from_visual_intent(visual_intent: str, narration: str, base_location: str, coverage: str) -> tuple[str, str, str]:
    """Turn an LLM visual beat into concrete subject/action/environment fields.

    v5.0 kept every shot in one canonical apartment/office, which made listicle
    videos look repetitive even when the script engine returned diverse
    ``visual_intent`` values.  v5.1 keeps a common visual language but lets each
    beat choose a distinct illustrative environment.
    """
    vi = re.sub(r"\s+", " ", str(visual_intent or "")).strip()
    text = (vi + " " + str(narration or "")).lower()
    env = base_location
    subject = "cinematic human-scale detail"
    action = vi or "a concrete visual metaphor for the narration beat"

    rules = [
        (("exercise", "workout", "walk", "run", "health"), "sunlit park path or clean fitness space", "person in motion"),
        (("read", "learn", "book", "study"), "quiet reading corner or library table", "hands reading and taking notes"),
        (("plan", "goal", "priority", "schedule", "journal"), "tidy desk with planner and pen", "hands planning the next concrete step"),
        (("focus", "work", "deep work", "phone", "screen"), "minimal distraction-free work desk", "person placing distractions aside and focusing"),
        (("sleep", "rest", "night", "recovery"), "calm bedroom at dusk with soft practical light", "person winding down deliberately"),
        (("money", "save", "budget", "finance"), "simple desk with notebook, calculator and receipts", "hands reviewing a simple budget"),
        (("family", "friend", "relationship", "people"), "warm cafe or living-room conversation setting", "two people having a natural supportive conversation"),
        (("gratitude", "mindset", "reflect", "thought"), "quiet window seat in soft morning light", "person journaling and reflecting"),
        (("failure", "mistake", "lesson", "reset"), "worktable with crossed-out draft and fresh page", "hands reset the plan and begin again"),
        (("success", "progress", "momentum", "growth"), "sunrise city overlook or staircase with forward depth", "person moving forward with calm purpose"),
        (("morning", "wake", "routine"), "bright morning kitchen or bedside routine", "person starting a simple morning routine"),
    ]
    for keys, e, a in rules:
        if any(k in text for k in keys):
            env, action = e, a
            break
    if coverage == "insert":
        subject = "close-up object detail"
    elif coverage == "broll":
        subject = "environmental b-roll"
    elif coverage in ("hook", "closeup"):
        subject = "expressive hands and face-free human detail"
    return subject, action, env


def _sentences_with_time(words: list[dict]) -> list[dict]:
    """Group word timings into sentences."""
    sents, cur = [], []
    for w in words:
        cur.append(w)
        if re.search(r"[.!?…:;]$", w["word"]) or w is words[-1]:
            text = " ".join(x["word"] for x in cur)
            sents.append({"text": text, "start": cur[0]["start"], "end": cur[-1]["end"]})
            cur = []
    if cur:
        sents.append({"text": " ".join(x["word"] for x in cur),
                      "start": cur[0]["start"], "end": cur[-1]["end"]})
    return sents


def _split_long_sentences(words: list[dict], sents: list[dict], max_len: float) -> list[dict]:
    """Split overlong timed sentences without recursion.

    Older builds recursively re-ran the splitter whenever *any* segment was
    still longer than ``max_len``.  If a segment could not be split (for
    example because it contained too few timed words), that exact segment was
    returned unchanged and recursion never made progress, eventually raising
    ``RecursionError``.

    v5.0.2 uses a bounded work queue.  A segment is split only when doing so
    actually creates two shorter non-empty segments; otherwise it is accepted
    as-is.  This guarantees termination even with unusual Whisper timings.
    """
    if not sents:
        return []
    try:
        limit = max(0.5, float(max_len))
    except Exception:
        limit = 8.0

    # Keep a hard safety bound. A 60-minute narration at 0.5 s per segment
    # would still fit comfortably below this number, while malformed timings
    # cannot explode the planner indefinitely.
    max_segments = 1000
    queue = [dict(s) for s in sents]
    out: list[dict] = []

    while queue and len(out) + len(queue) <= max_segments:
        s = queue.pop(0)
        try:
            start = float(s.get("start", 0.0))
            end = float(s.get("end", start))
        except Exception:
            out.append(s)
            continue
        span = max(0.0, end - start)
        if span <= limit + 1e-6:
            out.append(s)
            continue

        # Timed words belonging to this segment, sorted by actual start time.
        idx = [i for i, w in enumerate(words)
               if start - 0.01 <= float(w.get("start", -1e9)) <= end + 0.01]
        idx.sort(key=lambda i: float(words[i].get("start", 0.0)))

        # Need at least two words to make a meaningful split.  The previous
        # implementation required six and then recursed forever for shorter
        # long-duration segments.
        if len(idx) < 2:
            out.append(s)
            continue

        gaps = []
        for k in range(len(idx) - 1):
            left_i, right_i = idx[k], idx[k + 1]
            try:
                gap = float(words[right_i].get("start", 0.0)) - float(words[left_i].get("end", 0.0))
                left_span = float(words[left_i].get("end", start)) - start
            except Exception:
                continue
            balance_penalty = abs((left_span / span if span else 0.5) - 0.5)
            # Prefer natural pauses, then balanced halves.
            gaps.append((gap, -balance_penalty, k))

        cut = None
        for _, __, k in sorted(gaps, reverse=True):
            try:
                left_end = float(words[idx[k]].get("end", start))
                right_start = float(words[idx[k + 1]].get("start", end))
            except Exception:
                continue
            # Avoid zero-length/no-progress pieces.
            if left_end > start + 0.05 and right_start < end - 0.05:
                cut = k
                # Prefer cuts that keep both halves away from extreme imbalance.
                left_len = left_end - start
                right_len = end - right_start
                if left_len >= span * 0.25 and right_len >= span * 0.25:
                    break

        if cut is None:
            cut = max(0, min(len(idx) - 2, (len(idx) // 2) - 1))

        a, b = idx[:cut + 1], idx[cut + 1:]
        if not a or not b:
            out.append(s)
            continue

        try:
            left_end = float(words[a[-1]].get("end", start))
            right_start = float(words[b[0]].get("start", end))
        except Exception:
            out.append(s)
            continue

        # Most important guard: only enqueue a split if it makes real progress.
        left_span = left_end - start
        right_span = end - right_start
        if (left_span <= 0.05 or right_span <= 0.05 or
                left_span >= span - 0.01 or right_span >= span - 0.01):
            out.append(s)
            continue

        left = {"text": " ".join(str(words[i].get("word", "")).strip() for i in a).strip(),
                "start": start, "end": left_end}
        right = {"text": " ".join(str(words[i].get("word", "")).strip() for i in b).strip(),
                 "start": right_start, "end": end}

        # Process the two new segments again if either is still too long.
        queue.insert(0, right)
        queue.insert(0, left)

    # If the safety bound is ever hit, preserve the remaining material instead
    # of crashing or dropping narration.
    if queue:
        out.extend(queue)
    return out


def _visual_sentences(beats, story, total, max_length):
    """Gapless action windows driven by scene intent, never synthetic ASR words."""
    if not math.isfinite(float(total)) or not .1 <= total <= 6*3600:
        raise ValueError("Invalid visual story duration")
    source = list(beats or []) or [{'text': story, 'visual_intent': story, 'name': 'story'}]
    weights = [max(1, len(str(b.get('text') or b.get('visual_intent') or b.get('name') or '').split())) for b in source]
    windows, cursor = [], 0.0
    for index, (beat, weight) in enumerate(zip(source, weights)):
        end = total if index == len(source)-1 else cursor+total*weight/sum(weights)
        pieces = max(1, math.ceil((end-cursor)/max(1, float(max_length))))
        step = (end-cursor)/pieces
        for piece in range(pieces):
            windows.append({'text': str(beat.get('text') or beat.get('visual_intent') or story),
                            'start': cursor+piece*step, 'end': cursor+(piece+1)*step,
                            'beat_index': index})
        cursor = end
    if len(windows) > 1000:
        raise ValueError("Visual story needs too many scenes; increase shot length")
    return windows


def create_production_plan(manifest: ProductionManifest, narration: str, words: list[dict],
                           beats: list[dict], bible: dict, preset: dict,
                           router, total_duration: float, timing_source: str = "narration") -> ProductionManifest:
    """Fill manifest with voice-timed shots + routing + continuity rules."""
    manifest.visual_style = bible["visual_style"]
    manifest.color_palette = preset.get("color_treatment", "")
    manifest.lighting_language = bible["lighting"]
    manifest.camera_language = preset.get("camera_behavior", "")
    manifest.pace = preset.get("editing_pace", "")
    manifest.audio_mood = preset.get("music_style", "")
    manifest.continuity_rules = bible["continuity_rules"]
    manifest.negative_constraints = preset.get("negative", [])

    sents = _sentences_with_time(words) if words else [{"text": narration, "start": 0.0, "end": total_duration}]
    min_len, max_len = preset.get("shot_length", [4, 8])
    if timing_source == "visual_storyboard":
        sents = _visual_sentences(beats, narration, total_duration, max_len)
    elif timing_source != "narration":
        raise ValueError("Unknown story timing source")
    manifest.timing_source = timing_source
    # Never submit generations against a collapsed timing plan. This guard runs
    # before stock/Flow requests, including after estimated-timing recovery.
    if words and total_duration >= 30:
        gaps = [float(words[i]["start"]) - float(words[i-1]["end"])
                for i in range(1, len(words))]
        if max(gaps or [0]) > max(6.0, float(max_len)):
            raise RuntimeError("Narration timing has an unexplained long gap. Re-transcribe narration before generating media; no new shots submitted.")

    # IMPORTANT for long-form narration: a TTS/transcriber can return a whole
    # paragraph as one 20-60s sentence.  The old planner only split *between*
    # sentences, which could turn a 5-minute video into ~8 enormous shots.
    # Force long timed sentences into visual beats close to the preset max.
    if words and sents:
        sents = _split_long_sentences(words, sents, float(max_len))

    # Window sentences into shots without allowing the *next* sentence to push a
    # visual beat far beyond max_len.  v4.1 flushed only after overshoot, so an
    # 8s target could still become a 12-14s shot.
    windows, cur = [], []
    cur_start = sents[0]["start"] if sents else 0.0
    hook_done = False
    for sent in sents:
        if not cur:
            cur_start = sent["start"]
        proposed = sent["end"] - cur_start
        if cur and proposed > max_len:
            windows.append((cur, "hook" if not hook_done else "body"))
            hook_done = True
            cur = [sent]
            cur_start = sent["start"]
        else:
            cur.append(sent)
        span = cur[-1]["end"] - cur_start
        if not hook_done and span >= min(3.0, max_len):
            windows.append((cur, "hook"))
            cur = []
            hook_done = True
    if cur:
        windows.append((cur, "hero_outro" if len(windows) >= 2 else "body"))

    shots: list[Shot] = []
    for i, (group, kind) in enumerate(windows):
        start, end = group[0]["start"], group[-1]["end"]
        # snap to previous end: video timeline must be gapless
        if shots:
            start = shots[-1].voice_end
        # last shot extends to narration end
        if i == len(windows) - 1:
            end = total_duration
        # merge tiny windows
        if end - start < 1.5 and shots:
            shots[-1].voice_end = end
            shots[-1].duration_target = round(end - shots[-1].voice_start, 2)
            shots[-1].narration += " " + " ".join(s["text"] for s in group)
            continue
        coverage = "hook" if kind == "hook" else ("hero_outro" if kind == "hero_outro"
                                                  else COVERAGE_CYCLE[(i - 1) % len(COVERAGE_CYCLE)])
        priority = "HERO" if coverage in ("hook", "hero_outro") else "NORMAL"
        motion = "high" if coverage == "hook" else ("low" if coverage == "insert" else "medium")
        ch = bible["characters"][0]["canonical"] if bible.get("characters") else "cinematic subject"
        loc = bible["locations"][0]["canonical"] if bible.get("locations") else "cinematic environment"
        # Map a long sequence of timed shots across the script beats instead of
        # assigning beat 1 to shot 1, beat 2 to shot 2 and then repeating the
        # final beat for the remaining 40+ shots.  This was a major cause of
        # semantic visual drift in five-minute list videos.
        if beats:
            beat_idx = group[0].get('beat_index', min(len(beats) - 1, int(i * len(beats) / max(1, len(windows)))))
            beat = beats[beat_idx]
        else:
            beat_idx, beat = 0, {}
        visual_intent = str(beat.get("visual_intent") or "").strip()
        scene_subject, scene_action, scene_environment = _scene_from_visual_intent(
            visual_intent, " ".join(x["text"] for x in group), loc, coverage)
        if bible.get("characters"):
            scene_subject = f"CHARACTER_01 ({ch})"
        if beat.get('image_prompt') or beat.get('motion_prompt'):
            # Authored imported scene intent wins over the generic keyword-based
            # B-roll mapper, which could otherwise replace the reviewed action.
            scene_action = visual_intent
        shot = Shot(
            shot_id=f"shot_{i+1:03d}",
            voice_start=round(start, 2), voice_end=round(end, 2),
            duration_target=round(end - start, 2),
            narration=" ".join(s["text"] for s in group)[:400],
            coverage=coverage,
            visual_goal=(f"{beat.get('name','story')}: {visual_intent}" if visual_intent
                         else f"{coverage}: support narration beat ({beat.get('name','story')})"),
            subject=scene_subject,
            subject_action=scene_action,
            environment=scene_environment,
            camera_framing=FRAMING[coverage], camera_movement=MOVES[coverage],
            lighting=bible["lighting"], color_palette=preset.get("color_treatment", ""),
            motion_intensity=motion, priority=priority,
            transition_in="cut", transition_out="cut",
            qc_threshold=80 if priority == "HERO" else 70,
        )
        route = router.route(priority=priority, motion=motion,
                             needs_ref=bool(bible.get("characters")))
        shot.provider, shot.model = route["provider"], route["model"]
        shot.num_candidates = route["candidates"]
        shot.gen_duration = 8 if shot.duration_target > 5 else (6 if shot.duration_target > 3.5 else 4)
        shots.append(shot)

    # chain continuity: each shot may use previous end frame
    for i in range(1, len(shots)):
        shots[i].start_frame = f"{{prev_end_frame:{shots[i-1].shot_id}}}"
    manifest.shots = shots
    oversized = [s.shot_id for s in shots if s.duration_target > max(16, float(max_len) * 2)]
    if oversized and len(shots) > 1:
        raise RuntimeError("Shot timing QC blocked oversized visual windows: " + ", ".join(oversized) +
                           ". Repair narration timestamps before generating media.")
    manifest.status = "planned"
    return manifest
