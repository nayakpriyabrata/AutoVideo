"""Review-first stock B-roll cutaways for production renders and Clip Studio.

Candidates are downloaded only after an explicit search action, displayed for
manual approval, and bound to their exact local-file SHA-256 before render.
B-roll is visual-only: it never submits Flow/Veo generations or changes the
narration/music timeline.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

REVIEW_SCHEMA = 1
MIN_CUTAWAY_SECONDS = 0.5
MAX_CUTAWAY_SECONDS = 6.0
MAX_CANDIDATES = 10


def sha256_file(path: str | os.PathLike) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: str | os.PathLike, default=None):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, TypeError):
        return default


def _write_json(path: str | os.PathLike, value: dict) -> None:
    path = os.path.abspath(os.fspath(path))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _safe_id(text: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(text or ""))
    return value.strip("_")[:72] or "cutaway"


def _search_query(text: str) -> str:
    """Reduce narration/context to a short, concrete stock-search query."""
    stop = {
        "about", "after", "again", "also", "among", "because", "before",
        "being", "between", "could", "does", "during", "every", "first",
        "from", "have", "into", "just", "more", "most", "other", "over",
        "same", "should", "some", "such", "than", "that", "their", "them",
        "then", "there", "these", "they", "this", "through", "today",
        "under", "very", "what", "when", "where", "which", "while",
        "with", "would", "your", "you", "are", "can", "for", "how",
        "its", "not", "our", "the", "and", "but", "was", "were", "will",
        "has", "had", "his", "her", "she", "him", "who", "need", "needs",
        "into", "while", "make", "makes", "show", "shows", "using", "used",
        "background", "cinematic", "macro", "closeup", "close-up", "shot",
        "camera", "view", "video", "clip", "scene", "demonstrate", "action",
        "framing", "portrait", "vertical", "quality", "visually", "natural",
        "reel", "highlight", "footage", "broll", "b-roll", "people",
    }
    # Preserve non-Latin transcript keywords too. Users can add an English hint
    # in the review UI when a stock provider does not index their language well.
    words = re.findall(r"[^\W_][\w'-]{2,}", str(text or "").lower(), flags=re.UNICODE)
    picked = []
    for word in words:
        word = word.strip("'-")
        if len(word) < 3 or word in stop or word in picked:
            continue
        picked.append(word)
        if len(picked) >= 8:
            break
    return " ".join(picked) or "nature city technology people"


def _file_duration(path: str) -> float | None:
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=30)
        duration = float((proc.stdout or "").strip())
        return duration if proc.returncode == 0 and math.isfinite(duration) and duration > 0 else None
    except Exception:
        return None


def _file_dimensions(path: str) -> tuple[int, int]:
    """Read the encoded output frame size, not a stock asset's preview size."""
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "json", path],
            capture_output=True, text=True, timeout=30)
        streams = json.loads(proc.stdout or "{}").get("streams") or []
        width, height = int(streams[0].get("width") or 0), int(streams[0].get("height") or 0)
        if proc.returncode == 0 and width >= 2 and height >= 2:
            return width, height
    except Exception:
        pass
    raise RuntimeError("Could not determine the rendered highlight's frame size; install/repair ffprobe.")


def _public_metadata(meta: dict, query: str) -> dict:
    """Keep attribution/useful provenance; never retain raw media URLs."""
    meta = meta if isinstance(meta, dict) else {}
    source = str(meta.get("source") or "stock")[:80]
    local_source = meta.get("local_source")
    return {
        "source": source,
        "query": query[:180],
        "license": str(meta.get("license") or
                        ("User-supplied local stock; verify its licence" if source == "local-stock"
                         else "Review the stock provider's current licence terms"))[:180],
        "page_url": str(meta.get("page_url") or "")[:500],
        "creator": str(meta.get("creator") or "")[:160],
        "asset_id": str(meta.get("asset_id") or "")[:100],
        "local_source_name": os.path.basename(str(local_source)) if local_source else "",
    }


