"""MovieFlow Studio browser provider for cartoon/story video generation.

This adapter intentionally uses only the visible MovieFlow Studio UI. It does not
use private endpoints, automate credentials, bypass CAPTCHAs, or manipulate
billing/quotas. The first run may require the user to sign in manually in the
visible browser. A persistent browser profile is then reused.

MovieFlow's UI is newer and less stable than the Google Flow integration, so the
provider is selector-tolerant and saves a screenshot/DOM snapshot on failure.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from .base import VideoProvider, ProviderStatus, FlowState
from .flow_browser import (
    FlowBrowser,
    FlowBrowserProvider,
    FlowUIChanged,
    FlowBrowserClosedError,
    is_wsl,
)


class MovieFlowAuthNeeded(RuntimeError):
    pass


class MovieFlowUIChanged(RuntimeError):
    pass


class MovieFlowBrowserClosed(RuntimeError):
    pass


def default_movieflow_profile_dir() -> str:
    if is_wsl():
        return os.path.join(os.path.expanduser("~"), ".local", "share", "autovideoai", "movieflow-profile")
    return os.path.abspath(".movieflow-profile")


class MovieFlowBrowser(FlowBrowser):
    """Reuse AutoVideoAI's battle-tested Playwright lifecycle with MovieFlow-specific UI logic."""

    def __init__(self, profile_dir: str | None = None, headless: bool = False, state_cb=None):
        super().__init__(
            ui_cfg_path="config/movieflow_ui.yaml",
            profile_dir=profile_dir or default_movieflow_profile_dir(),
            headless=headless,
            state_cb=state_cb,
        )
        # MovieFlow can share the same debug Chrome as Flow, but dedicated
        # MOVIEFLOW_* environment variables override inherited FLOW_* settings.
        for env, key in (("MOVIEFLOW_BROWSER_MODE", "mode"),
                         ("MOVIEFLOW_BROWSER_CHANNEL", "channel"),
                         ("MOVIEFLOW_BROWSER_EXE", "executable"),
                         ("MOVIEFLOW_CDP_URL", "cdp_url")):
            if os.getenv(env):
                self.bcfg[key] = os.getenv(env)
        self.log_dir = "logs/movieflow"
        os.makedirs(self.log_dir, exist_ok=True)
        self._movieflow_project_url: str | None = None

    @staticmethod
    def normalize_project_url(url: str | None) -> str:
        u = str(url or "").strip()
        if not u:
            return ""
        if not re.match(r"^https?://([a-z0-9-]+\.)?movieflow\.ai/", u, re.I):
            return ""
        return u.split("#", 1)[0]

    def _post_connect(self, visible_login_seconds: int):
        self._set(FlowState.WAITING_FOR_UI)
        target = self.ui.get("movieflow_url") or "https://studio.movieflow.ai/"
        try:
            current = str(getattr(self._page, "url", "") or "")
        except Exception:
            current = ""
        if "movieflow.ai" not in current.lower():
            self._page.goto(target, timeout=90000, wait_until="domcontentloaded")

        deadline = time.time() + max(30, visible_login_seconds)
        while time.time() < deadline:
            url = (self._page.url or "").lower()
            body = ""
            try:
                body = (self._page.inner_text("body") or "")[:4000].lower()
            except Exception:
                pass
            loginish = any(x in url for x in ("/login", "/signin", "/sign-in", "auth"))
            loginish = loginish or ("log in" in body and "password" in body)
            if loginish:
                time.sleep(3)
                continue
            return True
        raise MovieFlowAuthNeeded(
            "MovieFlow login was not completed in the visible browser. Log in manually, then resume the job."
        )

    def is_logged_in(self) -> bool:
        try:
            url = (self._page.url or "").lower()
            if any(x in url for x in ("/login", "/signin", "/sign-in")):
                return False
            return "movieflow.ai" in url
        except Exception:
            return False

    def _composer_visible(self) -> bool:
        if not self._page:
            return False
        try:
            return self._try_resolve("prompt_box", timeout_ms=1200) is not None
        except Exception:
            return False

    def _projectish_url(self) -> str:
        try:
            u = str(self._page.url or "")
        except Exception:
            return ""
        if "movieflow.ai" not in u.lower():
            return ""
        # Preserve any workspace/project/creation route. Landing/home URLs are not
        # useful for resume, so only remember routes beyond the bare home page.
        path = re.sub(r"^https?://[^/]+", "", u).strip("/")
        if not path or path in {"home", "en", "studio"}:
            return ""
        return self.normalize_project_url(u)

    def current_project_url(self) -> str:
        return self._projectish_url() or self._movieflow_project_url or ""

    def ensure_project(self, project_name: str, project_url: str | None = None) -> str:
        wanted = self.normalize_project_url(project_url)
        if wanted:
            try:
                if self.normalize_project_url(self._page.url) != wanted:
                    self._page.goto(wanted, timeout=90000, wait_until="domcontentloaded")
                # MovieFlow may take a while to hydrate the Agent composer.
                deadline = time.time() + 45
                while time.time() < deadline:
                    if self._composer_visible():
                        self._movieflow_project_url = wanted
                        return wanted
                    time.sleep(1)
            except Exception:
                pass

        if self._composer_visible():
            got = self._projectish_url()
            if got:
                self._movieflow_project_url = got
            return got

        # On the public/studio landing page, try the visible start/new-project controls.
        for label in ("new_project",):
            btn = self._try_resolve(label, timeout_ms=2500)
            if btn is not None:
                try:
                    btn.click()
                    break
                except Exception:
                    pass

        # Some MovieFlow versions open the project/composer in a new tab.
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                pages = [p for p in self._ctx.pages if not p.is_closed()]
                for p in reversed(pages):
                    if "movieflow.ai" in (p.url or "").lower():
                        self._page = p
                        if self._composer_visible():
                            got = self._projectish_url()
                            if got:
                                self._movieflow_project_url = got
                            return got
            except Exception:
                pass
            time.sleep(1)
        raise MovieFlowUIChanged(
            "MovieFlow project composer was not found. Open MovieFlow Studio, create/open a project once, and retry."
        )

    def video_signatures(self) -> set[str]:
        sigs: set[str] = set()
        if not self._page:
            return sigs
        try:
            vids = self._page.locator("video")
            for i in range(min(vids.count(), 50)):
                v = vids.nth(i)
                src = v.get_attribute("src") or ""
                poster = v.get_attribute("poster") or ""
                sigs.add(f"video|{src}|{poster}|{i}")
        except Exception:
            pass
        # Cards that may not hydrate a <video> until hovered/opened.
        try:
            cards = self._page.locator("[data-testid*='video'], [class*='video'], [aria-label*='video' i]")
            for i in range(min(cards.count(), 80)):
                c = cards.nth(i)
                txt = ""
                try:
                    txt = (c.inner_text(timeout=200) or "")[:240]
                except Exception:
                    pass
                if txt:
                    sigs.add(f"card|{txt}|{i}")
        except Exception:
            pass
        return sigs

    def _fill_prompt(self, text: str):
        box = self._resolve("prompt_box", timeout_ms=15000)
        try:
            tag = (box.evaluate("el => el.tagName") or "").lower()
        except Exception:
            tag = ""
        if tag in ("textarea", "input"):
            box.fill(text)
        else:
            try:
                box.click()
                self._page.keyboard.press("Control+A")
                self._page.keyboard.type(text, delay=1)
            except Exception:
                box.fill(text)

    def submit_story(self, prompt: str):
        # Prefer Agent mode when a visible toggle exists; the guide/workflow is
        # story-first and Agent mode is better suited to multi-scene creation.
        agent = self._try_resolve("agent_mode", timeout_ms=1000)
        if agent is not None:
            try:
                agent.click()
                time.sleep(0.5)
            except Exception:
                pass
        self._fill_prompt(prompt)
        submit = self._try_resolve("submit", timeout_ms=3500)
        if submit is not None:
            submit.click()
            return
        # Common chat/agent fallback: Enter sends, Shift+Enter inserts newline.
        try:
            self._page.keyboard.press("Enter")
        except Exception as e:
            raise MovieFlowUIChanged(f"MovieFlow submit control was not found: {e}")

    def _new_video_candidate(self, before: set[str]) -> dict | None:
        if not self._page:
            return None
        candidates: list[dict] = []
        try:
            vids = self._page.locator("video")
            for i in range(vids.count()):
                v = vids.nth(i)
                try:
                    src = v.get_attribute("src") or ""
                    poster = v.get_attribute("poster") or ""
                    sig = f"video|{src}|{poster}|{i}"
                    # A video element with a duration > .5 sec is stronger than text badges.
                    dur = 0.0
                    try:
                        dur = float(v.evaluate("el => Number(el.duration || 0)"))
                    except Exception:
                        pass
                    if sig not in before or dur > 0.5:
                        candidates.append({"locator": v, "src": src, "signature": sig, "duration": dur, "index": i})
                except Exception:
                    continue
        except Exception:
            pass
        if not candidates:
            return None
        # Newest DOM item usually appears last; prefer actual finite-duration media.
        candidates.sort(key=lambda x: (x.get("duration", 0) > 0.5, x.get("index", 0)), reverse=True)
        return candidates[0]

    def wait_for_new_video(self, before: set[str], timeout_s: int = 1800) -> dict:
        deadline = time.time() + max(60, int(timeout_s))
        last_progress = ""
        while time.time() < deadline:
            try:
                if not self._page or self._page.is_closed():
                    raise MovieFlowBrowserClosed("MovieFlow page closed while generation was in progress")
                cand = self._new_video_candidate(before)
                if cand and (cand.get("duration", 0) > 0.5 or cand.get("src")):
                    # Let the final source/url settle before download.
                    time.sleep(3)
                    cand2 = self._new_video_candidate(before)
                    return cand2 or cand
                # Keep the loop patient while MovieFlow shows generation state.
                try:
                    txt = (self._page.inner_text("body") or "").lower()
                    for marker in ("generating", "rendering", "creating", "processing", "queued", "preparing"):
                        if marker in txt:
                            last_progress = marker
                            break
                except Exception:
                    pass
                time.sleep(2)
            except MovieFlowBrowserClosed:
                raise
            except Exception as e:
                if FlowBrowser._looks_like_browser_closed_error(e):
                    raise MovieFlowBrowserClosed(str(e))
                time.sleep(2)
        raise MovieFlowUIChanged(
            f"MovieFlow did not expose a completed video within {timeout_s}s"
            + (f" (last state: {last_progress})" if last_progress else "")
        )

    def _download_via_src(self, src: str, out_path: str) -> bool:
        if not src:
            return False
        try:
            os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        except Exception:
            pass
        if src.startswith("http://") or src.startswith("https://"):
            try:
                r = self._ctx.request.get(src, timeout=120000)
                if r.ok:
                    with open(out_path, "wb") as f:
                        f.write(r.body())
                    return True
            except Exception:
                pass
        # Blob/data URLs can be downloaded in-page without transferring a huge
        # base64 payload through Python.
        if src.startswith("blob:") or src.startswith("data:"):
            try:
                with self._page.expect_download(timeout=30000) as di:
                    self._page.evaluate(
                        """src => {const a=document.createElement('a');a.href=src;a.download='movieflow.mp4';document.body.appendChild(a);a.click();a.remove();}""",
                        src,
                    )
                d = di.value
                d.save_as(out_path)
                return True
            except Exception:
                pass
        return False

    def download_candidate(self, candidate: dict, out_path: str) -> str:
        loc = candidate.get("locator")
        src = candidate.get("src") or ""
        if self._download_via_src(src, out_path) and FlowBrowserProvider._is_valid_video_file(out_path):
            return out_path
        try:
            if os.path.exists(out_path):
                os.remove(out_path)
        except Exception:
            pass

        # Try a download button inside/near the video's card first.
        if loc is not None:
            try:
                card = loc.locator("xpath=ancestor::*[self::div or self::article][1]")
                btn = card.get_by_text(re.compile("download", re.I)).first
                if btn.is_visible(timeout=1000):
                    with self._page.expect_download(timeout=45000) as di:
                        btn.click()
                    di.value.save_as(out_path)
                    if FlowBrowserProvider._is_valid_video_file(out_path):
                        return out_path
            except Exception:
                pass
        # Last UI fallback: newest/global Download control.
        btn = self._try_resolve("download", timeout_ms=2500)
        if btn is not None:
            try:
                with self._page.expect_download(timeout=45000) as di:
                    btn.click()
                di.value.save_as(out_path)
                if FlowBrowserProvider._is_valid_video_file(out_path):
                    return out_path
            except Exception:
                pass
        raise MovieFlowUIChanged("MovieFlow completed a video but no downloadable time-based video could be captured")

    def recover_project(self, project_url: str, timeout_s: int = 90) -> bool:
        wanted = self.normalize_project_url(project_url)
        # Soft recovery: adopt any surviving MovieFlow tab.
        try:
            for p in reversed(self._ctx.pages):
                if p.is_closed():
                    continue
                if "movieflow.ai" in (p.url or "").lower():
                    self._page = p
                    if self._composer_visible() or self._new_video_candidate(set()):
                        return True
        except Exception:
            pass
        if wanted:
            try:
                p = self._ctx.new_page()
                p.goto(wanted, timeout=90000, wait_until="domcontentloaded")
                self._page = p
                deadline = time.time() + timeout_s
                while time.time() < deadline:
                    if self._composer_visible() or self._new_video_candidate(set()):
                        self._movieflow_project_url = wanted
                        return True
                    time.sleep(1)
            except Exception:
                pass
        return False

    def snapshot_failure(self, job_id: str, shot_id: str, err: Exception):
        stamp = time.strftime("%Y%m%d-%H%M%S")
        base = os.path.join(self.log_dir, f"{job_id}_{shot_id}_{stamp}")
        try:
            self._page.screenshot(path=base + ".png", full_page=True)
        except Exception:
            pass
        data = {"url": getattr(self._page, "url", "?"), "error": str(err)[:2000]}
        try:
            data["page_text"] = (self._page.inner_text("body") or "")[:6000]
        except Exception:
            pass
        try:
            with open(base + ".json", "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass
        return base + ".png"


class MovieFlowBrowserProvider(VideoProvider):
    name = "movieflow"

    def __init__(self):
        self.bridge: MovieFlowBrowser | None = None

    def status(self) -> ProviderStatus:
        try:
            import playwright  # noqa: F401
            return ProviderStatus(True, "MovieFlow Studio browser adapter available")
        except Exception as e:
            return ProviderStatus(False, f"Playwright unavailable: {e}")

    def _ensure(self) -> MovieFlowBrowser:
        if self.bridge is None:
            self.bridge = MovieFlowBrowser()
            self.bridge.ensure_session(visible_login_seconds=300)
        return self.bridge

    def current_project_url(self) -> str:
        try:
            return self.bridge.current_project_url() if self.bridge else ""
        except Exception:
            return ""

    def generate(self, shot, compiled: dict, refs: dict, out_path: str,
                 vertical: bool, dry_run: bool = False) -> dict:
        if dry_run:
            return {"path": None, "provider": "movieflow", "model": getattr(shot, "model", "movieflow_story"),
                    "credits": 0, "dry_run": True, "log": "DRY RUN: would submit story/scene to MovieFlow Studio"}
        b = self._ensure()
        project_url = MovieFlowBrowser.normalize_project_url(compiled.get("movieflow_project_url"))
        prompt = str(compiled.get("movieflow_story_prompt") or compiled.get("prompt") or "").strip()
        if not prompt:
            return {"path": None, "provider": "movieflow", "model": getattr(shot, "model", "movieflow_story"),
                    "credits": 0, "error": "MovieFlow prompt is empty"}
        try:
            project_url = b.ensure_project(compiled.get("project") or "AutoVideoAI", project_url=project_url) or project_url
            before = b.video_signatures()
            b.submit_story(prompt)
            wait_s = int(compiled.get("movieflow_wait_seconds", 1800) or 1800)
            recovery_s = int(compiled.get("movieflow_recovery_wait_seconds", 300) or 300)
            try:
                candidate = b.wait_for_new_video(before, timeout_s=wait_s)
            except MovieFlowBrowserClosed:
                # Critical rule: the request was already submitted. Never submit a
                # second generation just because the page closed. Reopen the exact
                # project and wait for the already-running MovieFlow job.
                if not b.recover_project(project_url, timeout_s=90):
                    raise
                candidate = b.wait_for_new_video(before, timeout_s=recovery_s)
            path = b.download_candidate(candidate, out_path)
            if not FlowBrowserProvider._is_valid_video_file(path):
                raise MovieFlowUIChanged("Downloaded MovieFlow asset is not a valid time-based video")
            return {"path": path, "provider": "movieflow", "model": getattr(shot, "model", "movieflow_story"),
                    "credits": 0, "project_url": b.current_project_url() or project_url,
                    "dry_run": False, "log": "movieflow studio video ok"}
        except (MovieFlowAuthNeeded, MovieFlowUIChanged, MovieFlowBrowserClosed, FlowUIChanged, FlowBrowserClosedError) as e:
            try:
                snap = b.snapshot_failure(compiled.get("project") or "AutoVideoAI", getattr(shot, "shot_id", "shot"), e)
            except Exception:
                snap = ""
            return {"path": None, "provider": "movieflow", "model": getattr(shot, "model", "movieflow_story"),
                    "credits": 0, "project_url": b.current_project_url() or project_url,
                    "error": f"{type(e).__name__}: {e}" + (f" [snapshot: {snap}]" if snap else "")}
        except Exception as e:
            return {"path": None, "provider": "movieflow", "model": getattr(shot, "model", "movieflow_story"),
                    "credits": 0, "project_url": b.current_project_url() or project_url,
                    "error": f"{type(e).__name__}: {str(e)[:500]}"}

    def generate_image(self, shot, compiled: dict, out_path: str,
                       vertical: bool, dry_run: bool = False) -> dict:
        raise NotImplementedError("MovieFlow browser adapter is currently video/story generation only")

    def close(self):
        if self.bridge:
            self.bridge.close()
            self.bridge = None
