"""One version label for source checkouts, packaged builds, and diagnostics."""
from pathlib import Path


def get_version() -> str:
    try:
        return (Path(__file__).resolve().parents[1] / "VERSION").read_text(encoding="utf-8").strip() or "unknown"
    except OSError:
        return "unknown"
