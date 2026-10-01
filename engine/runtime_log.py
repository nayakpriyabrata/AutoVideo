"""Timestamped console lines mirrored into the active job runtime log."""
from __future__ import annotations
import builtins
import datetime
import os
import threading
import time

_LOCK = threading.Lock()


def elapsed_text(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def timestamp_prefix() -> str:
    now = datetime.datetime.now().astimezone()
    try:
        started = float(os.getenv("AUTOVIDEO_SESSION_STARTED_EPOCH", "0") or 0)
    except Exception:
        started = 0
    elapsed = elapsed_text(time.time() - started) if started > 0 else "--:--:--"
    return f"[{now.isoformat(timespec='seconds')}] [+{elapsed}]"


def runtime_print(*args, **kwargs):
    """Behave like print(), while timestamping and persisting non-empty lines."""
    message = " ".join(str(x) for x in args)
    line = f"{timestamp_prefix()} {message}" if message.strip() else message
    builtins.print(line, **kwargs)
    path = os.getenv("AUTOVIDEO_RUNTIME_LOG", "").strip()
    if path and message.strip():
        try:
            with _LOCK:
                os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
                with open(path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except Exception:
            pass
