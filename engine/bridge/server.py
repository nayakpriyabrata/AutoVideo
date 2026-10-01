from __future__ import annotations
import argparse, json, os, threading, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(os.getenv("AUTOVIDEO_BRIDGE_STATE", "bridge_state.json"))
LOCK = threading.RLock()


def _default_state():
    return {"queue": [], "results": {}, "events": [], "downloads": [], "updated_at": time.time()}


def _load():
    with LOCK:
        if not ROOT.exists():
            return _default_state()
        try:
            data = json.loads(ROOT.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return _default_state()
            for k, v in _default_state().items():
                data.setdefault(k, v)
            return data
        except Exception:
            return _default_state()


def _save(data):
    with LOCK:
        data["updated_at"] = time.time()
        ROOT.parent.mkdir(parents=True, exist_ok=True)
        tmp = ROOT.with_suffix(ROOT.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(ROOT)


def enqueue(command: str, payload: dict | None = None) -> str:
    data = _load()
    task_id = uuid.uuid4().hex[:12]
    data["queue"].append({
        "id": task_id, "command": command, "payload": payload or {},
        "status": "queued", "created_at": time.time(), "claimed_at": None,
    })
    _save(data)
    return task_id


def get_result(task_id: str):
    return _load()["results"].get(task_id)


class Handler(BaseHTTPRequestHandler):
    server_version = "AutoVideoAIBridge/1.0"

    def _headers(self, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

    def _json(self, obj, code=200):
        self._headers(code)
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _body(self):
        n = int(self.headers.get("Content-Length", "0") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    def do_OPTIONS(self):
        self._headers(204)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            s = _load()
            return self._json({"ok": True, "queued": len([x for x in s["queue"] if x.get("status") == "queued"]), "time": time.time()})
        if path == "/next":
            s = _load()
            task = None
            for x in s["queue"]:
                if x.get("status") == "queued":
                    x["status"] = "claimed"
                    x["claimed_at"] = time.time()
                    task = x
                    break
            if task:
                _save(s)
            return self._json({"task": task})
        if path.startswith("/result/"):
            tid = path.rsplit("/", 1)[-1]
            return self._json({"result": _load()["results"].get(tid)})
        if path == "/state":
            return self._json(_load())
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._body()
        s = _load()
        if path == "/enqueue":
            tid = enqueue(body.get("command", "run_scene"), body.get("payload") or {})
            return self._json({"ok": True, "id": tid})
        if path == "/result":
            tid = str(body.get("id") or "")
            if not tid:
                return self._json({"error": "id required"}, 400)
            s["results"][tid] = body
            for x in s["queue"]:
                if x.get("id") == tid:
                    x["status"] = "done" if body.get("ok") else "failed"
            _save(s)
            return self._json({"ok": True})
        if path == "/event":
            body["time"] = time.time()
            s["events"] = (s["events"] + [body])[-500:]
            _save(s)
            return self._json({"ok": True})
        if path == "/download":
            body["time"] = time.time()
            s["downloads"] = (s["downloads"] + [body])[-200:]
            _save(s)
            return self._json({"ok": True})
        return self._json({"error": "not found"}, 404)

    def log_message(self, fmt, *args):
        if os.getenv("AUTOVIDEO_BRIDGE_VERBOSE") == "1":
            super().log_message(fmt, *args)


def run(host="127.0.0.1", port=8765):
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"AutoVideoAI Chrome bridge listening on http://{host}:{port}")
    print("Leave this window open while the Chrome companion extension is enabled.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--enqueue", help="queue one prompt and exit")
    ap.add_argument("--aspect", default="9:16")
    args = ap.parse_args()
    if args.enqueue:
        print(enqueue("run_scene", {"prompt": args.enqueue, "aspect": args.aspect}))
    else:
        run(args.host, args.port)

if __name__ == "__main__":
    main()
