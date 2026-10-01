"""Durable progress events shared by CLI and Studio."""
from __future__ import annotations
import datetime
import json
import os
import threading
import time
from .runtime_log import elapsed_text


class JobProgress:
    def __init__(self, job_dir: str, callback=None):
        self.job_dir = job_dir
        self.callback = callback
        self._lock = threading.Lock()
        self.log_dir = os.path.join(job_dir, "logs")
        os.makedirs(self.log_dir, exist_ok=True)
        self.started_epoch = time.time()
        os.environ["AUTOVIDEO_SESSION_STARTED_EPOCH"] = str(self.started_epoch)
        os.environ["AUTOVIDEO_RUNTIME_LOG"] = os.path.join(self.log_dir, "runtime.log")

    def emit(self, stage, percent, info=""):
        pct = max(0.0, min(100.0, float(percent)))
        event = {"ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                 "elapsed": elapsed_text(time.time() - self.started_epoch),
                 "percent": round(pct, 2), "stage": str(stage), "info": str(info or "")}
        with self._lock:
            with open(os.path.join(self.log_dir, "runtime.log"), "a", encoding="utf-8") as f:
                f.write(f"[{event['ts']}] [+{event['elapsed']}] [{pct:6.2f}%] {event['stage']} {event['info']}\n")
            target = os.path.join(self.log_dir, "progress.json")
            tmp = target + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(event, f, indent=2)
            os.replace(tmp, target)
        if self.callback:
            try:
                self.callback(stage, pct, info)
            except TypeError:
                self.callback(stage, pct)