def _fetch_candidates(slots: list[dict], assets_dir: str, vertical: bool) -> list[dict]:
    """Resolve a bounded set from the local library, then configured stock sources."""
    from .providers.stock_provider import StockProvider

    os.makedirs(assets_dir, exist_ok=True)
    candidates: list[dict | None] = [None] * len(slots)
    unresolved: list[int] = []
    used_local: set[str] = set()
    for slot in slots:
        excluded = slot.get("exclude_local") or slot.get("source_video")
        if excluded:
            try:
                used_local.add(os.path.realpath(str(excluded)))
            except Exception:
                pass
    for index, slot in enumerate(slots):
        query = _search_query(slot.get("query", ""))
        slot["query"] = query
        local = StockProvider._pick_local(query, excluded=used_local)
        if local:
            used_local.add(os.path.realpath(local))
            candidates[index] = {
                "source_path": local,
                "meta": {"source": "local-stock", "local_source": os.path.realpath(local),
                         "license": "User-supplied local stock; verify its licence"},
            }
        else:
            unresolved.append(index)

    excluded: dict[str, list[str]] = {}
    for index in unresolved:
        slot = slots[index]
        slot_dir = os.path.join(assets_dir, _safe_id(slot.get("candidate_id", f"cut_{index+1:02d}")))
        os.makedirs(slot_dir, exist_ok=True)
        try:
            from .stock_video import get_stock_videos
            result = get_stock_videos(
                [slot["query"]], slot["query"], slot_dir, vertical=vertical,
                source_mode=os.getenv("AUTOVIDEO_STOCK_SOURCE", "auto"),
                excluded_assets=excluded)
            clips = result.get("clips") or []
            metadata = result.get("metadata") or []
            if not clips:
                errors = [str(x).strip() for x in (result.get("errors") or []) if str(x).strip()]
                slot["search_error"] = (" ".join(errors[:2])[:360] or
                                        "No matching downloadable stock video was found. Check the stock source and network settings.")
            if clips:
                meta = metadata[0] if metadata else {"source": result.get("source", "stock")}
                source = str(meta.get("source") or result.get("source") or "stock")
                asset_id = str(meta.get("asset_id") or "")
                if asset_id:
                    excluded.setdefault(source, []).append(asset_id)
                candidates[index] = {"source_path": clips[0], "meta": meta}
                # The shared stock helper writes its raw download URL to a
                # temporary sidecar. Keep only sanitized public provenance in
                # our review file; signed media URLs are not needed after download.
                for clip_path in clips:
                    sidecar = str(clip_path) + ".source.json"
                    if os.path.isfile(sidecar):
                        try:
                            os.remove(sidecar)
                        except OSError:
                            pass
        except Exception as exc:
            # Never echo request exception strings: API/media URLs can contain
            # credentials or signed-download tokens.
            slot["search_error"] = (
                f"Stock search failed ({type(exc).__name__}). Check network/source settings and retry; "
                "no substitute clip was inserted."
            )

    out: list[dict] = []
    for index, slot in enumerate(slots):
        found = candidates[index]
        if not found:
            slot["status"] = "not_found"
            slot["search_error"] = slot.get("search_error") or "No matching configured stock asset was found."
            out.append(slot)
            continue
        src = os.path.abspath(os.fspath(found["source_path"]))
        if not os.path.isfile(src) or os.path.getsize(src) < 50_000:
            slot["status"] = "invalid_asset"
            slot["search_error"] = "Candidate is missing or too small to validate as video."
            out.append(slot)
            continue
        duration = _file_duration(src)
        if duration is not None and duration < MIN_CUTAWAY_SECONDS:
            slot["status"] = "invalid_asset"
            slot["search_error"] = "Candidate video is shorter than the minimum cutaway duration."
            out.append(slot)
            continue
        dest = os.path.abspath(os.path.join(
            assets_dir, _safe_id(slot.get("candidate_id", f"cut_{index+1:02d}")) + ".mp4"))
        if os.path.realpath(src) != os.path.realpath(dest):
            shutil.copy2(src, dest)
        slot.update({
            "status": "ready",
            "path": dest,
            "sha256": sha256_file(dest),
            "candidate_duration": round(duration, 3) if duration else None,
            "approved": False,
            "rights_reviewed": False,
            **_public_metadata(found.get("meta") or {}, slot.get("query", "")),
        })
        slot.pop("search_error", None)
        out.append(slot)
    return out


