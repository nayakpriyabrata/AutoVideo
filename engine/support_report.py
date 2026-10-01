"""Read-only, bounded diagnostics for a saved job. Never opens a provider/browser.

Reports intentionally exclude settings, environment files, cookies, browser
profiles, prompts/scripts, and media bytes. Known credentials and URL signing
values are redacted; users should still review a report before sharing it.
"""
from __future__ import annotations
import datetime
import hashlib
import json
import platform
from pathlib import Path
import re
import sys
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .version import get_version

REDACTED = "[REDACTED]"
MAX_JSON_BYTES = 512 * 1024
MAX_TAIL_BYTES = 64 * 1024
MAX_PENDING_REQUESTS = 20
URL = re.compile(r"\b(?:https?|wss?)://[^\s<>\"'|]+", re.I)
DATA_URI = re.compile(r"\b(data:[^,\s|]+),[^\s<>\"'|]+", re.I)
PUBLIC_QUERY_KEYS = {"id", "assetid", "mediaid", "asset_id", "media_id", "w", "h", "width", "height", "format"}
SECRET_KEYS = {"authorization", "cookie", "setcookie", "headers", "password", "secret", "credentials",
               "token", "accesstoken", "refreshtoken", "apikey", "signature", "privatekey"}
MEDIA_SIGNATURE_KEYS = {"signature", "expectedsignature"}
AUTH_TEXT = re.compile(r"\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+", re.I)
SECRET_TEXT = re.compile(
    r"(\b(?:[A-Za-z0-9]+_)?(?:API[_-]?KEY|ACCESS[_-]?TOKEN|REFRESH[_-]?TOKEN|PASSWORD|SECRET)[\"']?\s*[:=]\s*)"
    r"(?:[\"'][^\"'\r\n]*[\"']|[^\s,;]+)", re.I)
COOKIE_TEXT = re.compile(r"(\b(?:Set-Cookie|Cookie)[\"']?\s*:\s*)[^\r\n]+", re.I)
PROVIDER_TOKEN = re.compile(r"\b(?:AIza[A-Za-z0-9_-]{20,}|(?:sk-|gsk_|xai-)[A-Za-z0-9_-]{16,})")


def _redact_url(match):
    try:
        url = urlsplit(match.group())
        host = url.netloc.rsplit("@", 1)[-1]  # Do not export URL user/password information.
        query = [(key, value if key.lower() in PUBLIC_QUERY_KEYS else REDACTED)
                 for key, value in parse_qsl(url.query, keep_blank_values=True)]
        return urlunsplit((url.scheme, host, url.path, urlencode(query), REDACTED if url.fragment else ""))
    except ValueError:
        return "[REDACTED URL]"


def redact(value):
    """Redact nested known credential fields while retaining useful media IDs."""
    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
            media_signature = (normalized in MEDIA_SIGNATURE_KEYS and isinstance(item, str)
                               and item.startswith(("IMG|", "VIDEO|")))
            secret = (normalized in SECRET_KEYS or normalized.endswith(("apikey", "password", "secret", "token")))
            clean[key] = redact(item) if media_signature or not secret else REDACTED
        return clean
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        value = DATA_URI.sub(lambda match: match.group(1) + ",[MEDIA OMITTED sha256="
                             + hashlib.sha256(match.group().encode()).hexdigest()[:16] + "]", value)
        value = URL.sub(_redact_url, value)
        value = AUTH_TEXT.sub(lambda match: match.group(1) + " " + REDACTED, value)
        value = SECRET_TEXT.sub(lambda match: match.group(1) + REDACTED, value)
        value = COOKIE_TEXT.sub(lambda match: match.group(1) + REDACTED, value)
        return PROVIDER_TOKEN.sub(REDACTED, value)
    return value


def resolve_job_dir(outputs_root, job_id: str) -> Path:
    if not job_id or job_id in (".", "..") or "/" in job_id or "\\" in job_id:
        raise ValueError("Expected a saved job ID, not a filesystem path")
    root = Path(outputs_root).resolve()
    job = (root / job_id).resolve()
    if job.parent != root:
        raise ValueError("Job directory must be inside the outputs folder")
    return job


