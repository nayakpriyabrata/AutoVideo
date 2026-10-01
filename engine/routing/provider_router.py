"""ProviderRouter - profile-aware fallback chains. Never silently downgrades premium jobs."""
from __future__ import annotations


class NeedsDecision(Exception):
    """Raised when a premium job needs user input before downgrading."""
    def __init__(self, message: str, alternatives: list[str]):
        super().__init__(message)
        self.alternatives = alternatives


PREMIUM_PROFILES = {"FLOW_CINEMATIC", "FLOW_BALANCED", "FLOW_ECONOMY", "MANUAL_DIRECTOR"}


class ProviderRouter:
    CHAINS = {
        "FLOW_CINEMATIC": ["flow"],
        "FLOW_BALANCED": ["flow"],
        "FLOW_ECONOMY": ["flow"],
        "STORYBOARD_ECONOMY": ["flow", "movieflow", "stock", "image", "comfy"],
        "MANUAL_DIRECTOR": ["flow"],
        "LOCAL_FREE": ["comfy", "image"],
        "FREE_HYBRID": ["stock", "image", "comfy"],
    }

    def __init__(self, profile: str, allow_downgrade: bool | None = None):
        self.profile = profile
        self.chain = list(self.CHAINS.get(profile, ["flow"]))
        self.allow_downgrade = (profile not in PREMIUM_PROFILES) if allow_downgrade is None else allow_downgrade

    def plan(self, shot_provider: str, availability: dict[str, bool]) -> str:
        """Return provider to use. Raises NeedsDecision for premium jobs when primary is down."""
        if self.profile == "STORYBOARD_ECONOMY":
            # Never turn a free stock/image scene into a paid Flow generation just
            # because the free source is unavailable. Paid Flow is reserved only
            # for shots explicitly routed to flow by the credit planner.
            if shot_provider == "stock":
                ordered = ["stock", "image", "comfy"]
            elif shot_provider == "image":
                ordered = ["image", "stock", "comfy"]
            elif shot_provider == "flow":
                ordered = ["flow", "image", "stock", "comfy"]
            elif shot_provider == "movieflow":
                ordered = ["movieflow", "image", "flow", "stock", "comfy"]
            else:
                ordered = [shot_provider] + [p for p in ("image", "stock", "comfy") if p != shot_provider]
        else:
            ordered = [shot_provider] + [p for p in self.chain if p != shot_provider]
        for p in ordered:
            if availability.get(p):
                if p != shot_provider and not self.allow_downgrade:
                    raise NeedsDecision(
                        f"{shot_provider} unavailable for {self.profile}. Job paused.",
                        alternatives=[q for q in ordered if availability.get(q) and q != shot_provider])
                return p
        raise NeedsDecision(f"No providers available for {self.profile}.",
                            alternatives=[f"{p} (offline)" for p in ordered])
