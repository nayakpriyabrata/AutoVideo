"""
Google Flow Browser Bridge (experimental provider).

- Playwright + persistent Chromium profile. First run: visible browser, USER logs
  into Google manually. Never automates passwords. Session reused afterwards.
- Operates normal visible UI only. No private APIs, no CAPTCHA/limit bypass,
  no credit manipulation, no SynthID removal.
- Config-driven selectors (config/flow_ui.yaml). Any UI drift -> Assisted Flow Mode.
- DRY RUN exercises orchestration without clicking Generate (no credits).
"""
from __future__ import annotations
import os
import re
import glob
import time
import json
import shutil
import subprocess
import hashlib
import yaml
from ..runtime_log import runtime_print as print
from .base import VideoProvider, ProviderStatus, FlowState


def media_signature_matches(left, right):
    """Compare the same media URL/kind, independent of tile size and label.

    Old journals include viewport dimensions. Never match on a generic prompt,
    DOM position or newest tile. Signed URL normalization requires a stable ID.
    """
    if left == right and left:
        return True
    from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
    def identity(sig):
        try:
            tag, src, tail = str(sig).split('|', 2)
            _, kind, width, height = tail.rsplit('|', 3)
            if tag not in ('IMG', 'VIDEO') or kind not in ('image', 'video') or not src:
                return None
            float(width); float(height)
            u = urlsplit(src)
            query = parse_qsl(u.query, keep_blank_values=True)
            # Only remove signing parameters when an independent content ID exists.
            stable_id = bool(re.search(r'[0-9a-f]{8}-[0-9a-f-]{27,}', u.path, re.I)) or any(
                k.lower() in ('id', 'assetid', 'mediaid', 'asset_id', 'media_id') and v for k, v in query)
            if stable_id:
                query = [(k,v) for k,v in query if not k.lower().startswith('x-goog-') and
                         k.lower() not in ('signature', 'expires', 'googleaccessid')]
                src = urlunsplit((u.scheme, u.netloc, u.path, urlencode(sorted(query)), u.fragment))
            return src, kind
        except (ValueError, TypeError):
            return None
    a, b = identity(left), identity(right)
    return a is not None and a == b


def find_system_chrome() -> str | None:
    """Locate an installed Chrome/Chromium (incl. Windows Chrome visible from WSL)."""
    cands = []
    for c in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
              "microsoft-edge", "microsoft-edge-stable"):
        try:
            p = shutil.which(c)
        except Exception:
            p = None
        if p:
            cands.append(p)
    cands += [
        "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
        "/mnt/c/Program Files (x86)/Google/Chrome/Application/chrome.exe",
        "C:/Program Files/Google/Chrome/Application/chrome.exe",
        "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium",
    ]
    for p in cands:
        try:
            if p and os.path.exists(p):
                return p
        except Exception:
            pass
    return None


def to_windows_path(p: str) -> str | None:
    """/mnt/c/Users/x -> C:\\Users\\x. None when not convertible (native Linux fs)."""
    import re
    m = re.match(r"^/mnt/([a-zA-Z])/(.*)$", os.path.abspath(p))
    if not m:
        return None
    return f"{m.group(1).upper()}:" + "\\" + m.group(2).replace("/", "\\")


def is_windows_exe(exe: str) -> bool:
    el = (exe or "").lower()
    return el.endswith(".exe") or el.startswith("/mnt/") or (len(el) > 2 and el[1] == ":")


def is_wsl() -> bool:
    try:
        with open("/proc/version", encoding="utf-8", errors="ignore") as f:
            return "microsoft" in f.read().lower()
    except Exception:
        return False


def default_profile_dir() -> str:
    """Browser profile home. Under WSL this MUST be on the Linux filesystem:
    Chromium lock files / SQLite break on /mnt/c (DrvFs) and the browser dies
    at launch with 'Target page, context or browser has been closed'."""
    if is_wsl():
        return os.path.join(os.path.expanduser("~"), ".local", "share",
                            "autovideoai", "flow-profile")
    return os.path.abspath(".flow-profile")


PROFILE_DIR = default_profile_dir()


def maybe_migrate_profile() -> str | None:
    """One-time: copy a session from legacy ./.flow-profile to the WSL home dir."""
    if not is_wsl():
        return None
    legacy = os.path.abspath(".flow-profile")
    if os.path.isdir(legacy) and os.listdir(legacy) and not os.path.exists(PROFILE_DIR):
        try:
            import shutil
            shutil.copytree(legacy, PROFILE_DIR)
            return PROFILE_DIR
        except Exception:
            return None
    return None


def has_native_linux_chrome() -> bool:
    return any(shutil.which(c) for c in ("google-chrome", "google-chrome-stable",
                                        "chromium", "chromium-browser"))


def short_browser_error(e: BaseException, limit: int = 700) -> str:
    """One-line summary PLUS the 'Browser logs' tail (the part that names the cause).

    Playwright buries the reason after a 'Browser logs:' marker - naive [:140]
    truncation throws the diagnosis away, so preserve that section explicitly.
    """
    txt = str(e)
    head = txt.split("Browser logs:")[0].strip().splitlines()
    head = head[0][:160] if head else txt[:160]
    logs = ""
    if "Browser logs:" in txt:
        logs = txt.split("Browser logs:", 1)[1].strip()
        logs = "\n".join(logs.splitlines()[:12])[: max(0, limit - len(head) - 12)]
    return head if not logs else f"{head} | logs: {logs}"


def missing_shared_libs(exe_path: str) -> list[str]:
    """Parse `ldd` for 'not found' entries. [] = deps ok (or ldd unavailable)."""
    try:
        r = subprocess.run(["ldd", exe_path], capture_output=True, text=True, timeout=30)
        out = (r.stdout or "") + (r.stderr or "")
        return sorted({ln.split("=>")[0].strip() for ln in out.splitlines()
                       if "not found" in ln})
    except Exception:
        return []


