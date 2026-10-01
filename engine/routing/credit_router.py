"""CreditRouter - model routing + budget planning from config (never hard-coded costs)."""
from __future__ import annotations
import os
import yaml

MODEL2PROVIDER = {"omni_draft": "flow", "omni_standard": "flow", "veo_lite": "flow",
                  "veo_fast": "flow", "veo_quality": "flow",
                  "wan_t2v": "comfy", "wan_i2v": "comfy", "ltx_t2v": "comfy", "ltx_i2v": "comfy",
                  "stock": "stock", "kenburns_plus": "image", "image_pair_motion": "image",
                  "movieflow_story": "movieflow", "movieflow_scene": "movieflow"}


def load_model_registry(path: str = "config/flow_models.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class CreditRouter:
    def __init__(self, profile: str = "FLOW_BALANCED", registry: dict | None = None,
                 overrides: dict | None = None):
        self.reg = registry or load_model_registry()
        self.profile = profile
        self.cfg = self.reg["profiles"][profile]
        self.budgets = dict(self.reg.get("budgets", {}))
        if overrides:
            self.budgets.update(overrides)

    def route(self, priority: str = "NORMAL", motion: str = "medium",
              needs_ref: bool = False, is_edit: bool = False,
              is_extend: bool = False) -> dict:
        table = self.cfg["routing"]
        key = priority
        if is_extend and "EXTEND" in table:
            key = "EXTEND"
        elif is_edit and "EDIT" in table:
            key = "EDIT"
        elif needs_ref and priority == "NORMAL" and "REFERENCE_HEAVY" in table:
            key = "REFERENCE_HEAVY"
        elif motion == "high" and priority != "HERO" and "HIGH_MOTION" in table:
            key = "HIGH_MOTION"
        model = table.get(key, table.get("NORMAL"))
        cands = self.cfg.get("candidates", {}).get(priority if priority in ("LOW", "NORMAL", "HERO") else "NORMAL", 1)
        return {"provider": MODEL2PROVIDER.get(model, "flow"), "model": model,
                "candidates": cands, "upscale": self.cfg.get("upscale_accepted", False)}

    def model_cost(self, model: str, seconds: int = 8) -> float:
        m = self.reg["models"].get(model, {})
        table = m.get("credit_costs") or {}
        if table:
            # YAML may deserialize integer keys as ints; tolerate strings too.
            if seconds in table:
                return float(table[seconds])
            if str(seconds) in table:
                return float(table[str(seconds)])
            # Pick the nearest supported duration instead of pretending costs are linear.
            pairs = []
            for k, v in table.items():
                try:
                    pairs.append((abs(int(k) - int(seconds)), float(v)))
                except Exception:
                    pass
            if pairs:
                pairs.sort(key=lambda x: x[0])
                return pairs[0][1]
        base = float(m.get("credits_per_8s", 0))
        return round(base * seconds / 8, 1)

    def estimate_job(self, shots, monthly_remaining: int | None = None) -> dict:
        per_shot = []
        total = 0.0
        for s in shots:
            c = self.model_cost(s.model, s.gen_duration) * max(1, s.num_candidates)
            if self.cfg.get("upscale_accepted"):
                up = float(self.reg["models"].get(s.model, {}).get("upscale_cost", 0))
                c += up  # assume 1 upscale per accepted shot (worst case)
            per_shot.append({"shot_id": s.shot_id, "model": s.model, "credits": round(c, 1)})
            total += c
        reserve = round(total * self.budgets.get("RETRY_RESERVE_PCT", 25) / 100, 1)
        projected = round(total + reserve, 1)
        return {"per_shot": per_shot, "estimated_credits": round(total, 1),
                "retry_reserve": reserve, "projected_total": projected,
                "monthly_remaining": monthly_remaining,
                "max_per_video": self.budgets.get("MAX_CREDITS_PER_VIDEO"),
                "within_budget": projected <= float(self.budgets.get("MAX_CREDITS_PER_VIDEO", 1e9))}
