"""Gemini Web script-provider for AutoVideoAI v5.5.

This provider intentionally automates only the visible Gemini consumer UI with a
persistent browser profile.  The user completes Google sign-in manually once via
``python3 cli.py v3 gemini-open``.  No passwords, cookies, private endpoints,
CAPTCHA bypass, or quota bypass are implemented.

The script engine treats this like another writer backend: it submits one prompt,
waits until the response has stopped changing, and returns the visible response
text.  Publish-quality JSON validation remains in ``script_engine.py``.
"""
from __future__ import annotations

import atexit
import json
import os
import re
import time
from urllib.parse import urlparse
from pathlib import Path
from typing import Iterable

from .flow_browser import FlowBrowser, FlowState, FlowUIChanged, is_wsl
from ..runtime_log import runtime_print as print


class GeminiWebAuthNeeded(RuntimeError):
    pass


class GeminiWebUIChanged(RuntimeError):
    pass


def default_gemini_profile_dir() -> str:
    if is_wsl():
        return os.path.join(os.path.expanduser("~"), ".local", "share", "autovideoai", "gemini-profile")
    return os.path.abspath(".gemini-profile")


class GeminiWebBrowser(FlowBrowser):
    """Persistent headed Gemini browser using AutoVideoAI's proven launcher."""

    def __init__(self, profile_dir: str | None = None, headless: bool = False):
        super().__init__(
            ui_cfg_path="config/gemini_ui.yaml",
            profile_dir=profile_dir or default_gemini_profile_dir(),
            headless=headless,
            state_cb=None,
        )
        for env, key in (("GEMINI_WEB_BROWSER_MODE", "mode"),
                         ("GEMINI_WEB_BROWSER_CHANNEL", "channel"),
                         ("GEMINI_WEB_BROWSER_EXE", "executable"),
                         ("GEMINI_WEB_CDP_URL", "cdp_url")):
            if os.getenv(env):
                self.bcfg[key] = os.getenv(env)
        self.log_dir = "logs/gemini"
        os.makedirs(self.log_dir, exist_ok=True)

    def _post_connect(self, visible_login_seconds: int):
        self._set(FlowState.WAITING_FOR_UI)
        target = self.ui.get("gemini_url") or "https://gemini.google.com/app"
        try:
            current = str(getattr(self._page, "url", "") or "")
        except Exception:
            current = ""
        if "gemini.google.com" not in current.lower():
            self._page.goto(target, timeout=90000, wait_until="domcontentloaded")

        deadline = time.time() + max(30, visible_login_seconds)
        while time.time() < deadline:
            try:
                url = (self._page.url or "").lower()
            except Exception:
                url = ""
            if "accounts.google.com" in url or "/signin" in url:
                time.sleep(2)
                continue
            if "gemini.google.com" in url and self._prompt_box(timeout_ms=900):
                self._set(FlowState.READY)
                return True
            time.sleep(1)
        raise GeminiWebAuthNeeded(
            "Gemini web login/composer was not ready. Run `python3 cli.py v3 gemini-open`, "
            "finish Google sign-in manually, then retry."
        )

    def _prompt_box(self, timeout_ms: int = 1200):
        # Gemini can retain hidden editors before the live composer in DOM order.
        # The generic resolver checks .first only, so inspect visible matches here.
        try:
            matches = self._page.locator("textarea, [contenteditable='true']")
            for index in range(min(matches.count(), 30)):
                candidate = matches.nth(index)
                if candidate.is_visible(timeout=100) and candidate.is_editable(timeout=100):
                    return candidate
        except Exception:
            pass
        try:
            return self._resolve("prompt_box", timeout_ms=timeout_ms)
        except Exception:
            return None

    @staticmethod
    def _clean_text(text: str) -> str:
        text = str(text or "").replace("\u200b", "").strip()
        return re.sub(r"\n{3,}", "\n\n", text)

    def _response_candidates(self) -> list[str]:
        """Return visible model-response-like blocks, newest last.

        Gemini changes its DOM frequently.  Prefer known semantic/custom elements
        and only use broad class fallbacks if necessary.  The JSON parser in the
        script engine is the final authority, so accidental UI chrome is harmless.
        """
        sels: Iterable[str] = (
            "message-content",
            "model-response",
            "response-element",
            "code-block",
            "model-response pre",
            "model-response code",
            "[data-test-id*='model-response']",
            "[data-test-id*='response'] message-content",
            ".model-response-text",
            ".response-content",
            ".markdown-main-panel",
            "div[class*='model-response']",
            "div[class*='response-container']",
            "div.markdown",
        )
        found: list[str] = []
        seen = set()
        for sel in sels:
            try:
                loc = self._page.locator(sel)
                n = min(loc.count(), 80)
                for i in range(n):
                    el = loc.nth(i)
                    if not el.is_visible(timeout=100):
                        continue
                    txt = self._clean_text(el.inner_text(timeout=500))
                    if len(txt) < 20 or txt in seen:
                        continue
                    seen.add(txt)
                    found.append(txt)
            except Exception:
                continue
        return found

    @classmethod
    def _complete_json_response(cls, text: str) -> bool:
        """True only for a complete JSON-object-shaped Gemini answer.

        Gemini can show a small, stable "thinking" block for several seconds
        before the real answer is mounted.  Older builds treated any stable
        40-character response-like element as complete and returned it.  Every
        Gemini-web request made by this provider asks for one JSON object, so a
        balanced object is a safe and much stronger completion signal.
        """
        raw = cls._clean_text(text)
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start or len(raw[start:end + 1]) < 50:
            return False
        candidate = raw[start:end + 1]
        try:
            return isinstance(json.loads(candidate), dict)
        except Exception:
            # Gemini occasionally renders typographic/control characters that
            # the downstream repair diagnostic should report.  Still require a
            # balanced, key-like object before declaring streaming complete.
            depth = 0
            in_string = False
            escaped = False
            for ch in candidate:
                if escaped:
                    escaped = False
                    continue
                if ch == "\\" and in_string:
                    escaped = True
                elif ch == '"':
                    in_string = not in_string
                elif not in_string and ch == "{":
                    depth += 1
                elif not in_string and ch == "}":
                    depth -= 1
                    if depth < 0:
                        return False
            return depth == 0 and not in_string and bool(
                re.search(r'"(?:narration|beats|angle|hook|cta|candidates)"\s*:', candidate, re.I)
            )

    def _generation_in_progress(self) -> bool:
        for label in ("Stop response", "Stop generating", "Cancel response"):
            try:
                loc = self._page.get_by_role("button", name=re.compile(label, re.I))
                if loc.count() and loc.first.is_visible(timeout=100):
                    return True
            except Exception:
                continue
        return False

    def _body_text(self) -> str:
        try:
            return self._clean_text(self._page.inner_text("body", timeout=1500))
        except Exception:
            return ""

    def _fill_prompt(self, prompt: str):
        box = self._prompt_box(timeout_ms=10000)
        if box is None:
            raise GeminiWebUIChanged("Gemini prompt box was not found")
        try:
            box.click(timeout=3000)
        except Exception:
            pass
        # Playwright fill works for textarea and most contenteditables.  Fall
        # back to keyboard insertion for custom Angular editors.
        try:
            box.fill(prompt, timeout=5000)
        except Exception:
            try:
                box.press("Control+A")
            except Exception:
                pass
            try:
                self._page.keyboard.insert_text(prompt)
            except Exception as e:
                raise GeminiWebUIChanged(f"Could not enter Gemini prompt: {e}") from e

    def _submit(self):
        btn = self._try_resolve("send_button", timeout_ms=1800)
        if btn is not None:
            try:
                btn.click(timeout=3000)
                return
            except Exception:
                pass
        box = self._prompt_box(timeout_ms=1800)
        if box is None:
            raise GeminiWebUIChanged("Gemini send control was not found")
        try:
            box.press("Enter")
        except Exception as e:
            raise GeminiWebUIChanged(f"Could not submit Gemini prompt: {e}") from e

    def start_fresh_chat(self):
        """Navigate to the Gemini app root so each provider call is independent."""
        target = self.ui.get("gemini_url") or "https://gemini.google.com/app"
        try:
            self._page.goto(target, timeout=90000, wait_until="domcontentloaded")
        except Exception:
            # If the current page is still usable, let the composer check decide.
            pass
        deadline = time.time() + 20
        while time.time() < deadline:
            if self._prompt_box(timeout_ms=500):
                return
            time.sleep(0.5)
        raise GeminiWebUIChanged("Gemini composer did not become ready after opening a fresh chat")

    @staticmethod
    def _chat_id(url: str) -> str:
        parsed = urlparse(str(url or ""))
        if parsed.hostname != "gemini.google.com":
            return ""
        match = re.fullmatch(r"/app/([A-Za-z0-9_-]+)", parsed.path.rstrip("/"))
        return match.group(1) if match else ""

    def delete_current_chat(self) -> bool:
        """Delete only the freshly-created current chat, using visible UI.

        This is deliberately conservative. If an unambiguous menu/Delete/
        confirmation sequence is not visible, nothing is clicked.
        """
        expected = getattr(self, "_submitted_chat_id", "")
        if not expected or self._chat_id(self._page.url) != expected:
            return False
        try:
            self._page.keyboard.press("Escape")  # close any response menu
            links = self._page.locator(
                f'a[href="/app/{expected}"], a[href="https://gemini.google.com/app/{expected}"]')
            if links.count() == 0 or not links.first.is_visible():
                toggle = self._page.get_by_role("button", name=re.compile(r"^(?:Open menu|Expand menu|Main menu)$", re.I))
                if toggle.count() == 1:
                    toggle.click(timeout=2000)
            if links.count() != 1:
                return False
            link = links.first
            link.scroll_into_view_if_needed(timeout=2000)
            link.hover(timeout=2000)
            # Only climb inside this exact conversation row. Never fall back to
            # a global More button, which can belong to a response/another chat.
            row = link.locator("xpath=ancestor-or-self::*[self::conversation or "
                               "@role='listitem' or contains(@class,'conversation-container')][1]")
            if row.count() != 1:
                row = link.locator("xpath=..")
            if row.locator('a[href*="/app/"]').count() != 1:
                return False
            row.hover(timeout=2000)
            menu = row.get_by_role("button", name=re.compile(
                r"(?:more|options|menu)", re.I))
            if menu.count() != 1:
                return False
            if self._chat_id(self._page.url) != expected:
                return False
            menu.click(timeout=2000)
            popup = self._page.get_by_role("menu")
            popup.wait_for(state="visible", timeout=2000)
            delete = popup.get_by_role("menuitem", name=re.compile(r"^Delete$", re.I))
            if delete.count() != 1:
                return False
            delete.click(timeout=2000)
            dialog = self._page.get_by_role("dialog").filter(
                has_text=re.compile(r"Delete chat\?", re.I))
            dialog.wait_for(state="visible", timeout=2000)
            confirm = dialog.get_by_role("button", name=re.compile(r"^Delete$", re.I))
            if confirm.count() != 1 or self._chat_id(self._page.url) != expected:
                return False
            confirm.click(timeout=2000)
            dialog.wait_for(state="hidden", timeout=5000)
            links.wait_for(state="detached", timeout=5000)
            return self._chat_id(self._page.url) != expected
        except Exception:
            return False
        finally:
            try:
                self._page.keyboard.press("Escape")
            except Exception:
                pass

    def _save_captured_response(self, text: str):
        """Keep the answer locally before deleting any conversation."""
        folder = Path(getattr(self, "log_dir", "logs/gemini"))
        folder.mkdir(parents=True, exist_ok=True)
        name = f"response-{time.time_ns()}.txt"
        (folder / name).write_text(text, encoding="utf-8")

    def _cleanup_requested(self) -> bool:
        return (os.getenv("AUTOVIDEO_GEMINI_CHAT_CLEANUP", "keep").strip().lower()
                == "delete-after-read")

    def _cleanup_submitted_chat(self):
        """Best-effort cleanup which never hides the original provider result."""
        try:
            deleted = self.delete_current_chat()
            status = {"chat_id": getattr(self, "_submitted_chat_id", ""),
                      "deleted": deleted, "response_saved": True,
                      "reason": "verified removal" if deleted else "current-chat controls or removal could not be verified"}
            folder = Path(getattr(self, "log_dir", "logs/gemini"))
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "cleanup-latest.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
            print("[Gemini] Temporary chat cleanup: deleted." if deleted else
                  "[Gemini] Temporary chat cleanup: not deleted; an unambiguous "
                  "current-chat Delete control was not found.")
        except Exception as exc:
            print(f"[Gemini] Temporary chat cleanup failed safely: {type(exc).__name__}: "
                  f"{str(exc)[:160]}")

    def ask(self, prompt: str, timeout_seconds: int = 240) -> str:
        """Submit one prompt and return the final stable visible response text."""
        self.start_fresh_chat()
        if self._chat_id(self._page.url):
            raise GeminiWebUIChanged("Fresh chat navigation retained an existing conversation; refusing to submit or delete it")
        self._submitted_chat_id = ""
        before_candidates = self._response_candidates()
        submitted = False
        captured = False
        try:
            self._fill_prompt(prompt)
            self._submit()
            submitted = True
            if self._cleanup_requested():
                print("[Gemini] Temporary chat cleanup armed for this submitted chat.")

            deadline = time.time() + max(30, timeout_seconds)
            best = ""
            last = ""
            stable = 0
            first_complete_at = None
            heartbeat_at = time.time()
            while time.time() < deadline:
                if time.time() - heartbeat_at >= 15:
                    print(f"[Gemini] Waiting for complete JSON response; {max(0, int(deadline-time.time()))}s remaining.")
                    heartbeat_at = time.time()
                # Fail clearly if Google bounced us back to auth.
                try:
                    url = (self._page.url or "").lower()
                    current_id = self._chat_id(self._page.url)
                    if current_id and not self._submitted_chat_id:
                        self._submitted_chat_id = current_id
                    elif current_id and current_id != self._submitted_chat_id:
                        raise GeminiWebUIChanged("Conversation changed while awaiting response; cleanup cancelled")
                    if "accounts.google.com" in url:
                        raise GeminiWebAuthNeeded("Gemini web session requires Google sign-in again")
                except (GeminiWebAuthNeeded, GeminiWebUIChanged):
                    raise
                except Exception:
                    pass

                candidates = self._response_candidates()
                # Anything not present before submit is a likely new model answer.
                def is_user_echo(x: str) -> bool:
                    a = self._clean_text(x)
                    b = self._clean_text(prompt)
                    if not a:
                        return True
                    if a == b or a in b:
                        return True
                # Gemini may render the user message without our SYSTEM/USER
                # labels.  Reject candidates whose long prefix came directly
                # from the submitted prompt so streaming output is not confused
                # with our own request.
                    return len(a) > 80 and a[:80] in b

                new = [x for x in candidates
                       if x not in before_candidates and not is_user_echo(x)]
                pool = new or [x for x in candidates if not is_user_echo(x)]
                complete = [x for x in pool if self._complete_json_response(x)]
                if complete:
                    # A parent response container and its nested message/code
                    # block may both match. The longest complete object retains
                    # the full narration; newest position breaks equal lengths.
                    cur = max(enumerate(complete), key=lambda item: (len(item[1]), item[0]))[1]
                else:
                    cur = ""
                # Do not parse the whole body as a response: the user prompt
                # itself contains an example JSON schema and can be mistaken for
                # model output.  Known response elements are safer; on a DOM
                # redesign fail cheaply before TTS/Flow and save diagnostics.
                if len(cur) > len(best):
                    best = cur
                if cur and cur == last:
                    stable += 1
                else:
                    stable = 0
                    last = cur
                if cur and first_complete_at is None:
                    first_complete_at = time.time()

                # Wait for multiple unchanged polls. Give at least ~3 seconds
                # after complete JSON first appears so nested DOM blocks settle.
                if (best and stable >= 3 and first_complete_at
                        and time.time() - first_complete_at >= 3.0
                        and not self._generation_in_progress()):
                    self._save_captured_response(best)
                    captured = True
                    return best
                time.sleep(1.0)

            if best and not self._generation_in_progress():
                self._save_captured_response(best)
                captured = True
                return best
            raise GeminiWebUIChanged(
                f"Gemini web produced no complete JSON response within "
                f"{int(timeout_seconds)} seconds; short thinking/status blocks were ignored"
            )
        finally:
            # Keep failed/incomplete chats for diagnosis. Delete-after-read only
            # applies after a complete answer was durably captured locally.
            if submitted and captured and self._cleanup_requested():
                self._cleanup_submitted_chat()
            elif submitted and self._cleanup_requested():
                print("[Gemini] Cleanup skipped: no complete response saved; chat retained for diagnosis.")