def _inside(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root)
        return not path.is_symlink()
    except (ValueError, OSError):
        return False


def _read_json(root: Path, path: Path):
    if not _inside(root, path):
        return {"diagnostic_error": "Outside job directory or a symlink; not read"}
    if not path.is_file():
        return None
    try:
        if path.stat().st_size > MAX_JSON_BYTES:
            return {"diagnostic_error": "JSON exceeds diagnostic size limit"}
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"diagnostic_error": f"{type(exc).__name__}: could not read JSON"}


def build_support_report(job_dir, tail_lines: int = 80) -> dict:
    """Collect only diagnostic metadata; does not alter any existing job file."""
    root = Path(job_dir).resolve()
    manifest = _read_json(root, root / "production_manifest.json")
    if not isinstance(manifest, dict) or not manifest.get("job_id"):
        raise ValueError("Saved job manifest is missing or unreadable")
    if not 1 <= tail_lines <= 200:
        raise ValueError("tail_lines must be between 1 and 200")
    shots = manifest.get("shots") or []
    if not isinstance(shots, list) or any(not isinstance(shot, dict) for shot in shots):
        raise ValueError("Saved job shot metadata is unreadable")
    pause = _read_json(root, root / "pause_state.json")
    runtime = root / "logs" / "runtime.log"
    tail = []
    if _inside(root, runtime) and runtime.is_file():
        try:
            with runtime.open("rb") as handle:
                handle.seek(max(0, runtime.stat().st_size - MAX_TAIL_BYTES))
                tail = handle.read(MAX_TAIL_BYTES).decode("utf-8", errors="replace").splitlines()[-tail_lines:]
        except OSError:
            tail = ["Runtime log could not be read"]
    pending, pending_count, request_count = [], 0, 0
    for path in sorted(root.rglob("*.flow-request.json")):
        if not _inside(root, path):
            continue
        request_count += 1
        request = _read_json(root, path)
        if isinstance(request, dict) and request.get("status") == "downloaded":
            continue
        pending_count += 1
        if len(pending) >= MAX_PENDING_REQUESTS:
            continue
        media = Path(str(path).removesuffix(".flow-request.json"))
        row = {"request_file": path.relative_to(root).as_posix(), "request": request,
               "recovery_file": media.relative_to(root).as_posix() + ".recovery.json",
               "recovery": _read_json(root, Path(str(media) + ".recovery.json"))}
        if _inside(root, media):
            try:
                row["local_asset"] = {"exists": media.is_file(),
                                      "bytes": media.stat().st_size if media.is_file() else 0}
            except OSError:
                row["local_asset"] = {"exists": False, "bytes": 0}
        pending.append(row)
    report = {
        "schema_version": 1, "tool_version": get_version(),
        "collected_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "job": {"job_id": manifest["job_id"], "status": manifest.get("status"),
                "profile": manifest.get("profile"), "shot_count": len(shots),
                "accepted_shots": sum(shot.get("status") == "accepted" for shot in shots),
                "shots": [{key: shot.get(key) for key in ("shot_id", "status", "provider", "media_strategy")}
                          for shot in shots]},
        "environment": {"python": sys.version.split()[0], "system": platform.system(),
                        "kernel": platform.release()},
        "pause": pause, "progress": _read_json(root, root / "logs" / "progress.json"),
        "runtime_tail": tail, "flow_request_count": request_count,
        "pending_request_count": pending_count, "pending_requests": pending,
        "pending_requests_truncated": pending_count > len(pending),
        "new_generation_requests": 0,
        "note": "Read-only diagnostic snapshot, not a media recovery. Known secrets are redacted; review before sharing.",
    }
    return redact(report)


def write_support_report(job_dir, destination=None) -> Path:
    report = build_support_report(job_dir)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    path = Path(destination) if destination else Path(job_dir) / "logs" / f"support-report-{stamp}.json"
    if path.suffix.lower() != ".json":
        raise ValueError("Diagnostic output must have a .json extension")
    path.parent.mkdir(parents=True, exist_ok=True)
    # Never overwrite a manifest, request journal, existing media or prior report.
    with path.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return path