def probe_cdp(url: str, timeout: int = 5) -> dict:
    """Check a Chrome remote-debugging endpoint. Returns {ok, browser?, error?}."""
    import requests
    try:
        r = requests.get(url.rstrip("/") + "/json/version", timeout=timeout)
        if r.status_code == 200:
            j = r.json()
            return {"ok": True, "browser": j.get("Browser", "?"),
                    "ws": bool(j.get("webSocketDebuggerUrl"))}
        return {"ok": False, "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


def cdp_is_live(url: str, timeout: int = 5) -> bool:
    """Bool wrapper (a result dict is always truthy - never `if probe_cdp()`)."""
    try:
        return bool(probe_cdp(url, timeout=timeout).get("ok"))
    except Exception:
        return False


def doctor_report() -> str:
    """Human-readable diagnostics for Flow browser setup. No browser is launched."""
    import sys
    import platform as _plat
    lines = []
    lines.append(f"Python {sys.version.split()[0]} on {_plat.system()} {_plat.release()} | WSL={is_wsl()}")
    try:
        import playwright
        lines.append(f"playwright pip package: {getattr(playwright, '__version__', 'installed')}")
    except ImportError:
        lines.append("playwright pip package: MISSING (pip install playwright)")
    bundled = sorted(glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")))
    if bundled:
        miss = missing_shared_libs(bundled[0])
        if miss:
            lines.append(f"bundled chromium: {bundled[0]}")
            lines.append(f"bundled chromium MISSING LIBS ({len(miss)}): {', '.join(miss[:8])}")
            lines.append("  -> run: python3 -m playwright install --with-deps chromium")
        else:
            lines.append(f"bundled chromium: {bundled[0]} (deps ok)")
    else:
        lines.append("bundled chromium: NOT DOWNLOADED (python3 -m playwright install chromium)")
    if is_wsl():
        lines.append(f"WSLg display: DISPLAY={os.getenv('DISPLAY') or '-'} "
                     f"WAYLAND_DISPLAY={os.getenv('WAYLAND_DISPLAY') or '-'} "
                     f"{'(no GUI transport - run wsl --update + wsl --shutdown from PowerShell)' if not os.getenv('DISPLAY') and not os.getenv('WAYLAND_DISPLAY') else ''}".rstrip())
    sys_chrome = find_system_chrome()
    if sys_chrome and is_wsl() and is_windows_exe(sys_chrome):
        lines.append(f"Windows Chrome visible from WSL: {sys_chrome}")
        lines.append("launchable system chrome: none (Linux Playwright cannot drive a "
                     "Windows .exe - use CDP mode or bundled; see FLOW_SETUP.md)")
    else:
        lines.append(f"system chrome: {sys_chrome or 'not found'}")
    prof = PROFILE_DIR
    lines.append(f"profile dir: {prof}")
    try:
        ui = yaml.safe_load(open("config/flow_ui.yaml", encoding="utf-8"))
        bcfg = resolve_browser_cfg(ui)
    except Exception:
        bcfg = {}
    lines.append(f"browser mode: {(bcfg.get('mode') or 'auto')} | channel={bcfg.get('channel', 'chrome')} | "
                 f"exe={bcfg.get('executable') or '-'} | cdp={bcfg.get('cdp_url') or '-'}")
    cands = []
    if bcfg.get("cdp_url"):
        cands.append(bcfg["cdp_url"])
    for u in ("http://localhost:9222", "http://127.0.0.1:9222"):
        if u not in cands:
            cands.append(u)
    any_cdp = False
    for u in cands:
        r = probe_cdp(u, timeout=3)
        if r.get("ok"):
            any_cdp = True
        lines.append(f"CDP {u}: {'OK ' + r.get('browser', '') if r['ok'] else 'unreachable (' + r.get('error', '?') + ')'}")
    if is_wsl() and not any_cdp:
        lines.append("WSL hint: if Chrome IS running with --remote-debugging-port=9222 on "
                     "Windows but CDP is unreachable, it is WSL networking (NAT vs mirrored) - "
                     "see FLOW_SETUP.md, or use bundled: python3 -m playwright install chromium")
    return "\n".join(lines)


def browser_test_verdict(variants: list[dict]) -> str:
    """Sentence from a browser_self_test variant list. Pure -> unit-tested."""
    headed = [v for v in variants if v.get("headed")]
    headless_ok = any(v["ok"] for v in variants if not v.get("headed"))
    if any(v["ok"] for v in headed):
        first = next(v["name"] for v in headed if v["ok"])
        return (f"Headed launch WORKS ({first}). If the app still fails, compare the "
                f"REAL-profile variant: if only that one fails, delete {PROFILE_DIR} "
                f"(stale lock) and log in again.")
    details = " ".join(v.get("detail", "") for v in headed)
    if "without having a XServer running" in details:
        return ("No X server is answering (DISPLAY is set but WSLg's GUI layer is "
                "down). Fix: PowerShell (admin) -> wsl --update -> wsl --shutdown -> "
                "reopen WSL. Verify with: ls /mnt/wslg/ /tmp/.X11-unix/ (sockets must "
                "exist). Corporate VPN/firewall can also block WSLg - retry off-VPN. "
                "Alternative that needs no WSLg at all: CDP to Windows Chrome "
                "(FLOW_SETUP.md: mirrored networking + chrome-debug.bat).")
    if headless_ok:
        return ("Engine works HEADLESS but no headed variant launched: this is a "
                "display/GPU issue (WSLg). From PowerShell run wsl --update, "
                "wsl --shutdown, reopen WSL and retry. Screenshots: logs/flow/.")
    return ("Even headless failed: Playwright/Chromium install is broken. Run "
            "python3 -m playwright install --with-deps chromium (full output, "
            "allow sudo), then retry.")


def browser_self_test(log_dir: str = "logs/flow", url: str = "https://example.com") -> dict:
    """Launch bundled Chromium with progressive flag sets; report what works.

    Returns {"variants": [{name, ok, detail, screenshot?}], "verdict": str}.
    Uses throwaway profiles (except the real-profile probe) - never touches
    saved logins. Worst case takes a few minutes (each variant has timeouts).
    """
    import tempfile
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"variants": [], "verdict": "playwright pip package missing (pip install playwright)"}
    os.makedirs(log_dir, exist_ok=True)
    base = ["--disable-dev-shm-usage", "--no-first-run", "--no-default-browser-check"]
    # (name, headless, extra_args, real_profile, wayland_env)
    variants = [
        ("headed clean-profile, default flags", False, [], False, False),
        ("headed clean-profile + --disable-gpu", False, ["--disable-gpu"], False, False),
        ("headed clean-profile + --disable-gpu --no-sandbox", False,
         ["--disable-gpu", "--no-sandbox"], False, False),
        ("headed clean-profile, native Wayland (bypasses X)", False,
         ["--ozone-platform=wayland"], False, True),
        ("headed REAL profile, native Wayland", False,
         ["--ozone-platform=wayland"], True, True),
        ("headed REAL profile, default X11 flags", False, [], True, False),
        ("headless clean-profile (engine sanity)", True, [], False, False),
    ]
    out: list[dict] = []
    pw = sync_playwright().start()
    try:
        for i, (name, headless, extra, real_prof, wl) in enumerate(variants, 1):
            prof = PROFILE_DIR if real_prof else tempfile.mkdtemp(prefix="av-browsertest-")
            shot = os.path.join(log_dir, f"browser-test-{i}.png")
            rec: dict = {"name": name, "headed": not headless, "ok": False,
                         "detail": "", "screenshot": ""}
            ctx = None
            try:
                kw: dict = {}
                if wl:
                    env = dict(os.environ)
                    env.pop("DISPLAY", None)
                    env["WAYLAND_DISPLAY"] = os.environ.get("WAYLAND_DISPLAY", "wayland-0")
                    rtd = f"/run/user/{os.getuid()}"
                    env["XDG_RUNTIME_DIR"] = rtd if os.path.isdir(rtd) else env.get(
                        "XDG_RUNTIME_DIR", rtd)
                    kw["env"] = env
                ctx = pw.chromium.launch_persistent_context(
                    prof, headless=headless, args=base + extra, timeout=30000, **kw)
                pg = ctx.pages[0] if ctx.pages else ctx.new_page()
                pg.goto(url, timeout=20000)
                rec["ok"] = True
                rec["detail"] = f"title={pg.title()!r} url={pg.url}"
                try:
                    pg.screenshot(path=shot)
                    rec["screenshot"] = shot
                except Exception:
                    pass
            except Exception as e:
                rec["detail"] = short_browser_error(e, limit=400)
            finally:
                try:
                    if ctx:
                        ctx.close()
                except Exception:
                    pass
                if not real_prof:
                    try:
                        import shutil as _sh
                        _sh.rmtree(prof, ignore_errors=True)
                    except Exception:
                        pass
            out.append(rec)
    finally:
        try:
            pw.stop()
        except Exception:
            pass
    return {"variants": out, "verdict": browser_test_verdict(out)}


def resolve_browser_cfg(ui: dict) -> dict:
    """flow_ui.yaml browser: < user_settings.yaml < FLOW_* env vars."""
    cfg = dict((ui.get("browser") or {}))
    try:
        if os.path.exists("config/user_settings.yaml"):
            g = yaml.safe_load(open("config/user_settings.yaml", encoding="utf-8")) or {}
            for k, v in ((g.get("browser") or {}).items()):
                if v:
                    cfg[k] = v
    except Exception:
        pass
    for env, key in (("FLOW_BROWSER_MODE", "mode"), ("FLOW_BROWSER_CHANNEL", "channel"),
                     ("FLOW_BROWSER_EXE", "executable"), ("FLOW_CDP_URL", "cdp_url")):
        if os.getenv(env):
            cfg[key] = os.getenv(env)
    cfg.setdefault("mode", "auto")
    cfg.setdefault("channel", "chrome")
    return cfg


class FlowAuthNeeded(Exception):
    pass


class FlowUIChanged(Exception):
    """A selector failed -> caller should switch to Assisted Flow Mode."""
    pass


class FlowRequestPending(FlowUIChanged):
    """A request was submitted; download failure must not authorize generation."""
    pass


class FlowTransientNetworkError(Exception):
    """Temporary connectivity/browser transport failure. Safe to pause and retry."""
    pass


class FlowServiceBusy(Exception):
    """Flow Agent is temporarily at capacity/high demand. No prompt defect implied."""
    pass


class FlowBrowserClosedError(Exception):
    """The Playwright page/context/browser disappeared during a recoverable operation."""
    pass


def launch_fix_hint(errors: list[str]) -> str:
    """Contextual next-steps based on WHY the launch failed. Pure -> tested."""
    blob = " | ".join(errors)
    parts = ["FIX: run `python3 cli.py v3 doctor` + `python3 cli.py v3 browser-test` for diagnosis."]
    if "without having a XServer running" in blob:
        if is_wsl():
            parts.append("X11/Xwayland is unavailable. AutoVideoAI now tries native Wayland first; "
                         "if Wayland also failed, run `python3 cli.py v3 browser-test` and inspect "
                         "the native-Wayland result before changing WSL settings.")
        else:
            parts.append("No X server is available for a headed browser.")
    if is_wsl():
        parts.append("NO-WSLg ROUTE: on Windows run chrome-debug.bat, then from WSL test "
                     "`curl http://127.0.0.1:9222/json/version` (expect JSON). If JSON: app "
                     "SETTINGS -> Browser mode = cdp. If unreachable: mirrored networking "
                     "(.wslconfig networkingMode=mirrored + wsl --shutdown) or stay on bundled.")
    parts.append("Just want a video NOW with no browser? CREATE -> one-click FREE test "
                 "video (FREE_HYBRID).")
    return " ".join(parts)


class FlowQuotaExceeded(Exception):
    pass


class FlowBrowser:
    """Low-level Flow session. One instance per job (or shared, then close())."""

    def __init__(self, ui_cfg_path: str = "config/flow_ui.yaml",
                 profile_dir: str = PROFILE_DIR, headless: bool = False,
                 state_cb=None):
        try:
            maybe_migrate_profile()
        except Exception:
            pass
        self.ui = yaml.safe_load(open(ui_cfg_path, encoding="utf-8"))
        self.profile_dir = profile_dir
        self.headless = headless
        self.state_cb = state_cb
        self.state = FlowState.IDLE
        self._pw = self._ctx = self._page = self._cdp = None
        self._own_context = False
        self._guard_page = None  # stable project tab kept alive during fragile media-editor/download operations
        self._owns_page = False
        self._owns_guard_page = False
        self._isolated_worker = (
            os.path.basename(os.path.dirname(os.path.abspath(profile_dir or ""))) == ".flow-workers"
        )
        self.bcfg = resolve_browser_cfg(self.ui)
        self.active_browser = "?"
        self.log_dir = "logs/flow"
        os.makedirs(self.log_dir, exist_ok=True)
        self._project_ready: str | None = None  # logical AutoVideoAI project key
        self._project_url: str | None = None    # actual Flow /project/<uuid> URL
        self.last_generated_asset_signature: str | None = None
        self._generation_baseline_signatures: set[str] = set()
        # Snapshot of Agent failure-text counts immediately before the current
        # request is submitted. Flow keeps historical turns in the DOM; without
        # this, an old "generation failed"/"blocked" card can poison a later
        # image request and make wait_for_agent_generation() return False at once.
        self._agent_failure_baseline: dict[str, int] = {}

    # ---------- lifecycle ----------
    def _set(self, s: FlowState):
        self.state = s
        if self.state_cb:
            try:
                self.state_cb(s.value)
            except Exception:
                pass

    def _launch_options(self) -> list[dict]:
        mode = (self.bcfg.get("mode") or "auto").lower()
        self._launch_skipped: list[str] = []
        opts = []
        if mode in ("auto", "system"):
            if is_wsl() and not has_native_linux_chrome():
                self._launch_skipped.append(
                    "channel: skipped (no native Linux Chrome in WSL - use CDP or bundled)")
            else:
                opts.append({"kind": "channel", "channel": self.bcfg.get("channel", "chrome")})
            exe = self.bcfg.get("executable") or find_system_chrome()
            if exe:
                if is_wsl() and is_windows_exe(exe):
                    # Linux Playwright cannot drive a Windows .exe (cross-OS stdio):
                    # it always dies with "Target page, context or browser has been
                    # closed". Never attempt it - CDP or bundled instead.
                    self._launch_skipped.append(
                        f"exe: skipped {exe} (Windows Chrome is not launchable from WSL "
                        f"- use CDP mode with chrome-debug.bat, or bundled)")
                else:
                    opts.append({"kind": "exe", "executable": exe})
        if mode in ("auto", "bundled"):
            opts.append({"kind": "bundled"})
        return opts

    def _launch_persistent(self, opt: dict):
        """Launch a persistent context using the GUI transport that actually works.

        Important for WSLg: Chromium can have a healthy Wayland socket while the X11
        compatibility socket is unavailable.  browser_self_test already probes this,
        so the production launcher must mirror that behaviour instead of always
        assuming X11.  On WSL headed sessions we therefore try native Wayland first
        and only then fall back to the historical X11 flags.
        """
        kwargs: dict = {}
        profile = self.profile_dir
        if opt["kind"] == "channel":
            kwargs["channel"] = opt["channel"]
        elif opt["kind"] == "exe":
            exe = opt["executable"]
            kwargs["executable_path"] = exe
            if is_windows_exe(exe):
                # Windows Chrome cannot parse WSL/Linux paths -> translate.
                w = to_windows_path(profile)
                if not w:
                    raise RuntimeError(
                        f"Windows Chrome cannot use Linux profile path {profile}. "
                        f"Move the project under /mnt/<drive>/, or use CDP mode (FLOW_SETUP.md).")
                profile = w

        os.makedirs(self.profile_dir, exist_ok=True)
        common_args = ["--disable-blink-features=AutomationControlled",
                       "--disable-dev-shm-usage",
                       "--no-first-run", "--no-default-browser-check"]

        # (transport label, extra args, optional environment)
        strategies: list[tuple[str, list[str], dict | None]] = []
        if is_wsl() and not self.headless:
            # Native Wayland is the most reliable WSLg route and is exactly the
            # variant used by browser-test when it reports "native Wayland" PASS.
            env = dict(os.environ)
            env.pop("DISPLAY", None)  # prevent Chromium silently choosing X11
            env["WAYLAND_DISPLAY"] = os.environ.get("WAYLAND_DISPLAY", "wayland-0")
            rtd = f"/run/user/{os.getuid()}"
            env["XDG_RUNTIME_DIR"] = rtd if os.path.isdir(rtd) else env.get(
                "XDG_RUNTIME_DIR", rtd)
            strategies.append(("wayland", ["--ozone-platform=wayland"], env))
            # Keep X11 as a fallback for machines where WSLg exposes only Xwayland.
            strategies.append(("x11", ["--disable-gpu"], None))
        else:
            strategies.append(("headless" if self.headless else "native", [], None))

        launch_errors: list[str] = []
        for transport, extra_args, launch_env in strategies:
            try:
                launch_kwargs = dict(kwargs)
                if launch_env is not None:
                    launch_kwargs["env"] = launch_env
                self._ctx = self._pw.chromium.launch_persistent_context(
                    profile,
                    headless=self.headless,
                    accept_downloads=True,
                    args=common_args + extra_args,
                    **launch_kwargs,
                )
                self._own_context = True
                self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
                base = {"channel": f"system {opt.get('channel')}",
                        "exe": f"system ({opt.get('executable')})",
                        "bundled": "playwright chromium"}.get(opt["kind"], "?")
                self.active_browser = f"{base} [{transport}]"
                return
            except Exception as e:
                launch_errors.append(f"{transport}: {short_browser_error(e, limit=450)}")
                try:
                    if self._ctx:
                        self._ctx.close()
                except Exception:
                    pass
                self._ctx = self._page = None

        raise RuntimeError("; ".join(launch_errors) if launch_errors else "browser launch failed")

    def _connect_cdp(self, url: str):
        self._cdp = self._pw.chromium.connect_over_cdp(url, timeout=15000)
        ctxs = self._cdp.contexts
        if ctxs:
            self._ctx = ctxs[0]
            self._own_context = False  # never close the user's own tabs
        else:
            self._ctx = self._cdp.new_context(accept_downloads=True)
            self._own_context = True
        if getattr(self, "_isolated_worker", False):
            # CDP workers share Google's logged-in browser context but get their
            # own tab; never navigate the user's tab or another worker's tab.
            self._page = self._ctx.new_page()
            self._owns_page = True
            print("[Flow] Parallel image worker attached to CDP in a dedicated tab.")
        else:
            self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
            self._owns_page = not bool(ctxs and self._ctx.pages)
        self.active_browser = f"attached browser ({url})"

    def ensure_session(self, visible_login_seconds: int = 240):
        """Attach/launch a browser; user logs in manually on first run."""
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        # Workers isolate their Flow tabs/projects. In configured CDP mode keep
        # the already-authenticated Windows/WSL Chrome session; otherwise launch
        # a persistent worker profile as usual.
        mode = (self.bcfg.get("mode") or "auto").lower()
        if self._isolated_worker:
            print("[Flow] Isolated image worker: using a dedicated project and browser tab/profile.")
        errors: list[str] = []
        cdp_configured = (self.bcfg.get("cdp_url") or "").strip()
        if mode in ("auto", "cdp") and cdp_configured:
            try:
                self._connect_cdp(cdp_configured)
                return self._post_connect(visible_login_seconds)
            except Exception as e:
                errors.append(f"CDP {cdp_configured}: {short_browser_error(e)}")
                if mode == "cdp":
                    raise RuntimeError("CDP attach failed. Is Chrome running with "
                                       "--remote-debugging-port? See FLOW_SETUP.md. "
                                       f"({'; '.join(errors)})")
        if mode in ("auto", "cdp") and not cdp_configured:
            # Zero-config: is there a debug Chrome already listening?
            for u in ("http://127.0.0.1:9222", "http://localhost:9222"):
                try:
                    if probe_cdp(u, timeout=2).get("ok"):
                        self._connect_cdp(u)
                        return self._post_connect(visible_login_seconds)
                except Exception:
                    pass
        for opt in self._launch_options():
            try:
                self._launch_persistent(opt)
                return self._post_connect(visible_login_seconds)
            except Exception as e:
                errors.append(f"{opt['kind']}: {short_browser_error(e)}")
        errors += getattr(self, "_launch_skipped", [])
        raise RuntimeError(
            "Could not start any browser. " + (" | ".join(errors) if errors else "no launch options") +
            " " + launch_fix_hint(errors))

    def _post_connect(self, visible_login_seconds: int):
        self._set(FlowState.WAITING_FOR_UI)
        self._page.goto(self.ui.get("flow_url", "https://flow.google.com/"), timeout=60000)
        # If Google shows sign-in, wait for the USER to complete it manually.
        deadline = time.time() + visible_login_seconds
        while time.time() < deadline:
            url = (self._page.url or "").lower()
            if "accounts.google.com" in url and ("signin" in url or "challenge" in url):
                time.sleep(5)
                continue
            break
        else:
            raise FlowAuthNeeded("Google login not completed. Log in manually in the opened browser, then retry.")
        return True

    def is_logged_in(self) -> bool:
        try:
            if not self._page:
                return False
            url = (self._page.url or "").lower()
            return "accounts.google.com" not in url or "signin" not in url
        except Exception:
            return False

    def close(self):
        """Release our Playwright resources without killing a user-owned CDP browser.

        Older builds unconditionally closed ``self._ctx``.  When attached over CDP
        this can close the visible Chrome session that the user is interacting with.
        v4.9 closes only contexts launched/owned by AutoVideoAI; CDP-attached browser
        contexts are left alive and Playwright simply disconnects.
        """
        # Parallel workers may attach to a shared CDP context. Close only the
        # tabs they created, not the user's context or pre-existing browser tabs.
        for page, owned in ((getattr(self, "_page", None), getattr(self, "_owns_page", False)),
                            (getattr(self, "_guard_page", None), getattr(self, "_owns_guard_page", False))):
            if owned and page is not None:
                try:
                    if not page.is_closed():
                        page.close()
                except Exception:
                    pass
        try:
            if self._ctx and self._own_context:
                self._ctx.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._pw = self._ctx = self._page = self._cdp = None
        self._guard_page = None
        self._owns_page = self._owns_guard_page = False
        self._set(FlowState.IDLE)

    # ---------- locator helpers (config-driven) ----------
    def _candidates(self, action: str):
        cands = self.ui.get("actions", {}).get(action, [])
        return cands if isinstance(cands, list) else [cands]

    def _build_locator(self, c: dict):
        by = c.get("by")
        if by == "role":
            name_contains = c.get("name_contains")
            if name_contains:
                return self._page.get_by_role(
                    c["role"], name=re.compile(re.escape(name_contains), re.I)
                )
            return self._page.get_by_role(c["role"])
        if by == "text":
            return self._page.get_by_text(c["text"], exact=False)
        if by == "placeholder":
            return self._page.get_by_placeholder(c.get("text_contains", ""))
        if by == "css":
            return self._page.locator(c["selector"])
        return None

    def _resolve(self, action: str, timeout_ms: int = 8000, fmt: dict | None = None):
        """Resolve an action within ONE total timeout budget.

        Older builds accidentally waited the full timeout for every selector
        candidate. With five candidates and timeout_ms=12000 that could look
        frozen for about a minute before trying the selector that actually
        matched. This implementation polls all candidates rapidly until the
        shared deadline expires.
        """
        cands = self._candidates(action)
        deadline = time.time() + max(0.25, timeout_ms / 1000.0)
        errs = []
        while time.time() < deadline:
            for c in cands:
                try:
                    loc = self._build_locator(c)
                    if loc is None:
                        continue
                    first = loc.first
                    # Fast visibility probe; do not burn the whole action timeout
                    # on one stale role/text candidate.
                    if first.is_visible(timeout=250):
                        return first
                except Exception as e:
                    msg = str(e).replace("\n", " ")[:90]
                    if msg and msg not in errs:
                        errs.append(msg)
            self._page.wait_for_timeout(150)
        detail = '; '.join(errs[:3])[:220]
        raise FlowUIChanged(f"UI element not found: {action}" + (f" ({detail})" if detail else ""))

    def _try_resolve(self, action: str, timeout_ms: int = 1500):
        try:
            return self._resolve(action, timeout_ms=timeout_ms)
        except FlowUIChanged:
            return None

    def _click_text(self, text: str, timeout_ms: int = 8000):
        try:
            loc = self._page.get_by_text(text, exact=False).first
            loc.wait_for(timeout=timeout_ms)
            loc.click()
        except Exception as e:
            raise FlowUIChanged(f"Cannot click '{text}': {e}")

    def snapshot_failure(self, job_id: str, shot_id: str, err: Exception):
        """Screenshot + page dump so a selector miss is diagnosable (and user-shareable)."""
        stamp = time.strftime("%Y%m%d-%H%M%S")
        safe_job = "".join(c for c in str(job_id) if c.isalnum() or c in "-_")[:60]
        base = os.path.join(self.log_dir, f"{safe_job}_{shot_id}_{stamp}")
        try:
            self._page.screenshot(path=base + ".png")
        except Exception:
            pass
        dump: dict = {"url": getattr(self._page, "url", "?"), "job": job_id,
                      "shot": shot_id, "error": str(err)[:2000]}
        try:
            dump["page_text"] = (self._page.inner_text("body") or "")[:3000]
        except Exception:
            pass
        for role in ("tab", "button"):
            try:
                els = self._page.get_by_role(role).all()[:40]
                dump[role + "s"] = [(e.inner_text() or "").strip()[:60] for e in els]
            except Exception:
                pass
        try:
            dump["contenteditables"] = self._page.locator("[contenteditable='true']").count()
            dump["settings_trigger_count"] = self._page.locator(".settings-trigger-button").count()
            dump["overlay_count"] = self._page.locator(".cdk-overlay-pane").count()
        except Exception:
            pass
        try:
            with open(base + ".json", "w", encoding="utf-8") as f:
                json.dump(dump, f, indent=2)
        except Exception:
            pass
        return base + ".png"

    # ---------- resilient Flow UI helpers ----------
    @staticmethod
    def _looks_like_network_error(err) -> bool:
        txt = str(err or "").lower()
        tokens = (
            "err_internet_disconnected", "err_network_changed", "err_name_not_resolved",
            "err_connection", "networkerror", "network error", "internet disconnected",
            "no internet", "connection reset", "connection refused", "connection closed",
            "net::err_", "dns_probe", "temporarily unavailable",
        )
        return any(t in txt for t in tokens)

    @staticmethod
    def _looks_like_browser_closed_error(err) -> bool:
        txt = str(err or "").lower()
        tokens = (
            "target page, context or browser has been closed",
            "targetclosederror",
            "browser has been closed",
            "page has been closed",
            "context has been closed",
            "connection closed while reading from the driver",
        )
        return any(t in txt for t in tokens)

    def network_issue_detected(self, err=None) -> bool:
        """Best-effort detection of a temporary loss of Internet/Flow transport."""
        if self._looks_like_network_error(err):
            return True
        try:
            body = (self._page.inner_text("body") or "").lower()
            if any(t in body for t in (
                "err_internet_disconnected", "no internet", "you are offline",
                "this site can’t be reached", "this site can't be reached",
                "network changed", "dns_probe",
            )):
                return True
        except Exception:
            pass
        try:
            online = self._page.evaluate("() => navigator.onLine")
            if online is False:
                return True
        except Exception:
            pass
        return False

    def wait_for_network_recovery(self, timeout_s: int = 300) -> bool:
        """Pause instead of failing a production when the Internet drops briefly.

        Once connectivity comes back, reload the current Flow page and invalidate
        the cached project state so the next operation re-verifies the composer.
        """
        deadline = time.time() + max(5, int(timeout_s))
        announced = False
        while time.time() < deadline:
            if not announced:
                print(f"[Flow] Network interruption detected; waiting up to {int(timeout_s)}s for recovery...")
                announced = True
            online = True
            try:
                online = bool(self._page.evaluate("() => navigator.onLine"))
            except Exception:
                pass
            if online:
                try:
                    self._page.reload(wait_until="domcontentloaded", timeout=15000)
                    self._page.wait_for_timeout(900)
                    if not self.network_issue_detected():
                        self._project_ready = None
                        try:
                            self.return_to_project(timeout_ms=7000)
                        except Exception:
                            pass
                        print("[Flow] Network restored; browser session recovered.")
                        return True
                except Exception:
                    pass
            try:
                self._page.wait_for_timeout(5000)
            except Exception:
                time.sleep(5)
        print("[Flow] Network did not recover before timeout.")
        return False

    def _click_text_action(self, label: str, timeout_ms: int = 2500) -> bool:
        """Click a visible action even when Flow does not expose button semantics.

        The 2026 Flow Agent confirmation rows (Approve/Always approve/Reject) and
        some editor controls are sometimes rendered as clickable containers rather
        than accessibility-role=button elements. Exact visible text is therefore a
        required fallback.
        """
        deadline = time.time() + max(0.2, timeout_ms / 1000.0)
        pat = re.compile(rf"^\s*{re.escape(label)}\s*$", re.I)
        while time.time() < deadline:
            # Accessible button path first.
            try:
                loc = self._page.get_by_role("button", name=pat).first
                if loc.is_visible(timeout=120):
                    loc.click()
                    return True
            except Exception:
                pass
            # Flow Agent often uses a clickable div/list row with exact child text.
            try:
                loc = self._page.get_by_text(label, exact=True).first
                if loc.is_visible(timeout=120):
                    try:
                        loc.click()
                    except Exception:
                        try:
                            parent = loc.locator("xpath=ancestor-or-self::*[self::button or @role='button' or @tabindex][1]")
                            parent.click()
                        except Exception:
                            raise
                    return True
            except Exception:
                pass
            try:
                self._page.wait_for_timeout(150)
            except Exception:
                time.sleep(0.15)
        return False

    def _adopt_live_flow_page(self, project_url: str | None = None) -> bool:
        """Adopt another still-open Flow tab after the current editor tab closes.

        Flow's media editor can close/recreate its page target when leaving a detail
        view.  In CDP mode that should not be treated as the whole browser dying.
        Prefer the exact project URL, otherwise the newest open flow.google.com tab.
        """
        wanted = self.normalize_project_url(project_url)
        try:
            pages = list(getattr(self._ctx, "pages", []) or [])
        except Exception:
            pages = []
        fallback = None
        for pg in reversed(pages):
            try:
                if pg.is_closed():
                    continue
                url = str(pg.url or "")
                norm = self.normalize_project_url(url)
                if wanted and norm == wanted:
                    was_owned = ((pg is getattr(self, "_page", None) and getattr(self, "_owns_page", False))
                                 or (pg is getattr(self, "_guard_page", None)
                                     and getattr(self, "_owns_guard_page", False)))
                    self._page = pg
                    self._owns_page = was_owned
                    self._project_url = wanted
                    return True
                if "flow.google.com" in url and fallback is None:
                    fallback = pg
            except Exception:
                continue
        if getattr(self, "_isolated_worker", False) and self._ctx is not None and wanted:
            try:
                pg = self._ctx.new_page()
                self._page = pg
                self._owns_page = True
                pg.goto(wanted, wait_until="domcontentloaded", timeout=18000)
                pg.wait_for_timeout(500)
                self._project_url = wanted
                return True
            except Exception:
                return False
        if fallback is not None:
            self._page = fallback
            self._owns_page = False
            cur = self.normalize_project_url(getattr(fallback, "url", ""))
            if cur:
                self._project_url = cur
            return True
        return False

    def _ensure_project_guard_page(self, project_url: str | None = None) -> bool:
        """Keep one stable project tab alive while media editor/download tabs may close.

        Flow occasionally destroys the active detail/editor page after a generated
        asset is opened or downloaded.  If that was the only page, older recovery
        code escalated to a full browser restart.  The guard tab keeps the browser
        context alive so a page-target closure stays a cheap tab-level event.
        """
        wanted = self.normalize_project_url(project_url) or self.current_project_url()
        if not wanted or not self._ctx:
            return False
        try:
            gp = self._guard_page
            if gp is not None and not gp.is_closed() and self.normalize_project_url(getattr(gp, 'url', '')) == wanted:
                return True
        except Exception:
            self._guard_page = None
        try:
            gp = self._ctx.new_page()
            gp.goto(wanted, wait_until='domcontentloaded', timeout=18000)
            gp.wait_for_timeout(500)
            self._guard_page = gp
            self._owns_guard_page = True
            return True
        except Exception:
            self._guard_page = None
            return False

    def recover_project_page(self, project_url: str | None = None, timeout_ms: int = 12000) -> bool:
        """Recover from a closed Flow *page* without restarting the browser.

        This is the preferred v4.9 recovery path.  It first adopts any surviving
        project/guard tab; if none exists but the browser context is still alive,
        it opens a new project tab in that same context.  Only callers that cannot
        do this should escalate to a full browser relaunch.
        """
        wanted = self.normalize_project_url(project_url) or getattr(self, '_project_url', '') or ''
        if self._adopt_live_flow_page(wanted):
            try:
                if self._composer_visible(min(5000, timeout_ms)):
                    self._project_url = self.normalize_project_url(getattr(self._page, 'url', '')) or wanted
                    return True
            except Exception:
                pass
        if not wanted or not self._ctx:
            return False
        try:
            pg = self._ctx.new_page()
            pg.goto(wanted, wait_until='domcontentloaded', timeout=max(7000, timeout_ms))
            pg.wait_for_timeout(600)
            old = self._page
            old_owned = getattr(self, "_owns_page", False)
            self._page = pg
            self._owns_page = True
            self.dismiss_onboarding(rounds=1)
            if self._composer_visible(min(7000, timeout_ms)):
                self._project_url = wanted
                self._project_ready = None
                # Keep a separate guard if possible. Do not close the old page here;
                # it may be the last surviving target while Flow finishes cleanup.
                self._ensure_project_guard_page(wanted)
                return True
            self._page = old
            self._owns_page = old_owned
            try:
                pg.close()
            except Exception:
                pass
        except Exception:
            return False
        return False

    def return_to_project(self, timeout_ms: int = 10000) -> bool:
        """Leave Flow's media editor without touching its fragile Done control.

        In the Sep-2026 Flow UI an image detail/editor can replace or close the
        current page target when the app navigates back to the project.  Driving
        that same target with ``goto``/``Done`` therefore still produced
        TargetClosedError in v4.6.  v4.7 prefers a *fresh tab in the same browser
        context*, verifies the project composer there, then adopts that tab.
        """
        try:
            url = str(getattr(self._page, "url", "") or "")
        except Exception as e:
            if self._looks_like_browser_closed_error(e) and self._adopt_live_flow_page(getattr(self, "_project_url", "")):
                return self._composer_visible(5000)
            raise
        project_url = self.normalize_project_url(url) or getattr(self, "_project_url", "")
        if "/edit/" not in url:
            return False
        print("[Flow] Returning from image editor to project...")

        # First reuse an already-open project tab if Flow left one behind.
        current = self._page
        if project_url:
            try:
                pages = list(getattr(self._ctx, "pages", []) or [])
            except Exception:
                pages = []
            for pg in reversed(pages):
                if pg is current:
                    continue
                try:
                    if pg.is_closed():
                        continue
                    if self.normalize_project_url(getattr(pg, "url", "")) != project_url:
                        continue
                    self._page = pg
                    if self._composer_visible(min(5000, timeout_ms)):
                        self._project_ready = None
                        self._project_url = project_url
                        print("[Flow] Reused an already-open project tab.")
                        return True
                except Exception:
                    pass
                finally:
                    if self._page is pg and not self._composer_visible(200):
                        self._page = current

        # Preferred v4.7 path: open the canonical project route in a new target.
        # This avoids the editor target's self-destruction during SPA navigation.
        if project_url:
            fresh = None
            try:
                fresh = self._ctx.new_page()
                fresh.goto(project_url, wait_until="domcontentloaded",
                           timeout=min(18000, max(7000, timeout_ms)))
                fresh.wait_for_timeout(700)
                old = self._page
                self._page = fresh
                self.dismiss_onboarding(rounds=1)
                if self._composer_visible(min(7000, timeout_ms)):
                    self._project_ready = None
                    self._project_url = project_url
                    print("[Flow] Returned to project in a fresh tab.")
                    try:
                        if old is not fresh and not old.is_closed():
                            old.close()
                    except Exception:
                        pass
                    return True
                self._page = old
                try:
                    fresh.close()
                except Exception:
                    pass
            except Exception as e:
                if fresh is not None:
                    try:
                        if not fresh.is_closed():
                            fresh.close()
                    except Exception:
                        pass
                self._page = current
                if self._looks_like_browser_closed_error(e):
                    if self._adopt_live_flow_page(project_url):
                        try:
                            if self._composer_visible(5000):
                                self._project_ready = None
                                self._project_url = project_url
                                return True
                        except Exception:
                            pass
                    raise FlowBrowserClosedError(str(e))

        # Last-resort compatibility path. Prefer Back over Done because Done is the
        # control most often associated with Flow closing/replacing the editor page.
        clicked = False
        try:
            back = self._page.get_by_role("button", name=re.compile("Back", re.I)).first
            if back.is_visible(timeout=500):
                back.click()
                clicked = True
        except Exception:
            pass
        if not clicked:
            try:
                self._page.go_back(wait_until="domcontentloaded", timeout=8000)
            except Exception as e:
                if self._looks_like_browser_closed_error(e) and self._adopt_live_flow_page(project_url):
                    return self._composer_visible(5000)
                raise

        deadline = time.time() + max(1.0, timeout_ms / 1000.0)
        while time.time() < deadline:
            try:
                cur = str(getattr(self._page, "url", "") or "")
                if "/edit/" not in cur:
                    self._project_ready = None
                    self.current_project_url()
                    self._page.wait_for_timeout(350)
                    return True
                self._page.wait_for_timeout(200)
            except Exception as e:
                if self._looks_like_browser_closed_error(e) and self._adopt_live_flow_page(project_url):
                    if self._composer_visible(5000):
                        return True
                raise
        return False

    # ---------- project ops ----------
    def _composer_visible(self, timeout_ms: int = 1200) -> bool:
        # The public Flow landing page contains an Agent demo prompt, and Flow's
        # generated-media editor also contains prompt-like controls.  Neither is
        # the project composer.  A usable composer must be on the canonical
        # /project/<uuid> route, never /edit/<asset-id>.
        try:
            url = str(getattr(self._page, "url", "") or "")
            if "/project/" not in url or "/edit/" in url:
                return False
        except Exception:
            pass
        return self._try_resolve("prompt_box", timeout_ms=timeout_ms) is not None

    def enter_flow_app(self) -> bool:
        """Best-effort transition from a Flow marketing/landing page into the app."""
        loc = self._try_resolve("enter_flow", timeout_ms=1800)
        if not loc:
            return False
        try:
            loc.click()
            self._page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        return True

    @staticmethod
    def normalize_project_url(url: str | None) -> str:
        """Return a stable Flow project URL (without edit/query fragments)."""
        raw = str(url or "").strip()
        m = re.search(r"https://flow\.google\.com/project/([A-Za-z0-9-]+)", raw)
        return f"https://flow.google.com/project/{m.group(1)}" if m else ""

    def current_project_url(self) -> str:
        try:
            cur = self.normalize_project_url(getattr(self._page, "url", ""))
            if cur:
                self._project_url = cur
        except Exception:
            pass
        return getattr(self, "_project_url", None) or ""

    def create_project(self, name: str):
        print("[Flow] Clicking New project...")
        self._resolve("new_project", timeout_ms=12000).click()
        self._page.wait_for_timeout(1200)
        # Current Flow uses a date/time title and does not reliably expose a
        # rename field. `name` remains our logical job key; the actual project
        # identity is the /project/<uuid> URL captured below.
        try:
            box = self._resolve("project_name_input", timeout_ms=1800)
            box.fill(name)
            self._page.keyboard.press("Enter")
        except FlowUIChanged:
            pass

    def open_project(self, name: str):
        self._click_text(name, timeout_ms=5000)

    def dismiss_onboarding(self, rounds: int = 3) -> int:
        """Click through first-visit welcome/Labs dialogs. Returns clicks made."""
        texts = self.ui.get("actions", {}).get("onboarding_dismiss", []) or []
        clicked = 0
        for _ in range(rounds):
            round_clicks = 0
            for t in texts:
                try:
                    loc = self._page.get_by_text(t, exact=False).first
                    loc.wait_for(timeout=1200)
                    loc.click()
                    round_clicks += 1
                    time.sleep(0.8)
                except Exception:
                    pass
            clicked += round_clicks
            if round_clicks == 0:
                break
        return clicked

    def ensure_project(self, name: str, project_url: str | None = None):
        """Enter a usable Flow project and prefer an exact persisted project URL.

        Google Flow currently names projects with date/time labels, so the logical
        AutoVideoAI name cannot be used as a durable lookup key.  The /project/UUID
        URL is the canonical identity.  When supplied, it is opened directly; when
        a project is created or discovered, its URL is captured for persistence.
        """
        name = (name or "AutoVideoAI").strip() or "AutoVideoAI"
        wanted_url = self.normalize_project_url(project_url)

        # Never accept a media-detail /edit/ route as the project composer.  Sep-2026
        # Flow leaves prompt-like controls in that page, which previously fooled
        # _composer_visible() and sent the legacy standard path looking for a
        # nonexistent generate_button.  First leave the editor; if Flow refuses,
        # recover the canonical project page in the same browser context.
        try:
            raw_url = str(getattr(self._page, "url", "") or "")
        except Exception:
            raw_url = ""
        if "/edit/" in raw_url:
            canonical = self.normalize_project_url(raw_url) or wanted_url or getattr(self, "_project_url", "")
            left = False
            try:
                left = bool(self.return_to_project(timeout_ms=10000))
            except FlowBrowserClosedError:
                left = False
            except Exception:
                left = False
            try:
                still_edit = "/edit/" in str(getattr(self._page, "url", "") or "")
            except Exception:
                still_edit = True
            if (not left or still_edit) and canonical:
                if not self.recover_project_page(canonical, timeout_ms=12000):
                    raise FlowUIChanged(
                        f"Could not return from Flow media editor to project composer: {canonical}")
                self._project_ready = None
                self._project_url = canonical

        current_url = self.current_project_url()

        # Explicit/stored URL wins. This is what makes resume/browser recovery
        # deterministic and lets a new job intentionally reuse an older Flow project.
        if wanted_url and current_url != wanted_url:
            print(f"[Flow] Opening persisted project URL: {wanted_url}")
            try:
                self._page.goto(wanted_url, wait_until="domcontentloaded", timeout=20000)
                self._page.wait_for_timeout(900)
                self.dismiss_onboarding(rounds=1)
            except Exception as e:
                if self._looks_like_browser_closed_error(e):
                    raise FlowBrowserClosedError(str(e))
                raise FlowUIChanged(f"Could not open configured Flow project URL {wanted_url}: {e}")
            if not self._composer_visible(20000):
                raise FlowUIChanged(
                    f"Configured Flow project URL opened but composer was not found: {wanted_url}")
            self._project_ready = name
            self._project_url = wanted_url
            print("[Flow] Persisted Flow project is ready.")
            return

        if self._project_ready == name:
            if not hasattr(self, "_page"):
                return
            try:
                if "/edit/" in (getattr(self._page, "url", "") or ""):
                    self.return_to_project(timeout_ms=10000)
            except Exception:
                pass
            if self._composer_visible(1800):
                self.current_project_url()
                return
            self._project_ready = None

        print(f"[Flow] Current page: {getattr(getattr(self, '_page', None), 'url', '(test/mock)')}")
        print("[Flow] Looking for an open project/composer...")
        self.dismiss_onboarding()

        if self._composer_visible(1600):
            print("[Flow] Composer already open; reusing current project.")
            self._project_ready = name
            self.current_project_url()
            return

        if self.enter_flow_app():
            self.dismiss_onboarding(rounds=1)
            if self._composer_visible(6000):
                self._project_ready = name
                self.current_project_url()
                return

        # Legacy/older cohorts may still expose a user-defined project title.
        print(f"[Flow] Looking for existing project named {name!r}...")
        try:
            self.open_project(name)
            if self._composer_visible(12000):
                self._project_ready = name
                self.current_project_url()
                return
        except FlowUIChanged:
            pass

        print("[Flow] Existing named project not found; creating a fresh project.")
        self.create_project(name)
        print("[Flow] Waiting for the project composer...")
        if not self._composer_visible(20000):
            raise FlowUIChanged(
                f"Project opened/created but Flow prompt box was not found. url={self._page.url}")
        self._project_ready = name
        self.current_project_url()
        if getattr(self, "_project_url", None):
            print(f"[Flow] Project URL captured: {self._project_url}")
        print("[Flow] Project composer is ready.")

    def detect_editor_mode(self) -> str:
        """Return ``standard`` or ``agent`` for the canonical Flow project page.

        Media-detail pages under ``/edit/`` can expose controls that resemble both
        composer variants.  They are not generation composers, so normalize back
        to the project route before probing UI selectors.
        """
        try:
            url = str(getattr(self._page, "url", "") or "")
        except Exception:
            url = ""
        if "/edit/" in url:
            canonical = self.normalize_project_url(url) or getattr(self, "_project_url", "")
            try:
                if not self.return_to_project(timeout_ms=10000):
                    self.recover_project_page(canonical, timeout_ms=12000)
            except Exception:
                try:
                    self.recover_project_page(canonical, timeout_ms=12000)
                except Exception:
                    pass
            try:
                if "/edit/" in str(getattr(self._page, "url", "") or ""):
                    return "unknown"
            except Exception:
                return "unknown"

        if self._try_resolve("migrated_settings_trigger", timeout_ms=1200):
            return "standard"
        if self._try_resolve("agent_prompt_box", timeout_ms=1200):
            return "agent"
        return "unknown"

    @staticmethod
    def _agent_video_instruction(prompt: str, aspect: str = "9:16",
                                 model_label: str = "", duration: int = 8,
                                 count: int = 1) -> str:
        orientation = "portrait" if aspect == "9:16" else "landscape"
        model = model_label.strip() or "Veo 3.1 - Lite"
        return (
            f"Create exactly {max(1, int(count))} VIDEO clip{'s' if int(count) != 1 else ''}. "
            f"Do not create a still image. Use {orientation} orientation ({aspect}), "
            f"approximately {int(duration)} seconds, using {model}. Generate the media from "
            f"this scene description exactly as the creative brief: {prompt.strip()}"
        )[:4000]

    @staticmethod
    def _agent_image_instruction(prompt: str, aspect: str = "9:16", count: int = 1) -> str:
        orientation = "portrait" if aspect == "9:16" else "landscape"
        return (
            f"Create exactly {max(1, int(count))} STILL IMAGE{'S' if int(count) != 1 else ''}, not a video. "
            f"Use {orientation} orientation ({aspect}) and the no-charge Nano Banana 2 Lite image model when available. "
            f"Create this image exactly from the creative brief: {prompt.strip()}"
        )[:4000]

    def _finish_agent_media_picker(self, basename: str = "", timeout_ms: int = 12000) -> bool:
        """Finish Flow's current media-picker workflow by clicking Add to prompt.

        Sep-2026 Flow often uploads the file into the project library first and then
        leaves a modal open with an explicit ``Add to prompt`` button.  Returning
        immediately after ``set_input_files`` leaves that modal covering the Agent
        composer, which later causes a contenteditable click timeout.
        """
        started = time.time()
        deadline = started + max(1.0, timeout_ms / 1000.0)
        selected_once = False
        while time.time() < deadline:
            # If the uploaded asset is listed but not selected, select it by filename.
            if basename and not selected_once:
                try:
                    row = self._page.get_by_text(basename, exact=True).last
                    if row.is_visible(timeout=120):
                        row.click()
                        selected_once = True
                        self._page.wait_for_timeout(200)
                except Exception:
                    pass

            if self._click_text_action("Add to prompt", timeout_ms=300):
                self._page.wait_for_timeout(500)
                return True

            # Some cohorts attach directly and never show the project-library modal.
            try:
                if time.time() - started >= 1.5 and self._try_resolve("agent_prompt_box", timeout_ms=250):
                    body = (self._page.inner_text("body") or "")[-2500:].lower()
                    if "add to prompt" not in body:
                        return True
            except Exception:
                pass
            try:
                self._page.wait_for_timeout(250)
            except Exception:
                time.sleep(0.25)
        return False

    def _open_agent_add_menu(self):
        adds = self._page.locator("button:has(mat-icon:text-is('add'))")
        btn = None
        try:
            for i in range(adds.count() - 1, -1, -1):
                cand = adds.nth(i)
                if cand.is_visible(timeout=120):
                    btn = cand
                    break
        except Exception:
            btn = None
        if btn is None:
            btn = self._resolve("agent_add_media_button", timeout_ms=2500)
        btn.click()
        self._page.wait_for_timeout(250)

    @staticmethod
    def _media_upload_alias(path: str) -> str:
        """Stable Flow-library name derived from file content.

        Using only ``shot_001_open.jpg`` is unsafe across reused projects because a
        later job can have a different shot 001.  The short content hash makes the
        uploaded project-media name collision resistant and lets future runs reuse
        the exact same file already stored in the Flow project.
        """
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        base = re.sub(r"[^A-Za-z0-9._-]+", "_", os.path.basename(path))
        return f"AV_{h.hexdigest()[:12]}_{base}"

    def _try_attach_existing_project_media(self, display_name: str, timeout_ms: int = 3500) -> bool:
        """Best-effort attach of an already-uploaded Flow project asset by exact name.

        This never chooses a fuzzy/semantic match. If the media picker or exact
        fingerprinted filename is not available, the caller simply uploads the file.
        """
        try:
            self._open_agent_add_menu()
        except Exception:
            return False
        deadline = time.time() + max(0.8, timeout_ms / 1000.0)
        try:
            while time.time() < deadline:
                # Some Flow cohorts provide a Search assets box. Narrowing first
                # avoids selecting an old similarly named media item.
                try:
                    searches = self._page.locator("input[placeholder*='Search' i], input[aria-label*='Search' i]")
                    if searches.count():
                        q = searches.last
                        if q.is_visible(timeout=80):
                            q.fill(display_name)
                            self._page.wait_for_timeout(180)
                except Exception:
                    pass
                try:
                    row = self._page.get_by_text(display_name, exact=True).last
                    if row.is_visible(timeout=120):
                        row.click()
                        self._page.wait_for_timeout(180)
                        if self._click_text_action("Add to prompt", timeout_ms=1200):
                            self._page.wait_for_timeout(450)
                            print(f"[Flow] Reused existing project media: {display_name}")
                            return True
                except Exception:
                    pass
                self._page.wait_for_timeout(180)
        except Exception:
            pass
        # Close any picker/menu we opened; upload path will reopen what it needs.
        try:
            self._page.keyboard.press("Escape")
            self._page.wait_for_timeout(150)
        except Exception:
            pass
        return False

    def _aliased_upload_path(self, path: str, alias: str) -> str:
        """Create/reuse a local upload alias so Flow stores a deterministic name."""
        root = os.path.abspath(os.path.join("data", "flow_media_uploads"))
        os.makedirs(root, exist_ok=True)
        dst = os.path.join(root, alias)
        try:
            if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(path):
                shutil.copy2(path, dst)
            return dst
        except Exception:
            return path

    def attach_agent_media(self, paths: list[str], reuse_existing: bool = True) -> int:
        """Attach references to the live Flow Agent composer.

        v4.6 first looks for the exact content-fingerprinted asset already present
        in the Flow project. Only a byte-identical media alias can be reused; if it
        is absent, the file is uploaded once under that stable alias. This avoids
        repeatedly uploading/recreating the same first/last frames on a reused
        project while preventing generic ``shot_001.jpg`` collisions.
        """
        paths = [os.path.abspath(p) for p in (paths or []) if p and os.path.exists(p)]
        if not paths:
            return 0
        attached = 0
        errors = []
        for path in paths:
            basename = os.path.basename(path)
            try:
                alias = self._media_upload_alias(path)
                if reuse_existing and self._try_attach_existing_project_media(alias):
                    attached += 1
                    continue
                upload_path = self._aliased_upload_path(path, alias)
                upload_name = os.path.basename(upload_path)

                # A hidden input is the least brittle upload path when it exists.
                inputs = self._page.locator("input[type='file']")
                if inputs.count():
                    inputs.last.set_input_files(upload_path)
                    self._page.wait_for_timeout(500)
                    if not self._finish_agent_media_picker(upload_name):
                        raise FlowUIChanged(
                            f"Uploaded {upload_name} but Flow's 'Add to prompt' step did not complete")
                    attached += 1
                    print(f"[Flow] Added reference to prompt: {basename} ({alias[:15]}…)")
                    continue

                self._open_agent_add_menu()
                # The add menu may create a file input directly.
                inputs = self._page.locator("input[type='file']")
                if inputs.count():
                    inputs.last.set_input_files(upload_path)
                else:
                    # Or the Upload media row opens the native file chooser.
                    with self._page.expect_file_chooser(timeout=5000) as fc:
                        self._resolve("agent_upload_option", timeout_ms=4000).click()
                    fc.value.set_files(upload_path)
                self._page.wait_for_timeout(500)
                if not self._finish_agent_media_picker(upload_name):
                    raise FlowUIChanged(
                        f"Uploaded {upload_name} but Flow's 'Add to prompt' step did not complete")
                attached += 1
                print(f"[Flow] Added reference to prompt: {basename} ({alias[:15]}…)")
            except Exception as e:
                errors.append(f"{basename}: {e}")
                # Close a stuck picker before trying the next reference.
                try:
                    self._page.keyboard.press("Escape")
                except Exception:
                    pass
        if attached == 0:
            raise FlowUIChanged("Could not attach Agent reference media: " + "; ".join(errors)[-700:])
        if attached < len(paths):
            print(f"[Flow] WARNING: attached {attached}/{len(paths)} reference media; "
                  f"continuing with available references.")
        return attached

    def media_assets(self) -> list[dict]:
        """Return fingerprints for large visible image/video assets in DOM order.

        Flow often exposes a generated video as an ``img`` poster card rather
        than a literal ``<video>`` element.  v5.2 classifies the *card*, not just
        the poster image: play controls, resolution badges (360p/720p/1080p),
        video aria labels and descendant ``video`` elements all count as video
        evidence.  This prevents an intermediate still/poster from being treated
        as the completed movie.
        """
        try:
            return self._page.evaluate(r"""() => Array.from(document.querySelectorAll('img,video')).map((el, i) => {
                const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
                if (r.width < 140 || r.height < 90 || s.visibility === 'hidden' || s.display === 'none') return null;
                const src = el.currentSrc || el.src || el.poster || '';
                const alt = el.getAttribute('alt') || el.getAttribute('aria-label') || '';

                // Walk a few ancestors because Flow places the play icon and
                // resolution badge next to the poster image rather than inside it.
                let node = el, tile = el.parentElement, hints = '', depth = 0;
                let hasPlay = false, hasVideoNode = el.tagName.toLowerCase() === 'video';
                let hasResolution = false;
                while (node && depth < 6) {
                    try {
                        const aria = node.getAttribute && (node.getAttribute('aria-label') || '');
                        const title = node.getAttribute && (node.getAttribute('title') || '');
                        const txt = (node.innerText || '').trim();
                        const local = (aria + ' ' + title + ' ' + (txt.length < 900 ? txt : '')).trim();
                        hints += ' ' + local;
                        if (/\bplay\b|play video|video preview/i.test(local)) hasPlay = true;
                        if (/\b(?:360|480|720|1080|1440|2160)p\b/i.test(local)) hasResolution = true;
                        if (node.querySelector) {
                            if (node.querySelector('video')) hasVideoNode = true;
                            const labelled = Array.from(node.querySelectorAll('[aria-label],[title]')).slice(0, 18);
                            for (const n of labelled) {
                                const h = (n.getAttribute('aria-label') || '') + ' ' + (n.getAttribute('title') || '');
                                hints += ' ' + h;
                                if (/\bplay\b|play video|video preview/i.test(h)) hasPlay = true;
                            }
                        }
                    } catch (_) {}
                    if (node.matches && node.matches('[role="button"],[role="listitem"],button,[data-testid]')) tile = node;
                    node = node.parentElement; depth++;
                }
                const hint = (alt + ' ' + hints + ' ' + src).toLowerCase();
                let kind = 'image';
                if (hasVideoNode || hasPlay || hasResolution ||
                    /\bvideo\b|video preview|generated video|\.mp4(?:$|[?#])|\.webm(?:$|[?#])/.test(hint)) {
                    kind = 'video';
                }
                const sig = [el.tagName, src, alt, kind, Math.round(r.width), Math.round(r.height)].join('|');
                return {sig, src, alt, kind, tag: el.tagName.toLowerCase(), dom_index: i,
                        x: r.x, y: r.y, hint: hints.slice(0,600), hasPlay, hasResolution};
            }).filter(Boolean)""") or []
        except Exception as e:
            if self._looks_like_browser_closed_error(e):
                raise FlowBrowserClosedError(str(e))
            return []

    def media_asset_signatures(self) -> set[str]:
        return {str(x.get("sig")) for x in self.media_assets() if x.get("sig")}

    def media_asset_count(self) -> int:
        """Backward-compatible count used by older tests/callers."""
        return len(self.media_assets())

    def detect_service_busy(self) -> str | None:
        """Return the matching Flow Agent capacity message, if currently visible.

        Agent history remains in the DOM, so inspect the tail of the visible page text
        rather than the beginning. This reduces false positives from older messages.
        """
        try:
            body = (self._page.inner_text("body") or "")[-6000:].lower()
        except Exception as e:
            if self._looks_like_browser_closed_error(e):
                raise FlowBrowserClosedError(str(e))
            return None
        newest_busy = (-1, None)
        for t in self.ui.get("actions", {}).get("service_busy_texts", []):
            idx = body.rfind(str(t).lower())
            if idx > newest_busy[0]:
                newest_busy = (idx, str(t))
        if newest_busy[0] < 0:
            return None

        # A previous high-demand card can remain in the conversation history even
        # after Try again has successfully started a new request. If a newer
        # progress marker appears after the capacity message, treat the request as
        # running rather than repeatedly clicking an old Retry card.
        progress_markers = (
            "generation in progress", "creating video", "creating image",
            "generating", "pending",
        )
        newest_progress = max((body.rfind(x) for x in progress_markers), default=-1)
        if newest_progress > newest_busy[0]:
            return None
        return newest_busy[1]

    def recover_service_busy(self, max_wait_s: int | None = None,
                             max_retries: int | None = None) -> bool:
        """Retry a Flow Agent request that was rejected only because of high demand.

        Uses Flow's existing ``Try again``/``Retry`` control, so the original prompt
        is not resubmitted and a normal frame retry is not consumed. Backoff is
        bounded; persistent capacity pressure returns False so the job can pause.
        """
        timeouts = self.ui.get("timeouts", {})
        actions = self.ui.get("actions", {})
        max_wait_s = max(5, int(max_wait_s if max_wait_s is not None
                                else timeouts.get("service_busy_wait", 900)))
        max_retries = max(1, int(max_retries if max_retries is not None
                                 else timeouts.get("service_busy_retries", 8)))
        delays = actions.get("service_busy_retry_delays", [0, 30, 60, 90, 120, 180]) or [0]
        retry_labels = actions.get("service_retry_buttons", ["Try again", "Retry"]) or ["Try again"]
        deadline = time.time() + max_wait_s

        for attempt in range(max_retries):
            # A hard account/usage limit can share the words "try again later"
            # with temporary capacity cards. Stop immediately instead of spending
            # 10-15 minutes clicking Retry against a condition that cannot clear.
            self.detect_failure()
            if not self.detect_service_busy():
                return True
            delay = float(delays[min(attempt, len(delays) - 1)] or 0)
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            delay = min(delay, max(0.0, remaining))
            if delay > 0:
                retry_at = time.strftime("%H:%M:%S", time.localtime(time.time() + delay))
                print(f"[Flow] Agent is at capacity; waiting {int(delay)}s before retry "
                      f"({attempt + 1}/{max_retries}); next attempt at {retry_at}...")
                try:
                    self._page.wait_for_timeout(int(delay * 1000))
                except Exception as e:
                    if self._looks_like_browser_closed_error(e):
                        raise FlowBrowserClosedError(str(e))
                    time.sleep(delay)
            else:
                print(f"[Flow] Agent is at capacity; retrying now ({attempt + 1}/{max_retries})...")

            self.detect_failure()
            clicked = False
            for label in retry_labels:
                if self._click_text_action(str(label), timeout_ms=1800):
                    print(f"[Flow] Capacity recovery: clicked {label!r}.")
                    clicked = True
                    break
            if not clicked:
                print("[Flow] Capacity retry control is not visible yet; continuing to wait.")

            try:
                self._page.wait_for_timeout(1500)
            except Exception as e:
                if self._looks_like_browser_closed_error(e):
                    raise FlowBrowserClosedError(str(e))
            if not self.detect_service_busy():
                return True

        return not bool(self.detect_service_busy())

    def wait_for_agent_generation(self, before_assets=0, timeout_s: int | None = None,
                                  service_busy_wait_s: int | None = None,
                                  service_busy_retries: int | None = None,
                                  required_kind: str | None = None,
                                  video_ready_grace_s: int | None = None,
                                  approval: str = "once",
                                  max_generation_credits: int | None = None) -> bool:
        """Wait for the current Agent request to produce a genuinely new asset.

        v5.2 is deliberately conservative for video requests. Flow can show an
        intermediate poster/still several seconds before the playable/downloadable
        video is ready. We therefore keep polling for an explicit video card and
        require it to remain stable briefly. Only after a configurable grace period
        do we probe a still-untyped fresh card, and the provider then performs strict
        container/duration validation before accepting it.
        """
        timeout_s = timeout_s or self.ui["timeouts"]["generation"]
        deadline = time.time() + timeout_s
        if isinstance(before_assets, (set, list, tuple)):
            baseline = {str(x) for x in before_assets}
        else:
            baseline = None
            try:
                before_count = int(before_assets or 0)
            except Exception:
                before_count = 0
        self._generation_baseline_signatures = set(baseline or ())
        self.last_generated_asset_signature = None
        wanted = str(required_kind or "").strip().lower() or None
        saw_busy = False
        untyped_ready_at = None
        video_candidate_sig = None
        video_candidate_since = None
        announced_wait = False
        grace = max(5, int(video_ready_grace_s if video_ready_grace_s is not None else 20))
        last_approval_probe = 0.0
        approval_resolved = bool((getattr(self, "last_agent_confirmation", {}) or {}).get("clicked"))

        while time.time() < deadline:
            # Quota/usage-limit messages are more specific than the generic
            # "please try again later" capacity marker, so classify them first.
            fail = self.detect_failure()
            if fail:
                return False

            capacity = self.detect_service_busy()
            if capacity:
                ok = self.recover_service_busy(max_wait_s=service_busy_wait_s,
                                               max_retries=service_busy_retries)
                if not ok:
                    raise FlowServiceBusy(
                        f"Flow Agent remained at high demand after capacity recovery timeout "
                        f"(matched: {capacity!r}).")
                deadline = time.time() + timeout_s
                continue

            # On a brand-new Flow project the credit card can arrive well after
            # the prompt was submitted. Probe throughout the wait, not just once
            # during the first few seconds. "once" still never clicks the
            # persistent Always-approve control.
            now = time.time()
            confirmation_configured = bool(
                self.ui.get("actions", {}).get("agent_confirmation_buttons"))
            if (confirmation_configured and approval != "manual" and not approval_resolved
                    and now - last_approval_probe >= 2.0):
                last_approval_probe = now
                self.confirm_agent_generation(
                    timeout_s=1, approval=approval,
                    max_credits=max_generation_credits)
                confirm = getattr(self, "last_agent_confirmation", {}) or {}
                if confirm.get("blocked"):
                    return False
                approval_resolved = bool(confirm.get("clicked"))
            body = ""
            try:
                body = (self._page.inner_text("body") or "")[-7000:].lower()
            except Exception as e:
                if self._looks_like_browser_closed_error(e):
                    raise FlowBrowserClosedError(str(e))
            busy = any(x in body for x in (
                "pending", "generating", "creating video", "creating image",
                "generation in progress", "rendering video", "making your video"))
            saw_busy = saw_busy or busy

            if baseline is not None:
                assets = self.media_assets()
                new_assets = [a for a in assets if a.get("sig") and not any(
                    media_signature_matches(a["sig"], old) for old in baseline)]
                if new_assets:
                    matching = new_assets
                    if wanted:
                        matching = [a for a in new_assets if str(a.get("kind", "")).lower() == wanted]
                    if matching:
                        sig = str(matching[-1].get("sig"))
                        if wanted == "video":
                            # A real video card should stop changing before we click
                            # into it/download it. This is a small stability window,
                            # not an additional generation timeout.
                            if sig != video_candidate_sig:
                                video_candidate_sig = sig
                                video_candidate_since = time.time()
                                if not announced_wait:
                                    print("[Flow] Video tile detected; waiting briefly for Flow to finish the playable/download-ready asset...")
                                    announced_wait = True
                            elif not busy and video_candidate_since is not None and time.time() - video_candidate_since >= 3.0:
                                self.last_generated_asset_signature = sig
                                self._set(FlowState.GENERATION_COMPLETE)
                                return True
                        elif saw_busy or not busy:
                            self.last_generated_asset_signature = sig
                            self._set(FlowState.GENERATION_COMPLETE)
                            return True

                    # A poster can appear before Flow exposes the video card. Keep
                    # waiting instead of immediately downloading it as .mp4.
                    if wanted == "video" and not busy and not matching:
                        if untyped_ready_at is None:
                            untyped_ready_at = time.time()
                            if not announced_wait:
                                print(f"[Flow] Fresh media appeared; waiting up to {grace}s for the actual video tile/download to become ready...")
                                announced_wait = True
                        elif time.time() - untyped_ready_at >= grace:
                            self.last_generated_asset_signature = str(new_assets[-1].get("sig"))
                            print("[Flow] Video tile still untyped after readiness grace; probing the freshest asset with strict video validation.")
                            self._set(FlowState.GENERATION_COMPLETE)
                            return True
                    elif wanted != "video":
                        untyped_ready_at = None
                else:
                    untyped_ready_at = None
                    video_candidate_sig = None
                    video_candidate_since = None
            else:
                now_assets = self.media_asset_count()
                if now_assets > before_count and wanted != "video" and (saw_busy or not busy):
                    self._set(FlowState.GENERATION_COMPLETE)
                    return True
                if saw_busy and not busy and now_assets >= before_count and wanted != "video":
                    self._set(FlowState.GENERATION_COMPLETE)
                    return True

            try:
                self._page.wait_for_timeout(max(500, int(self.ui["timeouts"].get("poll_interval", 8) * 1000 / 2)))
            except Exception as e:
                if self._looks_like_browser_closed_error(e):
                    raise FlowBrowserClosedError(str(e))
                raise
        return False

    @staticmethod
    def _salvage_playwright_download(download, out_path: str) -> str | None:
        """Best-effort salvage when Playwright download.save_as() fails after page closure.

        Flow sometimes finishes the download, then destroys/replaces the page
        target before ``save_as`` completes.  In that case the ``Download``
        handle can still expose a temporary file via ``path()``.  v4.8 copies
        that file into ``out_path`` instead of discarding the generated media.
        """
        try:
            if download is None:
                return None
            tmp = None
            try:
                tmp = download.path()
            except Exception:
                tmp = None
            if not tmp or not os.path.exists(tmp):
                return None
            os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
            shutil.copyfile(tmp, out_path)
            return out_path if os.path.exists(out_path) else None
        except Exception:
            return None

    def _open_asset_tile_download_menu(self, media_locator) -> bool:
        """Open the kebab menu belonging to a project-grid media tile.

        Downloading from Flow's full-screen media viewer is fragile: the viewer
        destroys its own page target as the browser download starts.  The project
        grid exposes the same Download choices from the tile's three-dot menu and
        keeps the canonical project page alive, so prefer that route.
        """
        try:
            media_locator.hover(timeout=2500)
        except Exception:
            pass
        try:
            clicked = media_locator.evaluate(r"""el => {
                const visible = n => {
                    if (!n) return false;
                    const r = n.getBoundingClientRect(), s = getComputedStyle(n);
                    return r.width > 0 && r.height > 0 && s.display !== 'none' &&
                           s.visibility !== 'hidden';
                };
                let node = el;
                for (let depth = 0; node && depth < 8; depth++, node = node.parentElement) {
                    const controls = Array.from(node.querySelectorAll('button,[role="button"]'))
                        .filter(visible);
                    let more = controls.find(b => {
                        const hint = [b.getAttribute('aria-label') || '',
                                      b.getAttribute('title') || '',
                                      b.getAttribute('data-testid') || '',
                                      b.innerText || ''].join(' ').toLowerCase();
                        return /(?:more|menu|option|action|kebab|three.?dot|more_vert|more_horiz)/.test(hint);
                    });
                    // Flow's current tile has play + remix + kebab buttons; the
                    // kebab is the final control and sometimes has no accessible name.
                    if (!more && controls.length >= 2 && controls.length <= 8)
                        more = controls[controls.length - 1];
                    if (more) { more.click(); return true; }
                }
                return false;
            }""")
            if clicked:
                self._page.wait_for_timeout(350)
                return True
        except Exception:
            pass
        return False

    @staticmethod
    def _click_download_control(control, timeout=3000):
        """Only for already-resolved download controls, never generation buttons."""
        try:
            control.click(timeout=timeout)
        except Exception as exc:
            # Angular menu animations can prevent Playwright's stability check.
            # Do not bypass visibility/disabled checks or retry a detached page.
            if "not stable" not in str(exc).lower():
                raise
            if not control.is_visible() or not control.is_enabled():
                raise
            control.click(timeout=timeout, force=True)

    def _save_image_download_url(self, download, out_path):
        """Fetch the URL exposed by the browser's Download event, not a private API.

        Remote Windows CDP downloads may finish in Windows while save_as loses
        the target. A signed download URL needs no copied credentials/cookies.
        Never log that URL. Validate bytes before replacing the destination.
        """
        if not str(out_path).lower().endswith((".jpg", ".jpeg", ".png")):
            return None
        import io
        from urllib.parse import urlsplit
        import requests
        from PIL import Image
        temporary = out_path + ".download.tmp"
        try:
            url = download.url
            if urlsplit(url).scheme != "https":
                return None
            with requests.Session() as session:
                session.trust_env = False
                with session.get(url, stream=True, timeout=(10, 45)) as response:
                    response.raise_for_status()
                    data = bytearray()
                    for chunk in response.iter_content(65536):
                        data.extend(chunk)
                        if len(data) > 32 * 1024 * 1024:
                            raise ValueError("Image download exceeds 32 MB")
            with Image.open(io.BytesIO(data)) as image:
                if image.width < 140 or image.height < 90:
                    raise ValueError("Downloaded image is too small")
                image.verify()
            os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
            with open(temporary, "wb") as handle:
                handle.write(data)
            os.replace(temporary, out_path)
            print("[Flow] Recovered image from the browser download URL after save_as failed.")
            return out_path
        except Exception:
            return None
        finally:
            if os.path.isfile(temporary):
                os.remove(temporary)

    def _download_from_tile_button(self, button, out_path: str) -> str:
        """Listen BEFORE the first click: image menus can download immediately."""
        downloads = []
        page = self._page
        # Playwright caches its wrapper on the Python callback. Built-in
        # list.append cannot hold that attribute (including on WSL/Python 3.10).
        def on_download(download):
            downloads.append(download)

        page.on("download", on_download)
        label = "/".join(os.path.abspath(out_path).replace("\\", "/").split("/")[-3:])
        try:
            print(f"[Flow] Waiting for a download event: {label}")
            self._click_download_control(button)
            page.wait_for_timeout(500)
            if not downloads:
                option = self._try_resolve("download_original_option", timeout_ms=2000)
                if not downloads and option is not None:
                    self._click_download_control(option)
                elif not downloads:
                    # Scoped visible resolution items only, never another tile.
                    for label in ("1080p", "720p", "360p", "Original", "MP4", "1K", "Original size"):
                        options = page.get_by_text(label, exact=True)
                        if options.count() == 1 and options.first.is_visible(timeout=100):
                            self._click_download_control(options.first, timeout=2000)
                            break
            deadline = time.monotonic() + 30
            while not downloads and time.monotonic() < deadline:
                page.wait_for_timeout(250)
            if not downloads:
                raise FlowUIChanged("No download event within 30s of tile Download; request retained for recovery")
            print(f"[Flow] Download event received; saving {label}")
            try:
                downloads[0].save_as(out_path)
            except Exception:
                if not (self._salvage_playwright_download(downloads[0], out_path)
                        or self._save_image_download_url(downloads[0], out_path)):
                    raise
            if not os.path.isfile(out_path):
                raise FlowUIChanged("Download event completed without a local file")
            print(f"[Flow] Download saved: {label} ({os.path.getsize(out_path)} bytes)")
            return out_path
        except Exception as exc:
            from ..support_report import redact
            print(f"[Flow] Download failed: {label}: {type(exc).__name__}: {redact(str(exc))}")
            raise
        finally:
            try:
                page.remove_listener("download", on_download)
            except Exception:
                pass

    def _wait_for_media_signature(self, signature: str, timeout_ms: int = 15000):
        """Poll a loaded project gallery for one exact asset identity."""
        deadline = time.monotonic() + max(0, int(timeout_ms)) / 1000.0
        announced = False
        while True:
            for asset in self.media_assets():
                candidate = str(asset.get("sig", "") or "")
                if candidate and media_signature_matches(candidate, signature):
                    return asset
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            if not announced:
                print("[Flow] Waiting for the recorded media asset to appear in the recovered project gallery.")
                announced = True
            try:
                self._page.wait_for_timeout(min(500, max(50, int(remaining * 1000))))
            except Exception as exc:
                if self._looks_like_browser_closed_error(exc):
                    raise FlowBrowserClosedError(str(exc))
                raise

    def download_latest_asset(self, out_path: str, preferred_signature: str | None = None,
                              before_signatures: set[str] | None = None) -> str:
        """Download the newly generated Agent asset and automatically exit editor.

        ``preferred_signature`` comes from ``wait_for_agent_generation``.  If a
        baseline is supplied we refuse to silently download an older tile, fixing
        the repeated-single-image failure seen when Flow keeps historical media in
        the project grid.
        """
        baseline = set(before_signatures or ())
        candidates = []
        try:
            # Reuse media_assets() as the single fingerprint authority. Older
            # code rebuilt a shorter signature here (omitting `kind`), so a video
            # could be detected successfully and then become impossible to match
            # one line later during download.
            if preferred_signature:
                exact_asset = self._wait_for_media_signature(preferred_signature, timeout_ms=15000)
                assets = [exact_asset] if exact_asset else []
            else:
                assets = self.media_assets()
            els = self._page.locator("video, img")
            for asset in assets:
                i = int(asset.get("dom_index", -1))
                if i < 0 or i >= els.count():
                    continue
                el = els.nth(i)
                try:
                    if not el.is_visible(timeout=80):
                        continue
                    box = el.bounding_box()
                    if not box or box.get("width", 0) < 140 or box.get("height", 0) < 90:
                        continue
                    candidates.append((box.get("y", 0), box.get("x", 0),
                                       str(asset.get("sig", "")), el,
                                       str(asset.get("kind", "image")).lower()))
                except Exception as exc:
                    if self._looks_like_browser_closed_error(exc):
                        raise FlowBrowserClosedError(str(exc))
                    pass
        except FlowBrowserClosedError:
            raise
        except Exception:
            pass

        chosen = None
        if preferred_signature:
            for cand in candidates:
                if media_signature_matches(cand[2], preferred_signature):
                    chosen = cand
                    break
            if chosen is None:
                raise FlowUIChanged("The recorded asset is not visible; refusing to download a different tile")
        if chosen is None and baseline:
            fresh = [c for c in candidates if c[2] and c[2] not in baseline]
            if fresh:
                videos = [c for c in fresh if c[4] == "video"]
                if videos:
                    fresh = videos
                fresh.sort(key=lambda x: (x[0], x[1]))
                chosen = fresh[-1]
        if chosen is None and not baseline and candidates:
            candidates.sort(key=lambda x: (x[0], x[1]))
            chosen = candidates[-1]
        if chosen is None and baseline:
            raise FlowUIChanged(
                "Generation completed but no media distinct from the pre-generation assets was found; "
                "refusing to download an old Flow image")

        if chosen is not None and preferred_signature and chosen[2] == preferred_signature:
            print(f"[Flow] Matched the newly generated {chosen[4]} asset; preparing its tile download menu.")

        # Stay on the canonical project page.  This avoids the Flow media viewer
        # target-closing race that made Download.save_as fail repeatedly on WSL.
        direct_tile_menu = False
        if "/edit/" not in str(getattr(self._page, "url", "") or "") and chosen is not None:
            direct_tile_menu = self._open_asset_tile_download_menu(chosen[3])
            if direct_tile_menu:
                print("[Flow] Opened the project tile menu; downloading without entering the media viewer.")

        # Keep a sacrificial/stable project tab alive before opening a media editor.
        # Flow may close the active detail page after Download; the guard prevents
        # that tab-level close from becoming a visible full-browser restart.
        try:
            self._ensure_project_guard_page(getattr(self, "_project_url", "") or getattr(self._page, "url", ""))
        except Exception:
            pass

        if (not direct_tile_menu and
                "/edit/" not in str(getattr(self._page, "url", "") or "") and chosen is not None):
            try:
                chosen[3].click()
                self._page.wait_for_timeout(800)
            except Exception:
                pass

        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        saved = None
        last_err = None
        try:
            btn = self._resolve("download_button", timeout_ms=5000)
            if direct_tile_menu:
                return self._download_from_tile_button(btn, out_path)
            try:
                if not saved:
                    with self._page.expect_download(timeout=1800) as dl:
                        btn.click()
                    d = dl.value
                    try:
                        d.save_as(out_path)
                        saved = out_path
                    except Exception as e:
                        last_err = e
                        salvaged = self._salvage_playwright_download(d, out_path)
                        if salvaged:
                            print('[Flow] Salvaged completed browser download after page closure.')
                            saved = salvaged
                        elif self._looks_like_browser_closed_error(e):
                            raise FlowBrowserClosedError(
                                f"Generated asset was detected but the browser/page closed during download: {e}")
            except Exception as e:
                last_err = e
                if self._looks_like_browser_closed_error(e):
                    raise FlowBrowserClosedError(
                        f"Generated asset was detected but the browser/page closed during download: {e}")

            if not saved:
                try:
                    if not self._try_resolve("download_original_option", timeout_ms=1000):
                        btn.click()
                        self._page.wait_for_timeout(250)
                except Exception:
                    pass
                option = self._try_resolve("download_original_option", timeout_ms=3500)
                if option is None:
                    # Video menus use resolution/MP4 labels while image menus use
                    # 1K/Original size. Prefer the highest visible video option.
                    for label in ("1080p", "720p", "360p", "Download original",
                                  "Original", "MP4", "1K", "Original size"):
                        try:
                            cand = self._page.get_by_text(label, exact=True).first
                            if cand.is_visible(timeout=400):
                                option = cand
                                break
                        except Exception:
                            pass
                if option is None:
                    raise FlowUIChanged(
                        "Download menu opened but the 1K/Original size option was not found")
                with self._page.expect_download(timeout=self.ui["timeouts"]["download"] * 1000) as dl:
                    option.click()
                d = dl.value
                try:
                    d.save_as(out_path)
                    saved = out_path
                except Exception as e:
                    last_err = e
                    salvaged = self._salvage_playwright_download(d, out_path)
                    if salvaged:
                        print('[Flow] Salvaged completed browser download after page closure.')
                        saved = salvaged
                    elif self._looks_like_browser_closed_error(e):
                        raise FlowBrowserClosedError(
                            f"Generated asset was detected but the browser/page closed during download: {e}")

            if not saved or not os.path.exists(saved):
                raise FlowUIChanged(f"Flow download did not produce {out_path}: {last_err}")
            return saved
        except Exception as e:
            if self._looks_like_browser_closed_error(e):
                raise FlowBrowserClosedError(
                    f"Generated asset was detected but the browser/page closed during download: {e}")
            if self.network_issue_detected(e):
                raise FlowTransientNetworkError(f"Flow download interrupted by network: {e}")
            if isinstance(e, (FlowUIChanged, FlowBrowserClosedError)):
                raise
            raise FlowUIChanged(f"Generated asset found but automatic Download control was not found: {e}")
        finally:
            try:
                page_closed = False
                try:
                    if self._page is None:
                        page_closed = True
                    elif hasattr(self._page, "is_closed"):
                        page_closed = bool(self._page.is_closed())
                    else:
                        page_closed = False
                except Exception:
                    page_closed = True
                if page_closed and self._adopt_live_flow_page(getattr(self, "_project_url", "")):
                    print("[Flow] Media/editor tab closed; continued on the preserved project tab.")
                elif not page_closed and not self.return_to_project(timeout_ms=10000):
                    if "/edit/" in str(getattr(self._page, "url", "") or ""):
                        print("[Flow] WARNING: could not leave media editor automatically; next operation will retry recovery.")
            except Exception:
                try:
                    self._adopt_live_flow_page(getattr(self, "_project_url", ""))
                except Exception:
                    pass

    def _fill_editor_box(self, action: str, text: str, timeout_ms: int = 12000):
        # Expanded Agent sessions can contain more than one historical/editor
        # contenteditable. Prefer the last visible one, which is the live composer
        # at the bottom-right of the panel.
        box = None
        if action == "agent_prompt_box":
            try:
                eds = self._page.locator("[contenteditable='true']")
                for i in range(eds.count() - 1, -1, -1):
                    cand = eds.nth(i)
                    if cand.is_visible(timeout=120):
                        box = cand
                        break
            except Exception:
                box = None
        if box is None:
            box = self._resolve(action, timeout_ms=timeout_ms)
        box.click()
        try:
            box.fill(text[:4000])
        except Exception:
            # Current Flow's migrated composer is contenteditable.
            try:
                box.press("Control+A")
            except Exception:
                self._page.keyboard.press("Control+A")
            try:
                box.type(text[:4000], delay=1)
            except Exception:
                self._page.keyboard.type(text[:4000], delay=1)
        return box

    def configure_migrated_text_video(self, aspect: str = "9:16",
                                       model_label: str = "", duration: int = 8,
                                       count: int = 1):
        """Configure the Sep-2026 flow.google.com standard Angular editor.

        This intentionally uses the editor's structural controls rather than the
        removed ``Text to Video`` tab.  It is a normal UI path; no private API is
        called by AutoVideoAI.
        """
        trigger = self._resolve("migrated_settings_trigger", timeout_ms=5000)
        trigger.click()
        self._page.wait_for_timeout(350)

        # Video mode.
        video = self._try_resolve("migrated_video_radio", timeout_ms=3000)
        if video:
            try:
                if video.get_attribute("aria-checked") != "true":
                    video.click()
                    self._page.wait_for_timeout(300)
            except Exception:
                video.click()

        # Aspect ratio.
        akey = "migrated_aspect_portrait" if aspect == "9:16" else "migrated_aspect_landscape"
        ar = self._try_resolve(akey, timeout_ms=3000)
        if ar:
            try:
                if ar.get_attribute("aria-checked") != "true":
                    ar.click()
            except Exception:
                ar.click()

        # Model picker lives inside the settings overlay.  Keep the current model
        # when no label was requested.
        if model_label:
            mp = self._try_resolve("migrated_model_picker", timeout_ms=2500)
            if mp:
                mp.click()
                try:
                    opt = self._page.get_by_role(
                        "menuitem", name=re.compile(re.escape(model_label), re.I)
                    ).first
                    opt.wait_for(timeout=5000)
                    opt.click()
                except Exception as e:
                    # Close the model menu before surfacing a clean warning.
                    try:
                        self._page.keyboard.press("Escape")
                    except Exception:
                        pass
                    raise FlowUIChanged(f"Video model not found: {model_label}: {e}")

        # Duration / output count use exact numeric labels in the live editor.
        try:
            radios = self._page.locator(".cdk-overlay-pane [role='radio']")
            dur = radios.filter(has_text=re.compile(rf"^\s*{int(duration)}s\s*$", re.I)).first
            if dur.is_visible(timeout=800):
                dur.click()
        except Exception:
            pass
        try:
            radios = self._page.locator(".cdk-overlay-pane [role='radio']")
            cnt = radios.filter(has_text=re.compile(rf"^\s*x{max(1, int(count))}\s*$", re.I)).first
            if cnt.is_visible(timeout=800):
                cnt.click()
        except Exception:
            pass

        # Close settings and return to composer.
        try:
            self._page.keyboard.press("Escape")
        except Exception:
            pass
        self._page.wait_for_timeout(250)

    def prepare_text_video(self, aspect: str = "9:16", model_label: str = "",
                           duration: int = 8, count: int = 1) -> str:
        """Prepare text-to-video and return the active UI strategy.

        ``standard`` configures the migrated editor controls.  ``agent`` deliberately
        skips obsolete Text-to-Video tabs; the requested video settings are encoded
        into the Agent instruction instead.
        """
        mode = self.detect_editor_mode()
        if mode == "standard":
            self.configure_migrated_text_video(aspect, model_label, duration, count)
            return mode
        if mode == "agent":
            return mode

        # Older cohorts may still expose the pre-migration controls.
        self.select_video_mode("text")
        if model_label:
            self.select_model(model_label)
        try:
            self.set_aspect_ratio(aspect)
        except FlowUIChanged:
            pass
        self.set_duration(duration)
        self.set_output_count(count)
        return "legacy"

    def fill_text_video_prompt(self, prompt: str, strategy: str, aspect: str = "9:16",
                               model_label: str = "", duration: int = 8, count: int = 1):
        if strategy == "agent":
            text = self._agent_video_instruction(prompt, aspect, model_label, duration, count)
            return self._fill_editor_box("agent_prompt_box", text)
        return self._fill_editor_box("prompt_box", prompt)

    def submit_prepared_text_video(self, strategy: str):
        self._set(FlowState.SUBMITTING)
        # v4.8.2: remember which failure strings already existed before this
        # request. Agent history is persistent, so only a newly-added failure is
        # relevant to the request we are about to submit.
        try:
            body_before = (self._page.inner_text("body") or "").lower()
            self._agent_failure_baseline = {
                str(t).lower(): body_before.count(str(t).lower())
                for t in self.ui.get("actions", {}).get("failure_texts", [])
                if str(t).strip()
            }
        except Exception:
            self._agent_failure_baseline = {}
        if strategy == "standard":
            self._resolve("migrated_submit_button", timeout_ms=10000).click()
        elif strategy == "agent":
            btn = self._try_resolve("agent_send_button", timeout_ms=2500)
            if btn:
                btn.click()
            else:
                # Flow Agent accepts Enter as Send when the prompt has focus.
                self._page.keyboard.press("Enter")
        else:
            self._resolve("generate_button", timeout_ms=10000).click()
        self._set(FlowState.GENERATING)

    def confirm_agent_generation(self, timeout_s: int = 12, approval: str = "once",
                                 max_credits: int | None = None) -> bool:
        """Approve only a *currently clickable* Flow credit card.

        Flow keeps old Agent turns and old action text in the DOM.  v4.6 could
        therefore see a historical/non-clickable ``Approve``/generic action and
        eventually report ``credit confirmation blocked`` even though the newest
        turn already said ``I'm going to generate...``.  v4.7 never treats plain
        text as an approval control: the exact approval label must resolve to an
        enabled clickable element (button/role=button/clickable ancestor).
        """
        self.last_agent_confirmation = {"approval": approval, "cost": None,
                                        "clicked": None, "blocked": False}
        if approval == "manual":
            self.last_agent_confirmation["blocked"] = True
            self.last_agent_confirmation["reason"] = "manual approval requested"
            return False

        # Deliberately ignore generic Generate/Create/Continue/Yes controls. They
        # occur elsewhere in Flow and are not reliable credit-approval signals.
        configured = self.ui.get("actions", {}).get("agent_confirmation_buttons", []) or []
        approve_labels = [x for x in configured if "approve" in str(x).lower()]
        if approval == "always":
            labels = ["Always approve", "Approve", "Approve once"]
        else:
            labels = ["Approve", "Approve once"]
        for x in approve_labels:
            if x not in labels and not (approval != "always" and str(x).lower() == "always approve"):
                labels.append(x)

        def clickable_action(label: str):
            pat = re.compile(rf"^\s*{re.escape(label)}\s*$", re.I)
            # Best case: a real accessible button.
            try:
                locs = self._page.get_by_role("button", name=pat)
                if hasattr(locs, "count") and hasattr(locs, "nth"):
                    candidates = [locs.nth(i) for i in range(locs.count() - 1, -1, -1)]
                else:
                    candidates = [getattr(locs, "first", locs)]
                for loc in candidates:
                    if loc.is_visible(timeout=100):
                        try:
                            if loc.is_enabled(timeout=100):
                                return loc
                        except Exception:
                            return loc
            except Exception:
                pass

            # Some Flow cohorts render the text inside a clickable div.  Require a
            # clickable ancestor; never return the raw historical text node.
            try:
                texts = self._page.get_by_text(label, exact=True)
                if hasattr(texts, "count") and hasattr(texts, "nth"):
                    text_candidates = [texts.nth(i) for i in range(texts.count() - 1, -1, -1)]
                else:
                    text_candidates = [getattr(texts, "first", texts)]
                for txt in text_candidates:
                    if not txt.is_visible(timeout=80):
                        continue
                    try:
                        anc = txt.locator(
                            "xpath=ancestor-or-self::*[self::button or @role='button' or @tabindex or @href][1]"
                        )
                        if (not hasattr(anc, "count") or anc.count()) and anc.is_visible(timeout=80):
                            disabled = (anc.get_attribute("disabled") is not None or
                                        str(anc.get_attribute("aria-disabled") or "").lower() == "true")
                            if not disabled:
                                return anc
                    except Exception:
                        continue
            except Exception:
                pass
            return None

        deadline = time.time() + max(1, int(timeout_s))
        saw_clickable = False
        while time.time() < deadline:
            try:
                if self.network_issue_detected():
                    raise FlowTransientNetworkError(
                        "network unavailable while waiting for Flow credit approval")
                body_raw = self._page.inner_text("body") or ""
            except FlowTransientNetworkError:
                raise
            except Exception as e:
                if self._looks_like_browser_closed_error(e):
                    raise FlowBrowserClosedError(str(e))
                body_raw = ""

            tail = body_raw[-4200:]
            tail_lower = tail.lower()

            # If the newest Agent response says the generation is already starting,
            # leave immediately. This must take precedence over stale approval text.
            progress_markers = (
                "generating", "creating video", "generation in progress",
                "i'm going to generate", "i’m going to generate",
                "going to generate a", "video interpolation between",
                "i'll generate", "i’ll generate", "starting the video",
            )
            progress_pos = max((tail_lower.rfind(x) for x in progress_markers), default=-1)
            confirmation_phrases = (
                "would you like me to kick off", "would you like me to start",
                "would you like me to generate", "costing", "credits",
            )
            confirm_pos = max((tail_lower.rfind(x) for x in confirmation_phrases), default=-1)
            if progress_pos >= 0 and progress_pos >= confirm_pos:
                self.last_agent_confirmation["reason"] =                     "generation already started/no visible approval required"
                return False

            visible = []
            for label in labels:
                loc = clickable_action(label)
                if loc is not None:
                    visible.append((label, loc))
            if visible:
                saw_clickable = True
                m = re.search(r"cost(?:ing|s)?\s+([0-9][0-9,]*)\s+(?:ai\s+)?credits?", tail, re.I)
                if not m:
                    m = re.search(r"([0-9][0-9,]*)\s+(?:ai\s+)?credits?", tail, re.I)
                if m:
                    cost = int(m.group(1).replace(",", ""))
                    self.last_agent_confirmation["cost"] = cost
                    if max_credits is not None and cost > int(max_credits):
                        self.last_agent_confirmation.update(
                            blocked=True, reason=f"credit guard: {cost} > {int(max_credits)}")
                        print(f"[Flow] Credit guard blocked generation: {cost} > {int(max_credits)} credits")
                        return False

                # Prefer Always approve only when explicitly requested.
                if approval == "always":
                    visible.sort(key=lambda x: 0 if x[0].lower() == "always approve" else 1)
                for label, loc in visible:
                    try:
                        try:
                            loc.click(timeout=1200)
                        except TypeError:
                            loc.click()
                        self.last_agent_confirmation["clicked"] = label
                        print(f"[Flow] Credit confirmation: clicked {label!r}"
                              + (f" ({self.last_agent_confirmation.get('cost')} credits)"
                                 if self.last_agent_confirmation.get('cost') is not None else ""))
                        self._page.wait_for_timeout(600)
                        return True
                    except Exception as e:
                        if self._looks_like_browser_closed_error(e):
                            raise FlowBrowserClosedError(str(e))
                        # A short-lived overlay can steal a click; keep polling.
                        pass

            # Compatibility for Flow cohorts where Approve is a clickable div
            # without button/role/tabindex semantics. Only attempt this when the
            # *newest* Agent text is an explicit current credit question; never
            # because generic page text says Generate/Create/Continue.
            explicit_confirmation = bool(re.search(
                r"would you like me to (?:kick off|start|create|generate).*?(?:credits?|generation)",
                tail, re.I | re.S))
            if explicit_confirmation and confirm_pos > progress_pos:
                m = re.search(r"cost(?:ing|s)?\s+([0-9][0-9,]*)\s+(?:ai\s+)?credits?", tail, re.I)
                if not m:
                    m = re.search(r"([0-9][0-9,]*)\s+(?:ai\s+)?credits?", tail, re.I)
                if m:
                    cost = int(m.group(1).replace(",", ""))
                    self.last_agent_confirmation["cost"] = cost
                    if max_credits is not None and cost > int(max_credits):
                        self.last_agent_confirmation.update(
                            blocked=True, reason=f"credit guard: {cost} > {int(max_credits)}")
                        print(f"[Flow] Credit guard blocked generation: {cost} > {int(max_credits)} credits")
                        return False
                raw_labels = (["Always approve", "Approve", "Approve once"]
                              if approval == "always" else ["Approve", "Approve once"])
                for label in raw_labels:
                    try:
                        if self._click_text_action(label, timeout_ms=450):
                            self.last_agent_confirmation["clicked"] = label
                            print(f"[Flow] Credit confirmation: clicked nonsemantic {label!r}"
                                  + (f" ({self.last_agent_confirmation.get('cost')} credits)"
                                     if self.last_agent_confirmation.get('cost') is not None else ""))
                            self._page.wait_for_timeout(600)
                            return True
                    except Exception as e:
                        if self._looks_like_browser_closed_error(e):
                            raise FlowBrowserClosedError(str(e))

            try:
                self._page.wait_for_timeout(300)
            except Exception as e:
                if self._looks_like_browser_closed_error(e):
                    raise FlowBrowserClosedError(str(e))

        if saw_clickable:
            # Only a genuinely clickable approval action can produce a blocked
            # result. Historical text or generic page controls can never do so.
            self.last_agent_confirmation.update(
                blocked=True,
                reason="a clickable Flow approval control remained visible but could not be activated")
        else:
            self.last_agent_confirmation["reason"] =                 "no clickable credit approval is present; continue waiting for generation"
        return False

    def select_video_mode(self, mode: str = "text"):
        # Rebuilt Flow no longer exposes Text-to-Video as a fixed top-level tab.
        # Official UI: click the current model name (Nano Banana by default),
        # choose Video, then configure model/aspect/duration.
        if mode == "text":
            picker = self._try_resolve("generation_type_picker", timeout_ms=3500)
            if picker:
                try:
                    picker.click()
                    self._resolve("video_option", timeout_ms=5000).click()
                    return
                except FlowUIChanged:
                    pass
            # Legacy fallback. We do NOT silently continue merely because a prompt
            # box exists: the new default is Image and that could spend credits on
            # the wrong media type.
            self._resolve("text_to_video_tab", timeout_ms=3500).click()
            return

        action = {"frames": "frames_to_video_tab",
                  "ingredients": "ingredients_tab"}.get(mode)
        if not action:
            raise FlowUIChanged(f"Unsupported Flow video mode: {mode}")
        self._resolve(action).click()

    def select_image_mode(self):
        picker = self._try_resolve("generation_type_picker", timeout_ms=3500)
        if picker:
            try:
                picker.click()
                self._resolve("image_option", timeout_ms=5000).click()
                return
            except FlowUIChanged:
                pass
        self._resolve("image_tab").click()

    def submit_image_prompt(self, prompt: str):
        try:
            url = str(getattr(self._page, "url", "") or "")
        except Exception:
            url = ""
        if "/edit/" in url:
            canonical = self.normalize_project_url(url) or getattr(self, "_project_url", "")
            if not self.recover_project_page(canonical, timeout_ms=12000):
                raise FlowUIChanged(
                    "Flow is still on a generated-media /edit/ page; refusing to submit an image prompt there")
        self._set(FlowState.SUBMITTING)
        box = self._resolve("prompt_box")
        box.click()
        box.fill(prompt[:4000])
        self._resolve("generate_button").click()
        self._set(FlowState.GENERATING)

    def select_model(self, model_label: str):
        self._set(FlowState.SETTING_MODEL)
        try:
            self._resolve("model_picker").click()
        except FlowUIChanged:
            pass
        self._click_text(model_label)

    def set_aspect_ratio(self, aspect: str):
        self._resolve("aspect_portrait" if aspect == "9:16" else "aspect_landscape").click()

    def set_duration(self, seconds: int):
        try:
            self._click_text(str(seconds))
        except FlowUIChanged:
            pass

    def set_output_count(self, count: int):
        try:
            self._click_text(str(count))
        except FlowUIChanged:
            pass

    def upload_reference(self, path: str):
        self._set(FlowState.UPLOADING_REFERENCE)
        with self._page.expect_file_chooser(timeout=self.ui["timeouts"]["upload"] * 1000) as fc:
            self._resolve("upload_button").click()
        fc.value.set_files(path)

    def set_first_frame(self, path: str):
        try:
            self._resolve("first_frame_slot").click()
            with self._page.expect_file_chooser(timeout=30000) as fc:
                self._page.keyboard.press("Enter")
            fc.value.set_files(path)
        except Exception as e:
            raise FlowUIChanged(f"first-frame slot: {e}")

    def set_last_frame(self, path: str):
        try:
            self._resolve("last_frame_slot").click()
            with self._page.expect_file_chooser(timeout=30000) as fc:
                self._page.keyboard.press("Enter")
            fc.value.set_files(path)
        except Exception as e:
            raise FlowUIChanged(f"last-frame slot: {e}")

    def submit_prompt(self, prompt: str):
        self._set(FlowState.SUBMITTING)
        box = self._resolve("prompt_box")
        box.click()
        box.fill(prompt[:4000])
        self._resolve("generate_button").click()
        self._set(FlowState.GENERATING)

    def detect_failure(self) -> str | None:
        try:
            # Flow keeps historical Agent turns in the DOM.  Use the full body
            # for occurrence counts and a tail window only for recency checks.
            body_raw = self._page.inner_text("body") or ""
            body = body_raw.lower()
            tail = body[-9000:]
        except Exception as e:
            if self._looks_like_browser_closed_error(e):
                raise FlowBrowserClosedError(str(e))
            return None

        progress_markers = (
            "pending", "generating", "creating image", "creating video",
            "generation in progress", "rendering video", "making your video",
            "i'm going to generate", "i’m going to generate",
        )
        newest_progress = max((tail.rfind(x) for x in progress_markers), default=-1)

        # Usage-limit cards also persist in Agent history. Raise only when the
        # newest relevant state is still the limit; a later progress marker means
        # the account recovered and a newer request is already running.
        newest_quota = (-1, None)
        for t in self.ui["actions"].get("quota_texts", []):
            marker = str(t).lower()
            pos = tail.rfind(marker) if marker else -1
            if pos > newest_quota[0]:
                newest_quota = (pos, str(t))
        if newest_quota[0] >= 0 and newest_progress <= newest_quota[0]:
            raise FlowQuotaExceeded(
                f"Flow reports an account usage/rate limit ({newest_quota[1]!r}). "
                "Existing project media is safe; no automatic retry was submitted.")

        baseline = getattr(self, "_agent_failure_baseline", {}) or {}

        newest_failure = (-1, None)
        for t in self.ui["actions"].get("failure_texts", []):
            marker = str(t).lower().strip()
            if not marker:
                continue
            pos = tail.rfind(marker)
            if pos < 0:
                continue
            current_count = body.count(marker)
            prior_count = int(baseline.get(marker, 0) or 0)
            # If this exact failure string was already present before the current
            # submission and no new occurrence appeared, it is stale history.
            if baseline and current_count <= prior_count:
                continue
            if pos > newest_failure[0]:
                newest_failure = (pos, str(t))

        if newest_failure[0] < 0:
            return None
        # A newer progress marker means Flow has already moved on from the failure
        # card (e.g. user clicked Try again / Always approve manually).
        if newest_progress > newest_failure[0]:
            return None
        return newest_failure[1]

    def wait_for_generation(self, timeout_s: int | None = None,
                            indicator_key: str = "generating_indicator") -> bool:
        timeout_s = timeout_s or self.ui["timeouts"]["generation"]
        poll = self.ui["timeouts"]["poll_interval"]
        deadline = time.time() + timeout_s
        seen_busy = False
        while time.time() < deadline:
            fail = self.detect_failure()
            if fail:
                self._set(FlowState.FAILED)
                return False
            # generating indicator gone (after having been seen) => complete
            try:
                inds = self.ui["actions"].get(indicator_key) or []
                n = 0
                for ind in inds:
                    n += self._page.get_by_text(ind.get("text", "Generating"), exact=False).count()
                if n > 0:
                    seen_busy = True
                elif seen_busy:
                    self._set(FlowState.GENERATION_COMPLETE)
                    return True
            except Exception:
                pass
            time.sleep(poll)
        return False

    def wait_for_image(self, timeout_s: int | None = None) -> bool:
        return self.wait_for_generation(timeout_s or 300, "image_generating_indicator")

    def download_image(self, card_index: int, out_path: str):
        self._set(FlowState.DOWNLOADING)
        return self.download_generation(card_index, out_path)

    def collect_generation_cards(self) -> list:
        try:
            cands = self._candidates("generation_card")
            loc = self._page.locator(cands[0].get("selector", "[data-generation-card]")) if cands and cands[0].get("by") == "css" else None
            if loc is None:
                return []
            return [loc.nth(i) for i in range(min(loc.count(), 6))]
        except Exception:
            return []

    def download_generation(self, card_index: int, out_path: str):
        self._set(FlowState.DOWNLOADING)
        cards = self.collect_generation_cards()
        if cards and card_index < len(cards):
            cards[card_index].click()
        with self._page.expect_download(timeout=self.ui["timeouts"]["download"] * 1000) as dl:
            self._resolve("download_button").click()
        d = dl.value
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        d.save_as(out_path)
        return out_path

    def request_upscale(self):
        self._resolve("upscale_button").click()
        self._set(FlowState.GENERATING)

    # ---------- assisted mode ----------
    @staticmethod
    def watch_folder(folder: str, known: set[str], timeout_s: int = 600, poll: int = 5) -> str | None:
        """Return newest finished video file appearing in folder (assisted mode)."""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            files = []
            for ext in ("*.mp4", "*.webm", "*.mov"):
                files += glob.glob(os.path.join(folder, ext))
            fresh = sorted([f for f in files if f not in known and os.path.getsize(f) > 100000],
                           key=os.path.getmtime)
            if fresh:
                cand = fresh[-1]
                s1 = os.path.getsize(cand)
                time.sleep(4)  # ensure download finished (size stable)
                if os.path.getsize(cand) == s1:
                    return cand
            time.sleep(poll)
        return None


class FlowBrowserProvider(VideoProvider):
    """v3 provider wrapper around FlowBrowser (subscription, no API billing)."""
    name = "flow"

    def __init__(self, headless: bool = False, profile_dir: str | None = None):
        self.bridge: FlowBrowser | None = None
        self.headless = headless
        self.profile_dir = profile_dir
        self._last_video_baseline: set[str] = set()
        self._last_video_project_url: str = ""
        self._last_video_request_at: float = 0.0
        self._last_video_shot_id: str = ""

    def status(self) -> ProviderStatus:
        try:
            import playwright  # noqa
        except ImportError:
            return ProviderStatus(False, "playwright pip package missing (pip install playwright)")
        try:
            ui = yaml.safe_load(open("config/flow_ui.yaml", encoding="utf-8"))
            bcfg = resolve_browser_cfg(ui)
        except Exception:
            bcfg = {"mode": "auto"}
        sys_chrome = find_system_chrome()
        bits = [f"mode={bcfg.get('mode', 'auto')}"]
        bits.append(f"system-chrome={'yes' if sys_chrome else 'no'}")
        if sys_chrome:
            bits.append(sys_chrome)
        if bcfg.get("cdp_url"):
            bits.append(f"cdp={bcfg['cdp_url']}")
        if os.path.isdir(PROFILE_DIR) and os.listdir(PROFILE_DIR):
            bits.append("saved-session=yes")
        return ProviderStatus(True, " | ".join(bits))

    def _ensure(self):
        """Return a fully initialized Flow bridge, never a half-started one.

        Older builds assigned ``self.bridge`` before ``ensure_session()``.  If
        Playwright startup failed once, retries reused that poisoned object with
        ``_page=None`` and produced misleading ``NoneType.wait_for_timeout``
        errors.  Build the bridge transactionally and discard it on any startup
        failure so the next retry performs a real fresh launch.
        """
        if self.bridge is not None and getattr(self.bridge, "_page", None) is None:
            try:
                self.bridge.close()
            except Exception:
                pass
            self.bridge = None

        if self.bridge is None:
            if self.profile_dir:
                candidate = FlowBrowser(headless=self.headless, profile_dir=self.profile_dir)
            else:
                candidate = FlowBrowser(headless=self.headless)
            try:
                candidate.ensure_session()
            except Exception:
                try:
                    candidate.close()
                except Exception:
                    pass
                self.bridge = None
                raise
            self.bridge = candidate
        return self.bridge

    def is_transient_network_error(self, err) -> bool:
        try:
            b = self._ensure()
            return b._looks_like_network_error(err) or b.network_issue_detected(err)
        except Exception:
            return FlowBrowser._looks_like_network_error(err)

    def recover_network(self, project: str, timeout_s: int = 300, project_url: str | None = None) -> bool:
        b = self._ensure()
        if not b.wait_for_network_recovery(timeout_s=timeout_s):
            return False
        try:
            try:
                b.ensure_project(project, project_url=project_url)
            except TypeError:  # older bridge/test compatibility
                b.ensure_project(project)
            return True
        except Exception:
            return False

    def is_browser_closed_error(self, err) -> bool:
        return FlowBrowser._looks_like_browser_closed_error(err)

    def recover_browser(self, project: str, project_url: str | None = None) -> bool:
        """Recover a Flow page first; restart the browser only when the context is dead."""
        print("[Flow] Flow page closed unexpectedly; attempting soft page recovery...")
        try:
            b = self._ensure()
            if b.recover_project_page(project_url=project_url):
                try:
                    b.ensure_project(project, project_url=project_url)
                except TypeError:
                    b.ensure_project(project)
                print("[Flow] Page recovered without restarting the browser.")
                return True
        except Exception:
            pass

        print("[Flow] Browser context is not recoverable; rebuilding Flow session...")
        try:
            self.close()
            self.bridge = None
        except Exception:
            self.bridge = None
        try:
            b = self._ensure()
            b.ensure_project(project, project_url=project_url)
            print("[Flow] Browser session recovered.")
            return True
        except Exception as e:
            print(f"[Flow] Browser recovery failed: {str(e)[:220]}")
            return False

    def current_project_url(self) -> str:
        try:
            return self._ensure().current_project_url()
        except Exception:
            return ""

    def _ensure_live_recovery_project(self, project: str, project_url: str | None = None):
        """Return a live Flow bridge positioned on the canonical project page.

        Recovery waits are useful only while we actually have a browser/project
        page to inspect.  Older builds swallowed page/context failures and then
        slept for the full recovery timeout while no usable Flow window existed.
        v5.3.3 validates the page/context before every recovery poll and rebuilds
        the session immediately when necessary.
        """
        wanted = FlowBrowser.normalize_project_url(project_url) or self._last_video_project_url or ""

        def page_is_live(b):
            try:
                pg = getattr(b, "_page", None)
                if pg is None or pg.is_closed():
                    return False
                ctx = getattr(b, "_ctx", None)
                if ctx is None:
                    return False
                pages = list(getattr(ctx, "pages", []) or [])
                if not any(not x.is_closed() for x in pages):
                    return False
                return True
            except Exception:
                return False

        b = self._ensure()
        must_recover = not page_is_live(b)
        if not must_recover:
            try:
                raw = str(getattr(b._page, "url", "") or "")
                cur = FlowBrowser.normalize_project_url(raw)
                if "/edit/" in raw or (wanted and cur != wanted):
                    must_recover = True
            except Exception:
                must_recover = True

        if must_recover:
            print("[Flow] Recovery poll has no live canonical Flow project page; reopening it now...")
            if not self.recover_browser(project, project_url=wanted or project_url):
                return None
            b = self._ensure()

        try:
            try:
                b.ensure_project(project, project_url=wanted or project_url)
            except TypeError:
                b.ensure_project(project)
        except Exception as e:
            if FlowBrowser._looks_like_browser_closed_error(e):
                print("[Flow] Recovery project page disappeared; rebuilding before continuing the wait...")
                if not self.recover_browser(project, project_url=wanted or project_url):
                    return None
                b = self._ensure()
                try:
                    b.ensure_project(project, project_url=wanted or project_url)
                except TypeError:
                    b.ensure_project(project)
            else:
                return None

        # When running headed, make the fact that recovery is active visible to
        # the operator. This also wakes some Chromium/SPA rendering paths.
        if not self.headless:
            try:
                b._page.bring_to_front()
            except Exception:
                pass
        return b

    @staticmethod
    def _is_valid_video_file(path: str) -> bool:
        """Return True only for a time-based video, not a still image in disguise.

        v5.1 only checked ffprobe's ``codec_type=video``. A JPEG also has a video
        stream when probed as ``jpeg_pipe``, which allowed a single poster image
        to be saved as ``take_01.mp4`` and later exploded the renderer with an
        invalid/undefined duration. v5.2 requires a real container *and* finite
        positive duration.
        """
        try:
            if not path or not os.path.exists(path) or os.path.getsize(path) < 1024:
                return False
        except Exception:
            return False

        ffprobe = shutil.which("ffprobe")
        if ffprobe:
            try:
                import json as _json, math as _math
                cp = subprocess.run(
                    [ffprobe, "-v", "error", "-show_entries",
                     "format=format_name,duration:stream=codec_type,codec_name,duration,nb_frames,avg_frame_rate",
                     "-of", "json", path],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20)
                if cp.returncode != 0:
                    return False
                data = _json.loads(cp.stdout or "{}")
                fmt = data.get("format") or {}
                fmt_name = str(fmt.get("format_name") or "").lower()
                # Still-image demuxers are never acceptable as generated video.
                if any(x in fmt_name for x in ("image2", "jpeg_pipe", "png_pipe", "bmp_pipe", "gif")):
                    return False
                streams = [x for x in (data.get("streams") or []) if str(x.get("codec_type")) == "video"]
                if not streams:
                    return False
                durations = []
                for raw in [fmt.get("duration")] + [x.get("duration") for x in streams]:
                    try:
                        v = float(raw)
                        if _math.isfinite(v) and v > 0:
                            durations.append(v)
                    except Exception:
                        pass
                if not durations or max(durations) < 0.5:
                    return False
                return True
            except Exception:
                return False

        # Lightweight fallback only when ffprobe is unavailable. Require a real
        # container magic header; ordinary JPEG/PNG bytes are rejected.
        try:
            with open(path, "rb") as f:
                head = f.read(32)
            if len(head) >= 12 and head[4:8] == b"ftyp":
                return True
            if head.startswith(b"\x1aE\xdf\xa3"):
                return True
        except Exception:
            pass
        return False


    def _download_after_browser_recovery(self, project: str, out_path: str,
                                         project_url: str | None = None,
                                         preferred_signature: str | None = None,
                                         before_signatures: set[str] | None = None,
                                         attempts: int = 2) -> str:
        """Reconnect to the same project and re-download the already-generated newest asset.

        v4.8 strengthens the post-generation recovery path used when Flow closes
        the editor/page target during download.  We reconnect to the bound
        project URL, re-locate the newest asset using the same preferred
        signature/baseline that were captured before the original download
        attempt, and retry a small bounded number of times.
        """
        last_err = None
        tries = max(1, int(attempts or 1))
        for _ in range(tries):
            if not self.recover_browser(project, project_url=project_url):
                last_err = FlowBrowserClosedError(
                    'Could not rebuild Flow browser session after generation completed')
                continue
            b = self._ensure()
            try:
                b.ensure_project(project, project_url=project_url)
                return b.download_latest_asset(
                    out_path,
                    preferred_signature=preferred_signature,
                    before_signatures=before_signatures,
                )
            except FlowBrowserClosedError as e:
                last_err = e
                time.sleep(1)
                continue
        if last_err is not None:
            raise last_err
        raise FlowBrowserClosedError('Could not rebuild Flow browser session after generation completed')

    def rescue_recent_project_video(self, project: str, out_path: str,
                                    project_url: str | None = None,
                                    max_candidates: int = 8,
                                    wait_s: int = 0,
                                    baseline_signatures: set[str] | None = None,
                                    deadline_ts: float | None = None) -> dict | None:
        """Wait for/download an already-submitted Flow video without re-generating.

        v5.3.3 makes this a *project-page poll*, not an editor-click loop.  We
        require a live canonical Flow browser page before sleeping, never probe
        poster images as if they might be videos, and share one absolute deadline
        across the whole recovery call.  This prevents the old behaviour where
        the terminal printed a 179s wait while the browser was actually gone.
        """
        started_at = time.time()
        deadline = float(deadline_ts) if deadline_ts else started_at + max(0, int(wait_s or 0))
        baseline = set(baseline_signatures if baseline_signatures is not None
                       else (self._last_video_baseline or set()))
        announced = False
        tried_at: dict[str, float] = {}
        last_heartbeat = 0.0
        consecutive_reopen_failures = 0

        while True:
            now = time.time()
            if now >= deadline:
                return None

            b = self._ensure_live_recovery_project(project, project_url=project_url)
            if b is None:
                consecutive_reopen_failures += 1
                if consecutive_reopen_failures >= 3:
                    print("[Flow] Recovery aborted: could not reopen a live Flow project page after 3 attempts.")
                    return None
                time.sleep(min(5, max(1, deadline - time.time())))
                continue
            consecutive_reopen_failures = 0

            try:
                assets = b.media_assets()
            except FlowBrowserClosedError:
                # Do not silently sleep against a dead page. The next iteration
                # must visibly reopen/recover the canonical project page first.
                self.recover_browser(project, project_url=project_url)
                continue
            except Exception:
                assets = []

            fresh = [a for a in assets if str(a.get("sig", "") or "") and
                     (not baseline or str(a.get("sig")) not in baseline)]
            pool = fresh if fresh else ([] if baseline else assets)
            explicit_video = [a for a in pool if str(a.get("kind", "")).lower() == "video"]

            # Crucial v5.3.3 change: never click an untyped/image poster during
            # recovery. Opening those cards is what repeatedly drove Flow into
            # /edit/, closed targets, and produced hundreds of return-to-project
            # messages. Wait until Flow exposes an actual playable video tile.
            for a in list(reversed(explicit_video))[:max(1, int(max_candidates or 1))]:
                sig = str(a.get("sig", "") or "")
                if not sig:
                    continue
                if sig in tried_at and time.time() - tried_at[sig] < 20:
                    continue
                tried_at[sig] = time.time()
                try:
                    if os.path.exists(out_path):
                        os.remove(out_path)
                except Exception:
                    pass
                try:
                    b.download_latest_asset(out_path, preferred_signature=sig,
                                            before_signatures=(baseline or None))
                except FlowBrowserClosedError:
                    self.recover_browser(project, project_url=project_url)
                    continue
                except Exception:
                    continue
                if self._is_valid_video_file(out_path):
                    print("[Flow] Recovered the already-generated video from the Flow project; no new generation was submitted.")
                    return {"path": out_path, "provider": "flow", "model": "project-recovery",
                            "credits": -1, "dry_run": False,
                            "project_url": self.current_project_url(),
                            "log": "flow project video recovery"}
                try:
                    if os.path.exists(out_path):
                        os.remove(out_path)
                except Exception:
                    pass

            now = time.time()
            remaining = max(0, int(deadline - now))
            if not announced:
                print(f"[Flow] Existing video request may still be rendering; waiting up to {remaining}s for the already-generated video before any retry...")
                announced = True
            if now - last_heartbeat >= 15:
                try:
                    url = str(getattr(b._page, "url", "") or "")
                except Exception:
                    url = "(unavailable)"
                print(f"[Flow] Recovery heartbeat: browser=live project={FlowBrowser.normalize_project_url(url) or url} fresh_media={len(fresh)} video_tiles={len(explicit_video)} remaining={remaining}s")
                last_heartbeat = now

            # Wait only on a confirmed live page. If it dies during this sleep the
            # next loop reopens it instead of silently burning the timeout.
            sleep_s = min(5.0, max(0.2, deadline - time.time()))
            try:
                b._page.wait_for_timeout(int(sleep_s * 1000))
            except Exception:
                self.recover_browser(project, project_url=project_url)


    MODEL_LABELS = {
        "omni_draft": "Gemini Omni Flash 360p",
        "omni_standard": "Gemini Omni Flash 720p",
        "veo_lite": "Veo 3.1 - Lite",
        "veo_fast": "Veo 3.1 - Fast",
        "veo_quality": "Veo 3.1 - Quality",
    }

    @staticmethod
    def _save_request(out_path, data):
        target = out_path + ".flow-request.json"
        os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
        with open(target + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(target + ".tmp", target)

    def _record_submission(self, out_path, project_url, baseline, kind):
        self._save_request(out_path, {
            "status": "pending", "kind": kind, "project_url": project_url,
            "baseline": sorted(baseline), "signature": "", "submitted_at": time.time(),
            "request_hash": getattr(self, "_active_request_hash", ""),
        })

    def _record_asset(self, out_path, signature):
        with open(out_path + ".flow-request.json", encoding="utf-8") as f:
            request = json.load(f)
        request["signature"] = str(signature or "")
        self._save_request(out_path, request)

    def _asset_valid(self, path, kind):
        if kind == "video":
            return self._is_valid_video_file(path)
        try:
            from PIL import Image
            with Image.open(path) as im:
                im.verify()
            return True
        except Exception:
            return False

    def _guarded_generation(self, shot, compiled, refs, out_path, vertical, dry_run, kind):
        if kind != "image" or dry_run:
            return self._guarded_generation_once(shot, compiled, refs, out_path, vertical, dry_run, kind)
        # Retry the durable journal, not submission. Existing jobs inherit this
        # recovery policy. One missing-image replacement maximum across resumes.
        archive = out_path + ".flow-request.before-regeneration.json"
        if os.path.exists(archive) and not os.path.exists(out_path + ".flow-request.json"):
            raise FlowRequestPending("Image replacement was reserved but submission is uncertain; automatic regeneration blocked. Inspect the saved replacement record.")
        attempts = 3 if compiled.get("flow_image_auto_recover", True) else 0
        last = None
        for attempt in range(attempts + 1):
            try:
                return self._guarded_generation_once(shot, compiled, refs, out_path, vertical, False, kind)
            except FlowRequestPending as exc:
                last = exc
                if attempt == attempts:
                    break
                print(f"[Flow] Automatic image download recovery {attempt + 1}/{attempts}; no new generation.")
                try:
                    with open(out_path + ".flow-request.json", encoding="utf-8") as f:
                        request = json.load(f)
                    if not request.get("project_url"):
                        break
                    if FlowBrowser._looks_like_browser_closed_error(exc):
                        self.recover_browser(compiled.get("project") or "AutoVideoAI",
                                             project_url=request["project_url"])
                    # download_latest_asset now polls the live project for this
                    # exact signature; do not burn a blind delay between scans.
                    print("[Flow] Will rescan the exact recorded image after restoring the project; no prompt will be submitted.")
                except Exception:
                    pass
        # A failed download of a visible asset is NOT permission to regenerate.
        # Only replace an identified image absent on two successful project scans.
        archive = out_path + ".flow-request.before-regeneration.json"
        if attempts and compiled.get("flow_image_auto_regenerate", True) and not os.path.exists(archive):
            try:
                with open(out_path + ".flow-request.json", encoding="utf-8") as f:
                    request = json.load(f)
                key = hashlib.sha256(json.dumps([kind, str(getattr(shot, "shot_id", "")),
                    compiled.get("prompt", ""), vertical], sort_keys=True).encode()).hexdigest()
                bound = FlowBrowser.normalize_project_url(compiled.get("project_url"))
                eligible = (request.get("request_hash") == key and request.get("kind") == "image"
                            and request.get("signature") and request.get("project_url")
                            and time.time() - float(request.get("submitted_at", time.time())) >= 360
                            and (not bound or bound == request["project_url"]))
                if eligible:
                    b = self._ensure()
                    absent = True
                    for scan in range(2):
                        b.ensure_project(compiled.get("project") or "AutoVideoAI",
                                         project_url=request["project_url"])
                        assets = b.media_assets()
                        body = b._page.locator("body").inner_text(timeout=3000).lower()
                        if any(word in body for word in ("generating", "creating image", "in progress", "queued")):
                            absent = False
                            break
                        # Empty/loading grids cannot establish absence.
                        baseline = request.get("baseline") or []
                        # Require the entire saved pre-submission baseline to be
                        # visible, not merely an arbitrary nonempty gallery slice.
                        if (not assets or not baseline
                                or b.current_project_url() != request["project_url"]
                                or not all(any(media_signature_matches(a.get("sig"), old)
                                               for a in assets) for old in baseline)
                                or any(media_signature_matches(a.get("sig"), request["signature"])
                                       for a in assets)):
                            absent = False
                            break
                        if scan == 0:
                            b._page.wait_for_timeout(30000)
                    if absent:
                        # Persist cap BEFORE submission; never overwrite audit history.
                        with open(archive, "x", encoding="utf-8") as reservation:
                            json.dump(request, reservation, indent=2)
                            reservation.flush()
                            os.fsync(reservation.fileno())
                        os.remove(out_path + ".flow-request.json")
                        print("[Flow] Recorded image absent after recovery scans; regenerating once (may use image credits), then retrying download.")
                        replacement = dict(compiled, project_url=request["project_url"])
                        try:
                            return self._guarded_generation_once(shot, replacement, refs, out_path, vertical, False, kind)
                        except FlowRequestPending:
                            return self._guarded_generation(shot, replacement, refs, out_path, vertical, False, kind)
            except (FlowAuthNeeded, FlowQuotaExceeded):
                raise
            except Exception as exc:
                print(f"[Flow] Missing-image replacement could not complete: {type(exc).__name__}")
        raise last

    def _guarded_generation_once(self, shot, compiled, refs, out_path, vertical, dry_run, kind):
        generate_once = self._generate_video_once if kind == "video" else self._generate_image_once
        args = (shot, compiled, refs, out_path, vertical) if kind == "video" else (shot, compiled, out_path, vertical)
        if dry_run:
            return generate_once(*args, dry_run=True)
        key = hashlib.sha256(json.dumps([kind, str(getattr(shot, "shot_id", "")),
            compiled.get("prompt", ""), vertical], sort_keys=True).encode()).hexdigest()
        self._active_request_hash = key
        journal = out_path + ".flow-request.json"
        try:
            if os.path.exists(journal):
                with open(journal, encoding="utf-8") as f:
                    request = json.load(f)
                if request.get("request_hash") != key or request.get("kind") != kind:
                    raise FlowRequestPending("Recorded Flow request differs from this prompt; review the request record before replacing anything")
                bound = FlowBrowser.normalize_project_url(compiled.get("project_url"))
                if bound and request.get("project_url") and bound != request["project_url"]:
                    raise FlowRequestPending("Recorded request belongs to a different Flow project; restore its project binding")
                if not self._asset_valid(out_path, kind):
                    b = self._ensure()
                    url = request.get("project_url")
                    if not url:
                        raise FlowRequestPending("Request has no saved project URL; use assisted recovery, not regeneration")
                    print(f"[Flow] Download-only recovery of pending {kind}; no new prompt will be submitted: {url}")
                    b.ensure_project(compiled.get("project") or "AutoVideoAI", project_url=url)
                    if not request.get("signature"):
                        baseline = set(request.get("baseline", []))
                        fresh = [a for a in b.media_assets() if a.get("kind") == kind
                                 and a.get("sig") and not any(media_signature_matches(a["sig"], old) for old in baseline)]
                        if len(fresh) != 1:
                            raise FlowRequestPending("Existing request has no single identifiable asset; no recovery click submitted")
                        request["signature"] = fresh[0]["sig"]
                        self._save_request(out_path, request)
                    if not request.get("signature"):
                        raise FlowRequestPending("No unambiguous recorded asset; assisted recovery is required")
                    try:
                        b.download_latest_asset(out_path, preferred_signature=request["signature"],
                                                 before_signatures=set(request.get("baseline", [])))
                    except FlowUIChanged as error:
                        assets = b.media_assets()
                        # Keep full evidence locally; only a concise reason goes into runtime logs.
                        self._save_recovery_diagnostic(out_path, request, assets, str(error))
                        raise
                if not self._asset_valid(out_path, kind):
                    raise FlowRequestPending("Recovered file did not pass media validation")
                request["status"] = "downloaded"
                self._save_request(out_path, request)
                return {"path": out_path, "provider": "flow", "model": getattr(shot, "model", "imagen_flow"),
                        "credits": 0, "project_url": request.get("project_url"),
                        "log": "Recovered recorded Flow request; no new generation"}
            result = generate_once(*args, dry_run=False)
            if os.path.exists(journal):
                if not result.get("path") or not self._asset_valid(out_path, kind):
                    raise FlowRequestPending("Submitted Flow request has no validated local asset")
                with open(journal, encoding="utf-8") as f:
                    request = json.load(f)
                request["status"] = "downloaded"
                self._save_request(out_path, request)
            return result
        except Exception as exc:
            if os.path.exists(journal):
                # Initial post-submission failures previously advertised a
                # recovery.json that only a later resume attempt would create.
                # Capture evidence now without opening/restarting a browser.
                diagnostic = out_path + ".recovery.json"
                try:
                    self._record_failure_diagnostic(out_path, exc)
                except Exception as diagnostic_error:
                    print(f"[Flow] Could not save recovery diagnostic: {type(diagnostic_error).__name__}; request retained")
                details = (f"Recovery details: {diagnostic}. " if os.path.isfile(diagnostic)
                           else "Recovery diagnostic unavailable; inspect pause_state.json and the saved request. ")
                raise FlowRequestPending(
                    f"Flow {kind} request is saved at {journal}. Generation is blocked to avoid spending again. "
                    "Resume attempts download only. No manual MP4 step is required for an image request. "
                    f"{details}Cause: {type(exc).__name__}: {str(exc)[:300]}") from exc
            raise

    def _record_failure_diagnostic(self, out_path, error):
        with open(out_path + ".flow-request.json", encoding="utf-8") as handle:
            request = json.load(handle)
        assets, available, source, scan_error = [], False, "unavailable", ""
        bridge = getattr(self, "bridge", None)
        if bridge is not None:
            try:
                assets = bridge.media_assets()
                available, source = True, "current_page"
            except Exception as exc:
                scan_error = type(exc).__name__
        if not available and os.path.isfile(out_path + ".recovery.json"):
            try:
                with open(out_path + ".recovery.json", encoding="utf-8") as handle:
                    previous = json.load(handle)
                if previous.get("expected_signature") == request.get("signature"):
                    assets = previous.get("visible_assets") or []
                    source = "previous_diagnostic"  # Explicitly mark stale snapshots.
            except (OSError, ValueError):
                pass
        self._save_recovery_diagnostic(
            out_path, request, assets, f"{type(error).__name__}: {error}",
            visible_assets_available=available, asset_snapshot_source=source, asset_scan_error=scan_error)

    def generate(self, shot, compiled, refs, out_path, vertical, dry_run=False):
        return self._guarded_generation(shot, compiled, refs, out_path, vertical, dry_run, "video")

    @staticmethod
    def _save_recovery_diagnostic(out_path, request, assets, reason, **context):
        target = out_path + ".recovery.json"
        with open(target + ".tmp", "w", encoding="utf-8") as handle:
            json.dump({'kind': request.get('kind'), 'expected_signature': request.get('signature'),
                       'project_url': request.get('project_url'), 'visible_assets': assets,
                       'reason': reason, 'observed_at': time.time(), 'diagnostic_only': True,
                       'submission_journal_present': True, 'new_generations': 0, **context}, handle, indent=2)
        os.replace(target + ".tmp", target)

    def generate_image(self, shot, compiled, out_path, vertical, dry_run=False):
        return self._guarded_generation(shot, compiled, {}, out_path, vertical, dry_run, "image")

    def _generate_video_once(self, shot, compiled: dict, refs: dict, out_path: str,
                 vertical: bool, dry_run: bool = False) -> dict:
        if dry_run:
            return {"path": None, "provider": "flow", "model": shot.model, "seed": None,
                    "credits": 0, "dry_run": True,
                    "log": f"DRY RUN: would generate {shot.shot_id} via Flow/{shot.model} (no credits)"}
        b = self._ensure()
        project = (compiled.get("project") or "AutoVideoAI").strip() or "AutoVideoAI"
        project_url = FlowBrowser.normalize_project_url(compiled.get("project_url"))
        aspect = "9:16" if vertical else "16:9"
        model_label = self.MODEL_LABELS.get(shot.model, "Gemini Omni Flash 360p")
        duration = int(shot.gen_duration or 8)
        approval = str(compiled.get("approval", "once") or "once")
        cap = compiled.get("max_generation_credits", 10)
        recovery_wait_s = max(0, int(compiled.get("flow_video_recovery_wait_seconds", 180) or 0))
        try:
            try:
                b.ensure_project(project, project_url=project_url)
            except TypeError:  # older bridge/test compatibility
                b.ensure_project(project)
            try:
                project_url = b.current_project_url() or project_url
            except Exception:
                pass

            # A factory retry re-enters generate(). Before submitting another
            # credit-bearing request, perform one short final scan for the video
            # produced by the immediately previous request for this same shot.
            if (self._last_video_shot_id == getattr(shot, "shot_id", "")
                    and self._last_video_request_at > 0
                    and time.time() - self._last_video_request_at < 15 * 60):
                pre_retry_wait = min(30, recovery_wait_s)
                if pre_retry_wait > 0:
                    print(f"[Flow] Retry guard: checking the existing project for up to {pre_retry_wait}s before submitting another video request...")
                    rescued = self.rescue_recent_project_video(
                        project, out_path, project_url=project_url, max_candidates=8,
                        wait_s=pre_retry_wait, baseline_signatures=self._last_video_baseline)
                    if rescued and rescued.get("path"):
                        self._last_video_shot_id = ""
                        return rescued

            if not hasattr(b, "prepare_text_video"):
                # Compatibility with older/mock bridge implementations.
                has_frames = bool(refs.get("start"))
                b.select_video_mode("frames" if has_frames else "text")
                b.select_model(model_label)
                b.set_aspect_ratio(aspect)
                b.set_duration(duration)
                if refs.get("start"):
                    try: b.set_first_frame(refs["start"])
                    except Exception: b.upload_reference(refs["start"])
                if refs.get("end"):
                    try: b.set_last_frame(refs["end"])
                    except Exception: pass
                b.submit_prompt(compiled.get("prompt", shot.visual_goal))
                if not b.wait_for_generation():
                    return {"path": None, "provider": "flow", "model": shot.model, "error": "generation failed/rejected in Flow"}
                b.download_generation(0, out_path)
                return {"path": out_path, "provider": "flow", "model": shot.model, "credits": -1, "dry_run": False}
            strategy = b.prepare_text_video(aspect=aspect, model_label=model_label,
                                            duration=duration, count=1)
            prompt = compiled.get("prompt", shot.visual_goal)

            if strategy == "agent":
                attach = []
                seen_media_hashes = set()
                # Opening/closing frame continuity is the preferred economy path.
                # De-duplicate by *content*, not only by path: older runs could have
                # location_master.jpg and shot_001_open.jpg pointing to identical
                # bytes, which confused Flow and reduced interpolation quality.
                for k in ("start", "end", "character", "location"):
                    pth = refs.get(k)
                    if not pth or not os.path.isfile(pth):
                        continue
                    try:
                        h = hashlib.sha256()
                        with open(pth, "rb") as fh:
                            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                                h.update(chunk)
                        sig = h.hexdigest()
                    except Exception:
                        sig = os.path.abspath(pth)
                    if sig in seen_media_hashes:
                        print(f"[Flow] Skipping duplicate reference content: {os.path.basename(pth)}")
                        continue
                    seen_media_hashes.add(sig)
                    attach.append(pth)
                if attach:
                    b.attach_agent_media(attach[:4], reuse_existing=bool(compiled.get("flow_reuse_project_media", True)))
                    labels = []
                    if refs.get("start"): labels.append("Use the first attached image as the exact START frame.")
                    if refs.get("end"): labels.append("Use the second attached image as the exact END frame.")
                    if refs.get("character"): labels.append("Preserve the attached character identity and wardrobe exactly.")
                    prompt = " ".join(labels) + " " + prompt
                # Snapshot *after* reference thumbnails are attached. Otherwise
                # those thumbnails look like newly generated media and can make
                # the Agent wait return early before a video exists.
                before_assets = b.media_asset_signatures()
                self._last_video_baseline = set(before_assets)
                self._last_video_project_url = str(project_url or b.current_project_url() or "")
                self._last_video_request_at = time.time()
                self._last_video_shot_id = str(getattr(shot, "shot_id", "") or "")
                b.fill_text_video_prompt(prompt, strategy, aspect=aspect,
                                         model_label=model_label, duration=duration, count=1)
                self._record_submission(out_path, project_url, before_assets, "video")
                b.submit_prepared_text_video(strategy)
                # First-use projects can take noticeably longer to display the
                # one-time credit approval card. Give the initial card a fair
                # window; wait_for_agent_generation also keeps probing safely.
                clicked = b.confirm_agent_generation(timeout_s=30, approval=approval,
                                                       max_credits=int(cap) if cap is not None else None)
                info = getattr(b, "last_agent_confirmation", {}) or {}
                if info.get("blocked"):
                    return {"path": None, "provider": "flow", "model": shot.model,
                            "credits": 0, "dry_run": False,
                            "error": f"Flow credit confirmation blocked: {info.get('reason')}"}
                # clicked can be False when Flow is configured not to ask.
                if not b.wait_for_agent_generation(
                        before_assets=before_assets,
                        service_busy_wait_s=compiled.get("flow_capacity_wait_seconds"),
                        service_busy_retries=compiled.get("flow_capacity_retries"),
                        required_kind="video",
                        video_ready_grace_s=compiled.get("flow_video_ready_grace_seconds", 20),
                        approval=approval,
                        max_generation_credits=int(cap) if cap is not None else None):
                    info = getattr(b, "last_agent_confirmation", {}) or info
                    return {"path": None, "provider": "flow", "model": shot.model,
                            "credits": info.get("cost", 0) or 0, "dry_run": False,
                            "error": "Flow Agent generation did not reach a detectable completed asset"}
                # A late first-project approval may have been clicked inside the
                # generation wait. Preserve its cost/action in the result.
                info = getattr(b, "last_agent_confirmation", {}) or info
                # One recovery budget per submitted request. Older builds could
                # enter two or three separate 179s recovery loops here (and the
                # factory added another), turning a 3-minute setting into tens of
                # minutes while sometimes no browser page was alive.
                recovery_deadline = time.time() + recovery_wait_s
                download_error = None
                self._record_asset(out_path, b.last_generated_asset_signature)
                try:
                    b.download_latest_asset(out_path,
                                            preferred_signature=b.last_generated_asset_signature,
                                            before_signatures=before_assets)
                except Exception as e:
                    download_error = e

                if not self._is_valid_video_file(out_path):
                    try:
                        if os.path.exists(out_path):
                            os.remove(out_path)
                    except Exception:
                        pass
                    rescued = None
                    if recovery_wait_s > 0:
                        rescued = self.rescue_recent_project_video(
                            project, out_path, project_url=project_url, max_candidates=8,
                            wait_s=recovery_wait_s, baseline_signatures=before_assets,
                            deadline_ts=recovery_deadline)
                    if not rescued:
                        detail = f": {str(download_error)[:160]}" if download_error else ""
                        return {"path": None, "provider": "flow", "model": shot.model,
                                "credits": info.get("cost", 0) or 0, "dry_run": False,
                                "error": "Flow produced media but no valid time-based video became downloadable within the single recovery window" + detail}
                self._last_video_shot_id = ""
                observed_cost = info.get("cost")
                if not observed_cost:
                    observed_cost = -1  # factory records configured model estimate when Flow did not expose cost
                return {"path": out_path, "provider": "flow", "model": shot.model,
                        "seed": None, "credits": observed_cost, "dry_run": False,
                        "project_url": b.current_project_url(),
                        "log": f"flow-agent ok ({info.get('clicked') or 'no-confirmation'})"}

            # Standard/legacy editor. References are added best-effort; if the
            # migrated UI changes, the economy profile will fall back to images.
            if refs.get("start"):
                try:
                    b.set_first_frame(refs["start"])
                except FlowUIChanged:
                    try: b.upload_reference(refs["start"])
                    except Exception: pass
            elif refs.get("storyboard") or refs.get("character"):
                try: b.upload_reference(refs.get("storyboard") or refs["character"])
                except Exception: pass
            if refs.get("end"):
                try: b.set_last_frame(refs["end"])
                except FlowUIChanged: pass
            b.fill_text_video_prompt(prompt, strategy, aspect=aspect,
                                     model_label=model_label, duration=duration, count=1)
            b.submit_prepared_text_video(strategy)
            ok = b.wait_for_generation()
            if not ok:
                return {"path": None, "provider": "flow", "model": shot.model, "seed": None,
                        "credits": 0, "dry_run": False, "error": "generation failed/rejected in Flow"}
            b.download_generation(0, out_path)
            return {"path": out_path, "provider": "flow", "model": shot.model,
                    "seed": None, "credits": -1, "dry_run": False, "log": "flow standard ok"}
        except (FlowUIChanged, FlowAuthNeeded, FlowQuotaExceeded, FlowServiceBusy, FlowBrowserClosedError) as e:
            try:
                snap = b.snapshot_failure(project, shot.shot_id, e)
            except Exception:
                snap = ""
            if snap:
                raise type(e)(f"{e} [snapshot: {snap}]")
            raise
        except Exception as e:
            try:
                b.snapshot_failure(project, shot.shot_id, e)
            except Exception:
                pass
            return {"path": None, "provider": "flow", "model": shot.model, "seed": None,
                    "credits": 0, "dry_run": False, "error": str(e)[:300]}

    def _generate_image_once(self, shot, compiled: dict, out_path: str,
                       vertical: bool, dry_run: bool = False) -> dict:
        if dry_run:
            return {"path": None, "provider": "flow", "model": "imagen_flow",
                    "dry_run": True, "log": f"DRY RUN: would generate image for {shot.shot_id}"}
        b = self._ensure()
        project = (compiled.get("project") or "AutoVideoAI").strip() or "AutoVideoAI"
        project_url = FlowBrowser.normalize_project_url(compiled.get("project_url"))
        aspect = "9:16" if vertical else "16:9"
        try:
            try:
                b.ensure_project(project, project_url=project_url)
            except TypeError:  # older bridge/test compatibility
                b.ensure_project(project)
            try:
                project_url = b.current_project_url() or project_url
            except Exception:
                pass
            still = (compiled.get("prompt", "") +
                     " Ultra detailed still frame, sharp focus, professional photography.")
            mode = b.detect_editor_mode()
            if mode == "agent":
                reference_paths = compiled.get("reference_paths") or []
                if reference_paths and b.attach_agent_media(reference_paths, reuse_existing=True) != len(reference_paths):
                    raise FlowUIChanged("Image worker could not attach all master references; generation not submitted")
                before_assets = b.media_asset_signatures()
                b._fill_editor_box("agent_prompt_box", b._agent_image_instruction(still, aspect, 1))
                self._record_submission(out_path, project_url, before_assets, "image")
                b.submit_prepared_text_video("agent")  # same Agent send action; instruction says STILL IMAGE
                if not b.wait_for_agent_generation(
                        before_assets=before_assets, timeout_s=360,
                        service_busy_wait_s=compiled.get("flow_capacity_wait_seconds"),
                        service_busy_retries=compiled.get("flow_capacity_retries"), required_kind="image"):
                    return {"path": None, "provider": "flow", "model": "imagen_flow",
                            "error": "Flow Agent image generation did not reach a detectable completed asset"}
                self._record_asset(out_path, b.last_generated_asset_signature)
                try:
                    b.download_latest_asset(out_path,
                                            preferred_signature=b.last_generated_asset_signature,
                                            before_signatures=before_assets)
                except FlowBrowserClosedError:
                    # The image already exists in Flow. Reconnect to the exact
                    # persisted project instead of creating a date-stamped project.
                    self._download_after_browser_recovery(project, out_path, project_url=project_url,
                        preferred_signature=b.last_generated_asset_signature,
                        before_signatures=before_assets, attempts=1)
                return {"path": out_path, "provider": "flow", "model": "imagen_flow",
                        "dry_run": False, "credits": 0, "project_url": b.current_project_url(),
                        "log": "flow-agent image ok"}

            try:
                b.select_image_mode()
                b.set_aspect_ratio(aspect)
            except FlowUIChanged:
                pass
            b.submit_image_prompt(still)
            if not b.wait_for_image():
                return {"path": None, "provider": "flow", "model": "imagen_flow",
                        "error": "image generation failed/rejected in Flow"}
            b.download_image(0, out_path)
            return {"path": out_path, "provider": "flow", "model": "imagen_flow",
                    "dry_run": False, "credits": 0, "log": "flow image ok"}
        except (FlowUIChanged, FlowAuthNeeded, FlowQuotaExceeded,
                FlowServiceBusy, FlowBrowserClosedError) as e:
            try:
                snap = b.snapshot_failure(project, shot.shot_id, e)
            except Exception:
                snap = ""
            if snap:
                raise type(e)(f"{e} [snapshot: {snap}]")
            raise

    def close(self):
        if self.bridge:
            self.bridge.close()
            self.bridge = None
