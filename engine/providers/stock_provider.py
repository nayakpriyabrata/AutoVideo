"""Stock provider - local royalty-free library first, optional Pexels/Pixabay API fallback.

No stock API is required. Drop .mp4/.mov/.webm files into assets/stock_library and
name them with useful keywords (city_traffic_01.mp4, laptop_office.mp4, etc.).
"""
from __future__ import annotations
import os
import re
import shutil
import json
from pathlib import Path
from .base import VideoProvider, ProviderStatus


class StockProvider(VideoProvider):
    name = "stock"

    @staticmethod
    def library_dir() -> str:
        return os.getenv("STOCK_LIBRARY_DIR", "assets/stock_library")

    @classmethod
    def _library_files(cls) -> list[str]:
        root = cls.library_dir()
        if not os.path.isdir(root):
            return []
        exts = {".mp4", ".mov", ".webm", ".mkv"}
        out = []
        for base, _, files in os.walk(root):
            for fn in files:
                if os.path.splitext(fn)[1].lower() in exts:
                    out.append(os.path.join(base, fn))
        return sorted(out)

    def status(self) -> ProviderStatus:
        local = len(self._library_files())
        mode = os.getenv("AUTOVIDEO_STOCK_SOURCE", "auto").strip().lower() or "auto"
        has_api = bool(os.getenv("PEXELS_API_KEY", "").strip() or os.getenv("PIXABAY_API_KEY", "").strip())
        browser_ok = os.getenv("AUTOVIDEO_STOCK_BROWSER", "1").strip().lower() not in {"0", "false", "no"}
        if mode == "local":
            available = bool(local)
        elif mode == "api":
            available = bool(local or has_api)
        elif mode == "browser":
            available = bool(local or browser_ok)
        else:
            available = bool(local or has_api or browser_ok)
        bits = []
        if local:
            bits.append(f"local-library={local}")
        if has_api:
            bits.append("pexels/pixabay-api=yes")
        if browser_ok:
            bits.append("browser-fallback=yes")
        if not bits:
            bits.append("add clips to assets/stock_library or enable free Pexels/Pixabay API/browser fallback")
        return ProviderStatus(available, " | ".join(bits))

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return set(re.findall(r"[a-zA-Z]{3,}", (text or "").lower()))

    @classmethod
    def _pick_local(cls, query: str, excluded=None) -> str | None:
        files = [p for p in cls._library_files() if os.path.realpath(p) not in (excluded or set())]
        if not files:
            return None
        q = cls._tokens(query)
        scored = []
        for p in files:
            name = os.path.splitext(os.path.basename(p))[0].replace("_", " ").replace("-", " ")
            toks = cls._tokens(name)
            score = len(q & toks) * 10
            if query and query.lower() in name.lower():
                score += 20
            scored.append((score, p))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        # A small library is not permission to insert unrelated footage.
        return scored[0][1] if scored and scored[0][0] > 0 else None

    def generate(self, shot, compiled: dict, refs: dict, out_path: str,
                 vertical: bool, dry_run: bool = False) -> dict:
        if dry_run:
            return {"path": None, "provider": "stock", "model": "stock",
                    "seed": None, "credits": 0, "dry_run": True,
                    "log": f"DRY RUN: would fetch stock for {shot.shot_id}"}
        query = getattr(shot, "stock_query", "") or shot.narration or shot.visual_goal or shot.subject
        used_assets, used_local = {}, set()
        # Per-job sidecars survive resume; do not reset uniqueness per shot.
        for sidecar in Path(out_path).parent.parent.glob("*/*.source.json"):
            try:
                data = json.loads(sidecar.read_text(encoding="utf-8"))
                used_assets.setdefault(data.get("source", ""), []).append(data.get("asset_id"))
                if data.get("local_source"):
                    used_local.add(os.path.realpath(data["local_source"]))
            except (OSError, ValueError):
                continue
        local = self._pick_local(query, used_local)
        if local:
            os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
            shutil.copy(local, out_path)
            with open(out_path + ".source.json", "w", encoding="utf-8") as f:
                json.dump({"source": "local-stock", "local_source": os.path.realpath(local),
                           "query": query}, f)
            return {"path": out_path, "provider": "stock", "model": "local-stock",
                    "seed": None, "credits": 0, "dry_run": False,
                    "log": f"local-stock:{os.path.basename(local)}"}

        # Optional external stock APIs. These are unrelated to Gemini/Flow and are
        # never required for the storyboard-economy pipeline.
        from ..stock_video import get_stock_videos
        source_mode = os.getenv("AUTOVIDEO_STOCK_SOURCE", "auto")
        r = get_stock_videos([query], query, os.path.dirname(out_path), vertical,
                             source_mode=source_mode, excluded_assets=used_assets)
        if not r["clips"]:
            return {"path": None, "provider": "stock", "model": "stock",
                    "seed": None, "credits": 0, "dry_run": False,
                    "log": "no stock result", "error": "no semantically matching stock clip found"}
        shutil.copy(r["clips"][0], out_path)
        meta = (r.get("metadata") or [{}])[0]
        try:
            with open(out_path + ".source.json", "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
        except Exception:
            pass
        return {"path": out_path, "provider": "stock", "model": r["source"],
                "seed": None, "credits": 0, "dry_run": False, "log": f"stock:{r['source']}",
                "stock_metadata": meta}