_SESSION: GeminiWebBrowser | None = None


def get_shared_session() -> GeminiWebBrowser:
    global _SESSION
    if _SESSION is None or getattr(_SESSION, "_page", None) is None:
        _SESSION = GeminiWebBrowser()
        _SESSION.ensure_session(visible_login_seconds=int(os.getenv("GEMINI_WEB_LOGIN_WAIT", "300")))
    return _SESSION


def close_shared_session():
    global _SESSION
    if _SESSION is not None:
        try:
            _SESSION.close()
        except Exception:
            pass
    _SESSION = None


atexit.register(close_shared_session)


def gemini_web_generate(system: str, user: str, model: str = "auto") -> str:
    """Provider adapter used by ``engine.planning.script_engine``.

    The visible web UI does not expose a stable programmatic model identifier,
    so ``model`` is recorded only as provenance.  The user controls the model in
    Gemini's UI/account.  The prompt explicitly requests JSON-only output.
    """
    prompt = (
        "SYSTEM INSTRUCTIONS:\n" + system.strip() +
        "\n\nUSER TASK:\n" + user.strip() +
        "\n\nReturn ONLY the requested JSON object. Do not wrap it in commentary."
    )
    timeout = int(os.getenv("GEMINI_WEB_RESPONSE_TIMEOUT", "300"))
    return get_shared_session().ask(prompt, timeout_seconds=timeout)
