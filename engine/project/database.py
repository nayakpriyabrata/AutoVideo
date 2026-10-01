"""SQLite job database (stdlib sqlite3 - no ORM needed)."""
from __future__ import annotations
import os
import sqlite3
import datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs(
  job_id TEXT PRIMARY KEY,
  topic TEXT, status TEXT, video_type TEXT, target_seconds INTEGER,
  aspect TEXT, profile TEXT, preset TEXT,
  script_status TEXT DEFAULT 'pending',
  flow_project TEXT DEFAULT '',
  est_credits INTEGER DEFAULT 0,
  actual_generations INTEGER DEFAULT 0,
  accepted_shots INTEGER DEFAULT 0,
  rejected_shots INTEGER DEFAULT 0,
  retry_count INTEGER DEFAULT 0,
  render_status TEXT DEFAULT 'pending',
  final_path TEXT DEFAULT '',
  dry_run INTEGER DEFAULT 0,
  updated_at TEXT
);
"""


class JobDB:
    def __init__(self, path: str = "data/jobs.db"):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.path = path
        with self._cx() as cx:
            cx.executescript(SCHEMA)

    def _cx(self):
        cx = sqlite3.connect(self.path)
        cx.row_factory = sqlite3.Row
        return cx

    def upsert(self, job_id: str, **fields):
        fields["updated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        cols = ["job_id", *fields.keys()]
        vals = [job_id, *fields.values()]
        sets = ", ".join(f"{c}=excluded.{c}" for c in fields)
        with self._cx() as cx:
            cx.execute(f"INSERT INTO jobs({','.join(cols)}) VALUES({','.join('?'*len(cols))}) "
                       f"ON CONFLICT(job_id) DO UPDATE SET {sets}", vals)

    def get(self, job_id: str) -> dict | None:
        with self._cx() as cx:
            r = cx.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return dict(r) if r else None

    def list(self, limit: int = 50) -> list[dict]:
        with self._cx() as cx:
            rows = cx.execute("SELECT * FROM jobs ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def bump(self, job_id: str, field: str, by: int = 1):
        with self._cx() as cx:
            cx.execute(f"UPDATE jobs SET {field}={field}+?, updated_at=? WHERE job_id=?",
                       (by, datetime.datetime.now().isoformat(timespec="seconds"), job_id))
