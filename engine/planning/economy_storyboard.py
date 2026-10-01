"""Credit-aware storyboard router for long-form / economy productions.

The planner deliberately spends Flow credits only on scenes where real motion adds
meaning. Remaining scenes use free generated stills with local camera motion or
stock footage.  It is deterministic and works without an LLM/API.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

ACTION_WORDS = {
    "run", "running", "walk", "walking", "drive", "driving", "fly", "flying",
    "transform", "transforms", "explode", "explosion", "open", "opens", "close",
    "turn", "move", "moving", "dance", "fall", "rise", "reveal", "reveals",
    "build", "building", "assemble", "launch", "arrive", "enter", "leave",
    "pour", "cook", "cut", "mix", "travel", "race", "fight", "chase", "zoom",
}
STOCK_WORDS = {
    "city", "office", "laptop", "computer", "phone", "street", "traffic", "train",
    "airport", "mountain", "beach", "forest", "nature", "money", "market", "business",
    "team", "meeting", "food", "kitchen", "coffee", "factory", "server", "cloud",
    "robot", "technology", "student", "classroom", "hospital", "doctor", "gym",
}
DOMAIN_QUERIES = (
    ({"ai", "agents", "automation", "algorithm", "algorithms", "software", "computing"},
     "software engineer computer automation technology office"),
    ({"speak", "speaking", "communication", "meeting", "executive", "presentation", "pressure"},
     "professional business meeting confident speaker office"),
    ({"resume", "interview", "career", "job", "workplace"},
     "professional career interview resume office"),
    ({"study", "student", "learn", "exam", "education"},
     "student learning focused study desk classroom"),
    ({"money", "finance", "budget", "saving", "invest"},
     "personal finance budgeting calculator planning"),
    ({"health", "fitness", "exercise", "workout"},
     "healthy exercise fitness training wellness"),
)
EXPLAINER_WORDS = {
    "means", "because", "reason", "principle", "example", "fact", "data", "number",
    "step", "method", "concept", "definition", "difference", "problem", "solution",
}


@dataclass
class EconomyOptions:
    max_credits: float = 50.0
    video_share: float = 0.20
    stock_share: float = 0.60
    # ``flow_scenes`` is an explicit target. ``max_flow_scenes`` remains a cap
    # for backwards compatibility. Budget safety always wins.
    flow_scenes: int | None = None
    max_flow_scenes: int | None = None
    stock_scenes: int | None = None
    dynamic_video_scenes: int | None = None
    prefer_stock: bool = True
    reserve_pct: float = 15.0


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z]{3,}", (text or "").lower()))


def _motion_score(shot) -> float:
    toks = _tokens(" ".join([shot.narration, shot.visual_goal, shot.subject_action, shot.coverage]))
    score = 0.0
    if shot.coverage == "hook":
        score += 50
    if shot.coverage == "hero_outro":
        score += 38
    if shot.motion_intensity == "high":
        score += 32
    elif shot.motion_intensity == "medium":
        score += 14
    if toks & ACTION_WORDS:
        score += 24 + min(12, len(toks & ACTION_WORDS) * 3)
    if shot.coverage in ("broll", "primary"):
        score += 5
    if toks & EXPLAINER_WORDS:
        score -= 16
    if shot.coverage in ("insert", "closeup") and shot.motion_intensity == "low":
        score -= 10
    return score


def _stock_score(shot) -> float:
    toks = _tokens(" ".join([shot.narration, shot.visual_goal, shot.environment, shot.subject]))
    score = len(toks & STOCK_WORDS) * 8
    if shot.coverage == "broll":
        score += 20
    # Strong character continuity is a bad stock use case.
    if "CHARACTER_01" in (shot.subject or ""):
        score -= 30
    if shot.priority == "HERO":
        score -= 15
    return score


def _stock_query(shot) -> str:
    source = " ".join([shot.narration, shot.visual_goal, shot.environment, shot.subject])
    toks = _tokens(source)
    for keys, query in DOMAIN_QUERIES:
        if toks & keys:
            return query
    ordered = re.findall(r"[A-Za-z]{3,}", source.lower())
    picked = []
    for word in ordered:
        if word in STOCK_WORDS and word not in picked:
            picked.append(word)
    if not picked:
        stop = {"this", "that", "with", "from", "your", "have", "will", "when", "into", "about"}
        picked = [w.lower() for w in re.findall(r"[A-Za-z]{4,}", shot.narration or "")
                  if w.lower() not in stop][:5]
    return " ".join(picked[:5]) or "professional educational presentation"


def _supported_duration(seconds: float) -> int:
    # Omni 360p supports 4/6/8/10s. Match the narration window without paying
    # for more than necessary; local timeline trims excess cleanly.
    if seconds <= 4.2:
        return 4
    if seconds <= 6.2:
        return 6
    if seconds <= 8.2:
        return 8
    return 10



def _spread_ranked(shots: list, score_fn, count: int, excluded: set[str] | None = None) -> list:
    """Pick high-scoring scenes while keeping them distributed across the film."""
    excluded = excluded or set()
    pool = [s for s in shots if s.shot_id not in excluded]
    if count <= 0 or not pool:
        return []
    count = min(count, len(pool))
    # Desired anchor positions create an editorial cadence; semantic score still
    # decides which nearby shot is most appropriate.
    anchors = [(i + 0.5) * len(shots) / count for i in range(count)]
    chosen = []
    used = set(excluded)
    for anchor in anchors:
        candidates = []
        for idx, sh in enumerate(shots):
            if sh.shot_id in used:
                continue
            semantic = float(score_fn(sh))
            distance = abs((idx + 0.5) - anchor)
            # Strong semantics can move a clip a few shots from the ideal beat,
            # but cannot collapse all dynamic media into one section.
            combined = semantic - distance * 4.0
            candidates.append((combined, semantic, -distance, sh))
        if not candidates:
            break
        candidates.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
        sh = candidates[0][3]
        chosen.append(sh); used.add(sh.shot_id)
    return chosen

def assign_storyboard_economy(manifest, router, options: EconomyOptions) -> dict:
    """Mutate shots with media strategy/provider/model while respecting budget.

    Returns a serialisable report used by the UI/CLI before anything is generated.
    """
    shots = list(manifest.shots)
    n = len(shots)
    if not n:
        return {"shots": [], "estimated_credits": 0, "flow_scenes": 0,
                "stock_scenes": 0, "image_scenes": 0}

    usable = max(0.0, float(options.max_credits))
    usable = usable / (1.0 + max(0.0, options.reserve_pct) / 100.0)
    auto_desired_flow = max(1 if n <= 4 else 2, int(math.ceil(n * max(0.0, options.video_share))))
    if options.flow_scenes is not None:
        desired_flow = max(0, min(n, int(options.flow_scenes)))
    else:
        desired_flow = auto_desired_flow
    if options.max_flow_scenes is not None:
        desired_flow = min(desired_flow, max(0, int(options.max_flow_scenes)))

    selected: set[str] = set()
    spent = 0.0
    # v5.6 treats dynamic clips as editorial beats, not simply the highest motion
    # scores. Select around evenly-spaced anchors while still preferring scenes
    # where real motion adds meaning.
    for s in _spread_ranked(shots, _motion_score, desired_flow):
        if len(selected) >= desired_flow:
            break
        dur = _supported_duration(s.duration_target)
        cost = router.model_cost("omni_draft", dur)
        if spent + cost <= usable + 1e-9:
            selected.add(s.shot_id)
            spent += cost

    if options.stock_scenes is not None:
        stock_target = max(0, min(n - len(selected), int(options.stock_scenes)))
    elif options.dynamic_video_scenes is not None:
        stock_target = max(0, min(n - len(selected), int(options.dynamic_video_scenes) - len(selected)))
    else:
        stock_target = int(round(n * max(0.0, options.stock_share))) if options.prefer_stock else 0
    stock_pick = _spread_ranked(shots, _stock_score, stock_target, excluded=selected) if options.prefer_stock else []
    stock_ids = {s.shot_id for s in stock_pick}

    rows = []
    for s in shots:
        dur = _supported_duration(s.duration_target)
        if s.shot_id in selected:
            s.media_strategy = "flow_video"
            s.provider = "flow"
            s.model = "omni_draft"
            s.gen_duration = dur
            s.num_candidates = 1
            s.estimated_credits = router.model_cost("omni_draft", dur)
            s.strategy_reason = "meaningful motion / hero beat within credit budget"
        elif s.shot_id in stock_ids:
            s.media_strategy = "stock"
            s.provider = "stock"
            s.model = "stock"
            s.gen_duration = max(4, int(math.ceil(s.duration_target)))
            s.num_candidates = 1
            s.estimated_credits = 0.0
            s.stock_query = _stock_query(s)
            s.strategy_reason = "generic real-world B-roll is cheaper and more natural as stock"
        else:
            s.media_strategy = "image_motion"
            s.provider = "image"
            s.model = "image_pair_motion"
            s.gen_duration = max(4, int(math.ceil(s.duration_target)))
            s.num_candidates = 1
            s.estimated_credits = 0.0
            s.strategy_reason = "free opening/closing frames + local cinematic motion"
        rows.append({
            "shot_id": s.shot_id,
            "start": s.voice_start,
            "end": s.voice_end,
            "duration": s.duration_target,
            "strategy": s.media_strategy,
            "provider": s.provider,
            "model": s.model,
            "estimated_credits": s.estimated_credits,
            "motion_score": round(_motion_score(s), 1),
            "stock_score": round(_stock_score(s), 1),
            "reason": s.strategy_reason,
        })

    total = round(sum(float(s.estimated_credits or 0) for s in shots), 1)
    reserve = round(total * max(0.0, options.reserve_pct) / 100.0, 1)
    return {
        "profile": "STORYBOARD_ECONOMY",
        "shots": rows,
        "flow_scenes": sum(s.media_strategy == "flow_video" for s in shots),
        "stock_scenes": sum(s.media_strategy == "stock" for s in shots),
        "image_scenes": sum(s.media_strategy == "image_motion" for s in shots),
        "estimated_credits": total,
        "retry_reserve": reserve,
        "projected_total": round(total + reserve, 1),
        "budget": float(options.max_credits),
        "requested_flow_scenes": (int(options.flow_scenes) if options.flow_scenes is not None else None),
        "auto_desired_flow_scenes": int(auto_desired_flow),
        "desired_flow_scenes": int(desired_flow),
        "requested_stock_scenes": (int(options.stock_scenes) if options.stock_scenes is not None else None),
        "requested_dynamic_video_scenes": (int(options.dynamic_video_scenes) if options.dynamic_video_scenes is not None else None),
        "budget_limited": len(selected) < desired_flow,
        "within_budget": total + reserve <= float(options.max_credits) + 1e-9,
    }