def prepare_review(review_path: str, slots: list[dict], *, workflow: str,
                   max_candidates: int = 3, default_duration: float = 2.0,
                   vertical: bool = True, replace: bool = False) -> dict:
    """Search and persist reviewable stock candidates without applying any."""
    if type(max_candidates) is not int or not 1 <= max_candidates <= MAX_CANDIDATES:
        raise ValueError(f"Candidate limit must be 1–{MAX_CANDIDATES}.")
    if not isinstance(default_duration, (int, float)) or not math.isfinite(float(default_duration)):
        raise ValueError("Cutaway duration must be finite.")
    if not MIN_CUTAWAY_SECONDS <= float(default_duration) <= MAX_CUTAWAY_SECONDS:
        raise ValueError(f"Cutaway duration must be {MIN_CUTAWAY_SECONDS:g}–{MAX_CUTAWAY_SECONDS:g} seconds.")
    review_path = os.path.abspath(review_path)
    if os.path.isfile(review_path) and not replace:
        raise FileExistsError("A B-roll review already exists. Confirm replacement before searching again.")
    if os.path.isfile(review_path) and replace:
        backup = review_path + f".previous-{int(time.time())}"
        shutil.copy2(review_path, backup)

    selected = [dict(slot) for slot in slots[:max_candidates]]
    if not selected:
        raise ValueError("No scene boundaries or highlight clips are available for B-roll suggestions.")
    for index, slot in enumerate(selected, 1):
        slot["candidate_id"] = _safe_id(slot.get("candidate_id") or f"cut_{index:02d}")
        slot["default_duration"] = float(default_duration)
        slot.setdefault("duration", float(default_duration))
        slot.setdefault("approved", False)
        slot.setdefault("rights_reviewed", False)
        slot.setdefault("decision", "pending")
    review_id = str(time.time_ns())
    assets_dir = os.path.join(os.path.dirname(review_path), "broll",
                              f"{Path(review_path).stem}-{review_id}")
    candidates = _fetch_candidates(selected, assets_dir, bool(vertical))
    report = {
        "schema_version": REVIEW_SCHEMA,
        "workflow": str(workflow),
        "review_id": review_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "review_required": True,
        "audio_policy": "visual_only_preserve_existing_audio_and_duration",
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    _write_json(review_path, report)
    return report


def load_review(review_path: str) -> dict:
    report = _read_json(review_path)
    if not isinstance(report, dict) or report.get("schema_version") != REVIEW_SCHEMA:
        raise ValueError("B-roll review file is missing or has an unsupported schema.")
    report["path"] = os.path.abspath(review_path)
    return report


def save_review(review_path: str, updates: dict[str, dict]) -> dict:
    """Persist an explicit approve/skip decision and exact-file review state."""
    report = load_review(review_path)
    if not isinstance(updates, dict):
        raise ValueError("B-roll review edits must be a mapping.")
    for candidate in report.get("candidates", []):
        update = updates.get(candidate.get("candidate_id"), {})
        if not update:
            continue
        requested = str(update.get("decision") or "").strip().lower()
        if not requested:
            # Backward-compatible callers can still submit the old approval
            # fields. An unchecked approval is pending, never an implicit skip.
            requested = "approve" if bool(update.get("approved")) else "pending"
        if requested in {"approved", "approve"}:
            requested = "approve"
        elif requested in {"skipped", "skip"}:
            requested = "skip"
        elif requested in {"pending", ""}:
            requested = "pending"
        else:
            raise ValueError("B-roll decision must be approve, skip, or pending.")

        if requested == "skip":
            candidate["decision"] = "skipped"
            candidate["approved"] = False
            candidate["rights_reviewed"] = False
            candidate["status"] = "skipped"
            continue
        if requested == "pending":
            candidate["decision"] = "pending"
            candidate["approved"] = False
            candidate["rights_reviewed"] = False
            if candidate.get("status") == "approved":
                candidate["status"] = "pending_review"
            continue

        path = str(candidate.get("path") or "")
        same_file = bool(path and os.path.isfile(path)
                         and sha256_file(path) == candidate.get("sha256"))
        if not same_file:
            candidate["decision"] = "pending"
            candidate["approved"] = False
            candidate["rights_reviewed"] = False
            candidate["status"] = "asset_changed"
            continue
        start = float(update.get("start", candidate.get("start", 0)))
        duration = float(update.get("duration", candidate.get("duration", candidate.get("default_duration", 2))))
        if not math.isfinite(start) or start < 0:
            raise ValueError("Cutaway start must be a finite non-negative time.")
        if not math.isfinite(duration) or not MIN_CUTAWAY_SECONDS <= duration <= MAX_CUTAWAY_SECONDS:
            raise ValueError(f"Cutaway duration must be {MIN_CUTAWAY_SECONDS:g}–{MAX_CUTAWAY_SECONDS:g} seconds.")
        slot_limit = float(candidate.get("clip_duration") or candidate.get("timeline_duration") or 0)
        if slot_limit > 0 and start + duration > slot_limit + 0.01:
            raise ValueError("Cutaway placement extends beyond its highlight/timeline.")
        candidate["start"] = round(start, 3)
        candidate["duration"] = round(duration, 3)
        candidate["rights_reviewed"] = bool(update.get("rights_reviewed", False))
        candidate["approved"] = candidate["rights_reviewed"]
        candidate["decision"] = "approved" if candidate["approved"] else "pending"
        candidate["status"] = "approved" if candidate["approved"] else "pending_review"
    report.pop("path", None)
    report["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    _write_json(review_path, report)
    return load_review(review_path)


def validate_review_decisions(review_path: str, workflow: str | None = None) -> dict:
    """Require a deliberate approve-or-skip decision for every suggestion."""
    report = load_review(review_path)
    if workflow and report.get("workflow") != workflow:
        raise ValueError(f"This B-roll review does not belong to {workflow}.")
    pending = []
    for candidate in report.get("candidates", []):
        decision = str(candidate.get("decision") or "").lower()
        if not decision:
            # Migrate a previously saved approval only when both checks were
            # already persisted; an unchecked suggestion is never a skip.
            decision = ("approved" if candidate.get("approved") and candidate.get("rights_reviewed")
                        else "pending")
        if decision not in {"approved", "skipped"}:
            pending.append(str(candidate.get("candidate_id") or "candidate"))
        elif decision == "approved" and not (candidate.get("approved") and candidate.get("rights_reviewed")):
            pending.append(str(candidate.get("candidate_id") or "candidate"))
        elif decision == "skipped" and (candidate.get("approved") or candidate.get("rights_reviewed")):
            pending.append(str(candidate.get("candidate_id") or "candidate"))
    if pending:
        raise ValueError(
            "B-roll review is incomplete. Explicitly approve or skip every suggestion and save decisions: "
            + ", ".join(pending[:10])
        )
    return report


def approved_video_overlays(review_path: str, total_duration: float) -> list[dict]:
    """Return only reviewed exact stock files, rejecting stale/unsafe placements."""
    report = load_review(review_path)
    if report.get("workflow") != "production":
        raise ValueError("This B-roll review does not belong to a production render.")
    total = float(total_duration)
    if not math.isfinite(total) or total <= 0:
        raise ValueError("Rendered timeline duration is invalid.")
    result = []
    for candidate in report.get("candidates", []):
        if str(candidate.get("decision") or "").lower() == "skipped":
            continue
        if not (candidate.get("approved") and candidate.get("rights_reviewed")):
            continue
        path = os.path.abspath(str(candidate.get("path") or ""))
        if not os.path.isfile(path) or sha256_file(path) != candidate.get("sha256"):
            raise ValueError(f"Approved B-roll file changed or disappeared: {candidate.get('candidate_id')}")
        start = float(candidate.get("start", 0))
        duration = float(candidate.get("duration", 0))
        if (not math.isfinite(start) or not math.isfinite(duration) or start < 0
                or duration < MIN_CUTAWAY_SECONDS or duration > MAX_CUTAWAY_SECONDS
                or start + duration > total + 0.01):
            raise ValueError(f"Approved B-roll placement is outside the final timeline: {candidate.get('candidate_id')}")
        result.append({
            "path": path, "start": round(start, 3), "end": round(start + duration, 3),
            "in": 0.0, "candidate_id": candidate.get("candidate_id"),
            "query": candidate.get("query", ""), "source": candidate.get("source", "stock"),
            "license": candidate.get("license", ""), "page_url": candidate.get("page_url", ""),
            "creator": candidate.get("creator", ""), "asset_id": candidate.get("asset_id", ""),
        })
    return result


def _job_slots(factory, job_id: str, max_candidates: int, default_duration: float,
               query_hint: str = "") -> tuple[list[dict], bool]:
    manifest = factory.pm.load_manifest(job_id)
    shots = list(manifest.shots or [])
    if len(shots) < 2:
        raise ValueError("At least two storyboard scenes are needed for between-scene cutaways.")
    starts = {}
    cursor = 0.0
    for shot in shots:
        starts[shot.shot_id] = cursor
        cursor += max(0.1, float(shot.voice_end) - float(shot.voice_start))
    boundaries = []
    for index, (previous, following) in enumerate(zip(shots, shots[1:]), 1):
        context = " ".join(filter(None, [
            query_hint, getattr(previous, "stock_query", ""), previous.subject, previous.visual_goal,
            previous.environment, getattr(following, "stock_query", ""), following.subject,
            following.visual_goal, following.environment, following.narration,
        ]))
        query = _search_query(context)
        boundary = float(starts[following.shot_id])
        boundaries.append({
            "candidate_id": f"gap_{index:02d}_{_safe_id(previous.shot_id)}_{_safe_id(following.shot_id)}",
            "slot_id": f"gap_{index:02d}",
            "label": f"Between {previous.shot_id} and {following.shot_id}",
            "after_shot_id": previous.shot_id,
            "before_shot_id": following.shot_id,
            "query": query,
            "start": min(boundary, max(0.0, cursor - float(default_duration))),
            "duration": float(default_duration),
            "timeline_duration": round(cursor, 3),
        })
    if len(boundaries) > max_candidates:
        # Spread a small number of cutaways evenly across the whole production.
        chosen_indices = []
        for index in range(max_candidates):
            candidate_index = int((index + 0.5) * len(boundaries) / max_candidates)
            candidate_index = min(len(boundaries) - 1, candidate_index)
            if candidate_index not in chosen_indices:
                chosen_indices.append(candidate_index)
        boundaries = [boundaries[index] for index in chosen_indices]
    vertical = str(getattr(manifest, "aspect", "9:16")) == "9:16"
    return boundaries, vertical


def prepare_job_review(factory, job_id: str, max_candidates: int = 3,
                       default_duration: float = 2.0, replace: bool = False,
                       query_hint: str = "") -> tuple[str, dict]:
    if type(max_candidates) is not int or not 1 <= max_candidates <= MAX_CANDIDATES:
        raise ValueError(f"Candidate limit must be 1–{MAX_CANDIDATES}.")
    slots, vertical = _job_slots(factory, job_id, max_candidates, default_duration, query_hint=query_hint)
    dirs = factory.pm.dirs(job_id)
    review_path = os.path.join(dirs["render"], "broll_review.json")
    review = prepare_review(review_path, slots, workflow="production", max_candidates=max_candidates,
                            default_duration=default_duration, vertical=vertical, replace=replace)
    review["path"] = os.path.abspath(review_path)
    return review_path, review


def _ensure_clip_caption_path(highlight: dict, output_dir: str) -> str:
    path = os.path.abspath(str(highlight.get("caption_ass_path") or ""))
    if path and os.path.isfile(path):
        return path
    sidecar = str(highlight.get("transcript_sidecar") or "")
    data = _read_json(sidecar, {}) if sidecar else {}
    words = data.get("words") if isinstance(data, dict) else None
    if not words:
        raise ValueError("This highlight has no saved caption timing; regenerate it before applying B-roll.")
    from .render.captions_ass import build_captions
    tag = _safe_id(Path(str(highlight.get("output") or "clip")).stem)
    caption_root = os.path.join(output_dir, "_clip_work", "broll_captions", tag)
    width, height = _file_dimensions(str(highlight.get("output") or ""))
    aspect = "9:16" if height > width else "16:9"
    cap = build_captions(words, caption_root, template="OPUS", aspect=aspect,
                         W=width, H=height,
                         duration=float(highlight.get("duration") or data.get("source_end", 0) - data.get("source_start", 0)))
    if not cap.get("ass") or not os.path.isfile(cap["ass"]):
        raise ValueError("Could not rebuild the original highlight captions for the B-roll cutaway.")
    return os.path.abspath(cap["ass"])


def prepare_clip_studio_review(result: dict, max_candidates: int = 3,
                               default_duration: float = 2.0,
                               replace: bool = False,
                               query_hint: str = "") -> tuple[str, dict]:
    highlights = list(result.get("highlights") or [])
    if not highlights:
        raise ValueError("No rendered highlights are available for B-roll review.")
    if type(max_candidates) is not int or not 1 <= max_candidates <= MAX_CANDIDATES:
        raise ValueError(f"Candidate limit must be 1–{MAX_CANDIDATES}.")
    output_dir = os.path.abspath(os.path.dirname(str(highlights[0].get("output") or "")) or ".")
    source_video = os.path.abspath(str(result.get("source") or ""))
    if not os.path.isfile(source_video):
        raise FileNotFoundError("Original local source video is unavailable; the existing highlight was not changed.")
    source_digest = sha256_file(source_video)
    run_key = hashlib.sha256(str(result.get("selection_report") or result.get("source") or time.time_ns()).encode()).hexdigest()[:12]
    review_path = os.path.join(output_dir, f"broll-review-{run_key}.json")
    slots = []
    for index, highlight in enumerate(highlights[:max_candidates], 1):
        output = os.path.abspath(str(highlight.get("output") or ""))
        if not os.path.isfile(output):
            continue
        duration = float(highlight.get("duration") or 0)
        if duration <= 0.5:
            continue
        cut_duration = min(float(default_duration), MAX_CUTAWAY_SECONDS, duration - 0.5)
        start = min(max(0.0, round(duration * 0.42, 3)), max(0.0, duration - cut_duration))
        captions = _ensure_clip_caption_path(highlight, output_dir)
        frame_width, frame_height = _file_dimensions(output)
        face_x = float(highlight.get("face_center_x", 0.5) or 0.5)
        slots.append({
            "candidate_id": f"clip_{index:02d}_{_safe_id(Path(output).stem)}",
            "slot_id": f"clip_{index:02d}",
            "label": f"Cutaway inside {Path(output).name}",
            "query": " ".join(filter(None, [
                str(query_hint or "").strip(),
                str(highlight.get("title") or "").strip(),
                str(highlight.get("text") or "").strip(),
            ])),
            "start": start,
            "duration": cut_duration,
            "clip_output": output,
            "clip_output_sha256": sha256_file(output),
            "source_video": source_video,
            "source_video_sha256": source_digest,
            "source_start": float(highlight.get("start") or 0),
            "clip_duration": duration,
            "caption_ass_path": captions,
            "framing": str(highlight.get("framing") or "face-crop"),
            "output_width": frame_width,
            "output_height": frame_height,
            "face_center_x": face_x,
            "title": str(highlight.get("title") or "")[:120],
        })
    if not slots:
        raise ValueError("No eligible highlight clips were found.")
    first_slot = slots[0]
    vertical = int(first_slot.get("output_height", 0)) > int(first_slot.get("output_width", 0))
    report = prepare_review(review_path, slots, workflow="clip_studio", max_candidates=max_candidates,
                            default_duration=default_duration, vertical=vertical, replace=replace)
    report["path"] = os.path.abspath(review_path)
    return review_path, report


def _render_clip_studio_cutaway(candidate: dict) -> str:
    from .clipping import framing_filter
    from .render.ffmpeg_renderer import _esc_filter_path, _fontsdir, ffmpeg_exe, has_subtitles_filter

    source = os.path.abspath(str(candidate.get("source_video") or ""))
    original = os.path.abspath(str(candidate.get("clip_output") or ""))
    stock = os.path.abspath(str(candidate.get("path") or ""))
    captions = os.path.abspath(str(candidate.get("caption_ass_path") or ""))
    for path in (source, original, stock, captions):
        if not os.path.isfile(path):
            raise FileNotFoundError(f"B-roll edit input is unavailable: {os.path.basename(path)}")
    if candidate.get("source_video_sha256") and sha256_file(source) != candidate["source_video_sha256"]:
        raise ValueError("Original source video changed after B-roll review; no cutaway was rendered.")
    if candidate.get("clip_output_sha256") and sha256_file(original) != candidate["clip_output_sha256"]:
        raise ValueError("Original highlight changed after B-roll review; no cutaway was rendered.")
    if not has_subtitles_filter():
        raise RuntimeError("FFmpeg subtitle support is required to keep the approved highlight captions visible.")

    source_start = float(candidate["source_start"])
    clip_duration = float(candidate["clip_duration"])
    start = float(candidate["start"])
    cut_duration = float(candidate["duration"])
    if (not all(math.isfinite(x) for x in (source_start, clip_duration, start, cut_duration))
            or source_start < 0 or clip_duration <= 0 or start < 0
            or cut_duration < MIN_CUTAWAY_SECONDS or start + cut_duration > clip_duration + 0.01):
        raise ValueError("B-roll cutaway placement is outside the selected highlight.")

    face_x = max(0.15, min(0.85, float(candidate.get("face_center_x", 0.5))))
    framing_mode = str(candidate.get("framing") or "face-crop")
    frame_width, frame_height = _file_dimensions(original)
    if framing_mode == "face-crop" and (frame_width, frame_height) != (1080, 1920):
        raise ValueError("The selected face-crop highlight is not 1080x1920; refusing to alter its layout.")
    framing = framing_filter(framing_mode, face_x,
                             width=frame_width, height=frame_height)
    broll_filter = (
        f"scale={frame_width}:{frame_height}:force_original_aspect_ratio=increase:force_divisible_by=2,"
        f"crop={frame_width}:{frame_height},setsar=1,fps=30,format=yuv420p,"
        f"trim=duration={cut_duration:.3f},setpts=PTS-STARTPTS+{start:.3f}/TB")
    graph = [
        f"[0:v]{framing},fps=30,format=yuv420p,setpts=PTS-STARTPTS[base]",
        f"[2:v]{broll_filter}[broll]",
        f"[base][broll]overlay=0:0:eof_action=pass:shortest=0:repeatlast=0:"
        f"enable='between(t,{start:.3f},{start+cut_duration:.3f})'[cut]",
    ]
    font_dir = _fontsdir()
    subtitle_filter = f"subtitles='{_esc_filter_path(captions)}'"
    if font_dir:
        subtitle_filter += f":fontsdir='{_esc_filter_path(font_dir)}'"
    graph.append(f"[cut]{subtitle_filter}[vout]")
    output_stem = os.path.splitext(original)[0] + f"-broll-{_safe_id(candidate.get('candidate_id', 'cut'))}"
    output = output_stem + ".mp4"
    suffix = 2
    while os.path.exists(output):
        output = f"{output_stem}-{suffix}.mp4"
        suffix += 1
    cmd = [ffmpeg_exe(), "-y", "-ss", str(source_start), "-t", str(clip_duration), "-i", source,
           "-i", original, "-stream_loop", "-1", "-t", str(cut_duration), "-i", stock,
           "-filter_complex", ";".join(graph), "-map", "[vout]", "-map", "1:a?",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
           "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-t", f"{clip_duration:.3f}",
           "-movflags", "+faststart", output]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=max(180, min(1200, int(clip_duration * 30))))
    except subprocess.TimeoutExpired as exc:
        try:
            if os.path.isfile(output):
                os.remove(output)
        except OSError:
            pass
        raise RuntimeError("B-roll highlight edit timed out; original clip remains unchanged.") from exc
    if proc.returncode != 0 or not os.path.isfile(output) or os.path.getsize(output) < 50_000:
        detail = (proc.stderr or proc.stdout or "no output file")[-900:]
        try:
            if os.path.isfile(output):
                os.remove(output)
        except OSError:
            pass
        raise RuntimeError("B-roll highlight edit failed; original clip remains unchanged: " + detail)
    actual = _file_duration(output)
    if actual is not None and abs(actual - clip_duration) > max(0.5, clip_duration * 0.03):
        try:
            os.remove(output)
        except OSError:
            pass
        raise RuntimeError("B-roll highlight duration QC failed; original clip remains unchanged.")
    if _file_dimensions(output) != (frame_width, frame_height):
        try:
            os.remove(output)
        except OSError:
            pass
        raise RuntimeError("B-roll highlight framing QC failed; original clip remains unchanged.")
    return output


def apply_clip_studio_review(review_path: str) -> dict:
    """Render approved cutaways as separate files; the original highlights survive."""
    review_path = os.path.abspath(review_path)
    report = validate_review_decisions(review_path, workflow="clip_studio")
    applied, skipped = [], []
    for candidate in report.get("candidates", []):
        if not (candidate.get("approved") and candidate.get("rights_reviewed")):
            continue
        if not os.path.isfile(candidate.get("path", "")) or sha256_file(candidate["path"]) != candidate.get("sha256"):
            raise ValueError(f"Approved B-roll file changed or disappeared: {candidate.get('candidate_id')}")
        output = _render_clip_studio_cutaway(candidate)
        candidate["broll_output"] = output
        candidate["applied_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        applied.append(output)
    if not applied:
        skipped.append("No B-roll candidates were both approved and rights-reviewed.")
    report.pop("path", None)
    report["applied_outputs"] = applied
    report["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    _write_json(review_path, report)

    # Preserve the original outputs list and add separate B-roll copies to the
    # editorial report, never replacing the user's source-derived clip.
    highlights_path = os.path.join(os.path.dirname(review_path), "highlights.json")
    highlights_report = _read_json(highlights_path, {})
    if isinstance(highlights_report, dict) and highlights_report.get("highlights"):
        by_source = {os.path.realpath(x.get("clip_output", "")): x for x in report.get("candidates", [])
                     if x.get("broll_output")}
        for highlight in highlights_report["highlights"]:
            original = os.path.realpath(str(highlight.get("output") or ""))
            item = by_source.get(original)
            if item:
                highlight["broll_output"] = item["broll_output"]
                highlight["broll_cutaway"] = {
                    "start": item.get("start"), "duration": item.get("duration"),
                    "query": item.get("query"), "source": item.get("source"),
                    "license": item.get("license"), "page_url": item.get("page_url"),
                    "creator": item.get("creator"),
                }
        highlights_report["broll_outputs"] = applied
        _write_json(highlights_path, highlights_report)
    return {"review": review_path, "outputs": applied, "skipped": skipped,
            "candidates": report.get("candidates", [])}
