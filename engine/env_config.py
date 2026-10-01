"""Deterministic environment discovery shared by CLI and dashboard.

Only key names and source paths are reported. Secret values are never logged.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values


API_KEYS = (
    "GEMINI_API_KEY", "GROQ_API_KEY", "ELEVENLABS_API_KEY",
    "OPENAI_API_KEY", "XAI_API_KEY", "FAL_KEY",
    "PEXELS_API_KEY", "PIXABAY_API_KEY",
)

ALIASES = {
    "GEMINI_API_KEY": (
        "GOOGLE_API_KEY", "GOOGLE_GEMINI_API_KEY", "GOOGLE_GENAI_API_KEY",
    ),
    "GROQ_API_KEY": ("GROQ_KEY",),
    "ELEVENLABS_API_KEY": ("ELEVENLABS_KEY", "ELEVEN_LABS_API_KEY"),
    "FAL_KEY": ("FAL_API_KEY",),
}


def _candidate_files(project_root: str | os.PathLike | None = None) -> list[Path]:
    root = Path(project_root or Path(__file__).resolve().parents[1]).resolve()
    cwd = Path.cwd().resolve()
    candidates = [
        root / ".env",
        root / ".env.local",
        cwd / ".env",
        cwd / ".env.local",
        root.parent / ".env",
        Path.home() / ".config" / "autovideoai" / ".env",
    ]
    try:
        candidates.extend(sorted(
            root.parent.glob("AutoVideoAI-v*/.env"),
            key=lambda q: q.stat().st_mtime if q.exists() else 0,
            reverse=True,
        ))
    except Exception:
        pass
    unique, seen = [], set()
    for path in candidates:
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path
        if str(resolved) not in seen:
            seen.add(str(resolved))
            unique.append(resolved)
    return unique


def load_environment(project_root: str | os.PathLike | None = None) -> dict:
    """Merge non-empty values from known environment files.

    Current non-empty process variables win. Empty exported shell variables do
    not block valid file values. A UTF-8 BOM on the first key is tolerated.
    """
    existing, loaded, malformed = [], [], []
    for path in _candidate_files(project_root):
        if not path.is_file():
            continue
        existing.append(str(path))
        try:
            values = dotenv_values(path, encoding="utf-8-sig")
        except Exception as exc:
            malformed.append(f"{path}: {type(exc).__name__}")
            continue
        used = []
        for raw_key, raw_value in values.items():
            key = str(raw_key or "").strip().lstrip("\ufeff")
            value = str(raw_value or "").strip()
            if not key or not value:
                continue
            if not os.getenv(key):
                os.environ[key] = value
                used.append(key)
        if used:
            loaded.append({"path": str(path), "keys": sorted(set(used))})

    aliases_used = []
    for canonical, aliases in ALIASES.items():
        if os.getenv(canonical):
            continue
        for alias in aliases:
            value = str(os.getenv(alias, "") or "").strip()
            if value:
                os.environ[canonical] = value
                aliases_used.append(f"{alias}->{canonical}")
                break

    root = Path(project_root or Path(__file__).resolve().parents[1]).resolve()
    return {
        "project_root": str(root),
        "files_found": existing,
        "loaded": loaded,
        "aliases_used": aliases_used,
        "parse_errors": malformed,
        "present": {key: bool(str(os.getenv(key, "") or "").strip()) for key in API_KEYS},
    }


def format_environment_report(report: dict) -> str:
    lines = ["AutoVideoAI environment diagnosis",
             f"Project root: {report.get('project_root')}"]
    found = report.get("files_found") or []
    if found:
        lines.append("Environment files found:")
        lines.extend(f"  - {path}" for path in found)
    else:
        lines.append("Environment files found: NONE")
    lines.append("Provider variables (values hidden):")
    for key, present in (report.get("present") or {}).items():
        lines.append(f"  {'OK     ' if present else 'MISSING'} {key}")
    if report.get("aliases_used"):
        lines.append("Normalized aliases: " + ", ".join(report["aliases_used"]))
    if report.get("parse_errors"):
        lines.append("Parse errors:")
        lines.extend(f"  - {item}" for item in report["parse_errors"])
    if not (report.get("present") or {}).get("GEMINI_API_KEY"):
        lines.append("Gemini fix: add GEMINI_API_KEY=your_key to the project .env "
                     "(GOOGLE_API_KEY is also accepted).")
    return "\n".join(lines)
