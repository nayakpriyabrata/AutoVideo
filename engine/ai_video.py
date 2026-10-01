"""
AI Motion Video Providers (v2 engagement upgrade)

Providers:
  veo      - Google Veo 3.1 via Gemini API (~$0.10/s Fast 720p). Needs GEMINI_API_KEY with billing.
             NOTE: your Google AI Pro/Ultra *subscription* credits do NOT work on the API.
             Use "flow" mode below to leverage your subscription ($0 extra).
  seedance - ByteDance Seedance 2.0 via fal.ai (~$0.24/s Fast 720p). Needs FAL_KEY.
  fal      - Any custom fal.ai endpoint (Kling/Pika/Vidu/...). Needs FAL_KEY + FAL_ENDPOINT.
  flow     - Clips YOU generate in the Flow app with your subscription, dropped in assets/flow_clips/.
             Platform auto-assembles them. $0 extra. (Recommended with your subscription!)
  comfy    - Local ComfyUI (Wan / LTX-Video / Hunyuan - free, needs NVIDIA GPU).
"""
import os
import glob
import time
import json
import requests

# Approx USD per output second (2026) - for cost estimates
COST_PER_SEC = {
    "veo": 0.10, "seedance": 0.24, "fal": 0.20,
    "flow": 0.0, "stock": 0.0, "kenburns": 0.0, "comfy": 0.0,
}

PROVIDER_LABELS = {
    "veo": "Google Veo 3.1 Fast (Gemini API)",
    "seedance": "Seedance 2.0 Fast (fal.ai)",
    "fal": "Custom fal.ai endpoint",
    "comfy": "Local ComfyUI (free)",
}

SEEDANCE_ENDPOINTS = {
    "fast": "bytedance/seedance-2.0/fast/text-to-video",
    "quality": "bytedance/seedance-2.0/text-to-video",
}

CAMERA_MOVES = [
    "slow cinematic dolly-in", "smooth pan from left to right",
    "gentle aerial drift forward", "slow orbit around the subject",
    "intimate close-up with shallow depth of field", "wide establishing shot, slow tilt up",
    "tracking shot following the subject", "slow zoom out revealing the environment",
]


def estimate_cost(provider: str, seconds: float) -> float:
    return round(COST_PER_SEC.get(provider, 0.0) * seconds, 2)


def provider_key_present(provider: str) -> bool:
    if provider == "veo":
        return bool((os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip())
    if provider in ("seedance", "fal"):
        return bool(os.getenv("FAL_KEY", "").strip())
    if provider == "comfy":
        return True  # local, no key (needs ComfyUI running)
    return False


# ---------------- Shot planning (for Flow app + APIs) ----------------

def plan_shots(scenes: list, topic: str, vertical: bool, workdir: str) -> dict:
    """Build per-scene AI-video prompts + a copy-paste shot list for Flow."""
    os.makedirs(workdir, exist_ok=True)
    from .visuals import _keywords
    comp = "vertical 9:16 composition, subject centered" if vertical else "wide 16:9 cinematic composition"
    shots = []
    for i, scene in enumerate(scenes):
        kw = _keywords(scene, topic)
        move = CAMERA_MOVES[i % len(CAMERA_MOVES)]
        prompt = (f"{kw}, {move}, cinematic lighting, photorealistic, ultra detailed, "
                  f"smooth natural motion, {comp}, no text, no watermark, no logos")
        shots.append({"idx": i, "prompt": prompt, "file": f"shot{i:02d}.mp4",
                      "scene": scene[:200]})
    md = [f"# 🎞️ Shot List — {topic}", "",
          f"Scenes: {len(shots)} | Format: {'9:16 vertical' if vertical else '16:9 horizontal'}", "",
          "## Option A: Google Flow (uses your Gemini subscription, $0 extra)",
          "1. Open Flow (labs.google/fx) → New project → Text to Video (Veo)",
          f"2. Set output to **{'Portrait 9:16' if vertical else 'Landscape 16:9'}**, 8 seconds",
          "3. Paste each prompt below → Generate → Download",
          f"4. Rename downloads to `shot00.mp4`, `shot01.mp4`... and drop into `assets/flow_clips/`",
          "5. Back in Auto Video AI, set **Visual style → My Flow/Veo clips** → Generate Video", "",
          "## Option B: Fully automatic via API",
          "Set Visual style → AI video API, pick Veo/Seedance, add key in `.env` → Generate.", "",
          "---", ""]
    for s in shots:
        md += [f"### Shot {s['idx']:02d} → `{s['file']}`",
               f"*Scene: {s['scene']}...*",
               "```", s["prompt"], "```", ""]
    md_path = os.path.join(workdir, "shot_list.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    with open(os.path.join(workdir, "shots.json"), "w", encoding="utf-8") as f:
        json.dump(shots, f, indent=2)
    return {"shots": shots, "shot_list_md": md_path}


def collect_flow_clips(folder: str = "assets/flow_clips") -> list:
    """Sorted list of user-provided Flow/Veo clips (mp4/mov/webm/mkv)."""
    exts = ("*.mp4", "*.mov", "*.webm", "*.mkv", "*.MP4", "*.MOV")
    files = []
    for e in exts:
        files += glob.glob(os.path.join(folder, e))
    return sorted([f for f in files if os.path.getsize(f) > 10000])


# ---------------- API generation ----------------

def generate_ai_clips(shots: list, provider: str = "veo", vertical: bool = True,
                      workdir: str = "outputs/aiclips", progress_cb=None) -> dict:
    os.makedirs(workdir, exist_ok=True)
    if provider == "veo":
        return _gen_veo(shots, vertical, workdir, progress_cb)
    if provider in ("seedance", "fal"):
        return _gen_fal(shots, provider, vertical, workdir, progress_cb)
    if provider == "comfy":
        return _gen_comfy(shots, vertical, workdir, progress_cb)
    raise ValueError(f"Unknown provider: {provider}")


def _gen_veo(shots, vertical, workdir, progress_cb):
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise RuntimeError("google-genai not installed. Run: pip install google-genai")
    key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY missing in .env (get one at aistudio.google.com; API billing is separate from your subscription).")
    model = os.getenv("VEO_MODEL", "veo-3.1-fast-generate-preview")
    aspect = "9:16" if vertical else "16:9"
    client = genai.Client(api_key=key)
    clips = []
    for i, s in enumerate(shots):
        if progress_cb:
            progress_cb(f"🤖 Veo generating shot {i+1}/{len(shots)}...", 55 + int(20 * i / len(shots)))
        try:
            cfg = types.GenerateVideosConfig(number_of_videos=1, aspect_ratio=aspect,
                                             resolution="720p", duration_seconds=8)
            op = client.models.generate_videos(model=model, prompt=s["prompt"], config=cfg)
        except TypeError:  # older SDK: minimal config
            op = client.models.generate_videos(model=model, prompt=s["prompt"])
        except Exception as e:
            raise RuntimeError(f"Veo request failed: {e}")
        deadline = time.time() + 12 * 60
        while not op.done:
            if time.time() > deadline:
                raise RuntimeError("Veo timed out after 12 min for a shot.")
            time.sleep(15)
            op = client.operations.get(op)
        try:
            vid = op.response.generated_videos[0]
            out = os.path.join(workdir, s["file"])
            try:
                client.files.download(file=vid.video)
            except Exception:
                pass
            vid.video.save(out)
        except Exception as e:
            raise RuntimeError(f"Veo download failed: {e}")
        clips.append(out)
    secs = sum(_vdur(c) or 8 for c in clips)
    return {"clips": clips, "source": "veo", "cost_usd": estimate_cost("veo", secs)}


def _gen_fal(shots, provider, vertical, workdir, progress_cb):
    key = os.getenv("FAL_KEY", "").strip()
    if not key:
        raise RuntimeError("FAL_KEY missing in .env (get one at fal.ai/dashboard/keys).")
    if provider == "seedance":
        endpoint = os.getenv("FAL_ENDPOINT", SEEDANCE_ENDPOINTS["fast"])
    else:
        endpoint = os.getenv("FAL_ENDPOINT", SEEDANCE_ENDPOINTS["fast"])
    aspect = "9:16" if vertical else "16:9"
    # Some endpoints require duration, some forbid it -> probe once, reuse winner
    input_variants = [
        {"prompt": "", "resolution": "720p", "aspect_ratio": aspect},
        {"prompt": "", "resolution": "720p", "aspect_ratio": aspect, "duration": "10"},
        {"prompt": "", "resolution": "720p", "aspect_ratio": aspect, "duration": "5"},
    ]
    chosen = None
    clips = []
    for i, s in enumerate(shots):
        if progress_cb:
            progress_cb(f"🤖 {provider} generating shot {i+1}/{len(shots)}...", 55 + int(20 * i / len(shots)))
        variants = [chosen] if chosen else input_variants
        last_err = ""
        for v in variants:
            inp = dict(v); inp["prompt"] = s["prompt"]
            try:
                url = _fal_run(endpoint, key, inp)
                if chosen is None:
                    chosen = v
                out = os.path.join(workdir, s["file"])
                _download(url, out)
                clips.append(out)
                break
            except RuntimeError as e:
                last_err = str(e)
                continue
        else:
            raise RuntimeError(f"fal.ai failed: {last_err}")
    secs = sum(_vdur(c) or 8 for c in clips)
    return {"clips": clips, "source": provider, "cost_usd": estimate_cost(provider, secs)}


def _fal_run(endpoint: str, key: str, inp: dict) -> str:
    H = {"Authorization": f"Key {key}", "Content-Type": "application/json"}
    r = requests.post(f"https://queue.fal.run/{endpoint}", headers=H,
                      json={"input": inp}, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"submit {r.status_code}: {r.text[:200]}")
    rid = r.json().get("request_id")
    if not rid:
        raise RuntimeError(f"no request_id: {r.text[:200]}")
    deadline = time.time() + 12 * 60
    while True:
        s = requests.get(f"https://queue.fal.run/{endpoint}/requests/{rid}/status",
                         headers=H, timeout=30).json()
        st = s.get("status")
        if st == "COMPLETED":
            break
        if st in ("FAILED",):
            raise RuntimeError(f"generation failed: {json.dumps(s)[:300]}")
        if time.time() > deadline:
            raise RuntimeError("timed out after 12 min")
        time.sleep(10)
    res = requests.get(f"https://queue.fal.run/{endpoint}/requests/{rid}",
                       headers=H, timeout=30).json()
    url = ((res.get("video") or {}).get("url")) or ((res.get("data") or {}).get("video") or {}).get("url")
    if not url:
        raise RuntimeError(f"no video url: {json.dumps(res)[:300]}")
    return url


def _gen_comfy(shots, vertical, workdir, progress_cb):
    base = os.getenv("COMFY_URL", "http://127.0.0.1:8188").rstrip("/")
    wf_path = os.getenv("COMFY_WORKFLOW", "assets/comfy_workflow.json")
    if not os.path.exists(wf_path):
        raise RuntimeError(
            f"Local mode needs an API-format workflow at {wf_path}.\n"
            "In ComfyUI: build any Wan/LTX/Hunyuan text-to-video flow → enable Dev Mode → "
            "'Save (API Format)' → save as assets/comfy_workflow.json → put {PROMPT} where your "
            "prompt goes (also supports {SEED}, {WIDTH}, {HEIGHT}). Then start ComfyUI and retry.")
    with open(wf_path, encoding="utf-8") as f:
        wf_tpl = f.read()
    W, H = (720, 1280) if vertical else (1280, 720)
    clips = []
    for i, s in enumerate(shots):
        if progress_cb:
            progress_cb(f"🤖 ComfyUI generating shot {i+1}/{len(shots)}...", 55 + int(20 * i / len(shots)))
        wf = wf_tpl.replace("{PROMPT}", s["prompt"].replace('"', "'"))
        wf = wf.replace("{SEED}", str(1000 + i)).replace("{WIDTH}", str(W)).replace("{HEIGHT}", str(H))
        try:
            r = requests.post(f"{base}/prompt", json={"prompt": json.loads(wf)}, timeout=30)
            r.raise_for_status()
            pid = r.json()["prompt_id"]
        except Exception as e:
            raise RuntimeError(f"ComfyUI not reachable at {base}: {e}")
        deadline = time.time() + 30 * 60
        out_file = None
        while time.time() < deadline:
            time.sleep(8)
            try:
                hist = requests.get(f"{base}/history/{pid}", timeout=30).json().get(pid, {})
            except Exception:
                continue
            for node_out in (hist.get("outputs") or {}).values():
                for g in (node_out.get("gifs") or []) + (node_out.get("videos") or []):
                    out_file = (g.get("filename"), g.get("subfolder", ""), g.get("type", "output"))
            if out_file:
                break
        if not out_file:
            raise RuntimeError("ComfyUI timed out (30 min).")
        fn, sub, typ = out_file
        dl = requests.get(f"{base}/view", params={"filename": fn, "subfolder": sub, "type": typ}, timeout=120)
        out = os.path.join(workdir, os.path.splitext(s["file"])[0] + os.path.splitext(fn)[1])
        with open(out, "wb") as f:
            f.write(dl.content)
        clips.append(out)
    return {"clips": clips, "source": "comfy", "cost_usd": 0.0}


def _download(url: str, path: str):
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    with open(path, "wb") as f:
        f.write(r.content)
    if os.path.getsize(path) < 10000:
        raise RuntimeError("downloaded file too small")


def _vdur(path: str):
    try:
        from moviepy.editor import VideoFileClip
        c = VideoFileClip(path)
        d = c.duration
        c.close()
        return d
    except Exception:
        return None
