"""Pydantic manifest models - the source of truth for every production."""
from __future__ import annotations
from pydantic import BaseModel, Field


class Shot(BaseModel):
    shot_id: str = "shot_001"
    voice_start: float = 0.0
    voice_end: float = 4.0
    duration_target: float = 4.0
    narration: str = ""
    coverage: str = "primary"  # hook/primary/closeup/insert/broll/hero_outro
    visual_goal: str = ""
    subject: str = ""
    subject_action: str = ""
    environment: str = ""
    camera_framing: str = ""
    camera_movement: str = ""
    lens_feeling: str = "35mm"
    lighting: str = ""
    color_palette: str = ""
    motion_intensity: str = "medium"  # low/medium/high
    reference_assets: list[str] = Field(default_factory=list)
    start_frame: str | None = None
    end_frame: str | None = None
    provider: str = "flow"      # flow/comfy/stock/image
    model: str = "veo_lite"
    gen_duration: int = 8
    num_candidates: int = 1
    negative: str = ""
    transition_in: str = "cut"
    transition_out: str = "cut"
    priority: str = "NORMAL"    # LOW/NORMAL/HERO (+HIGH_MOTION/REFERENCE_HEAVY routing tags)
    qc_threshold: int = 70
    compiled_prompt: str = ""
    status: str = "planned"     # planned/approved/generating/qc/accepted/failed/skipped
    takes: list[str] = Field(default_factory=list)  # take file names
    accepted_take: str | None = None
    # v4 storyboard-economy routing metadata
    media_strategy: str = "flow_video"   # flow_video/image_motion/stock/local_video
    opening_frame: str | None = None
    closing_frame: str | None = None
    opening_frame_source: str = ""
    closing_frame_source: str = ""
    stock_query: str = ""
    estimated_credits: float = 0.0
    strategy_reason: str = ""
    continuity_group: str = "main"
    # What was actually used after runtime availability/fallback decisions.
    actual_provider: str = ""
    actual_model: str = ""
    fallback_reason: str = ""
    retry_count: int = 0
    retry_history: list[str] = Field(default_factory=list)
    credits_spent: int = 0


class ProductionManifest(BaseModel):
    job_id: str
    topic: str
    angle: str = ""
    audience: str = ""
    tone: str = "cinematic"
    content_type: str = "education"
    video_type: str = "shorts"
    target_seconds: int = 45
    aspect: str = "9:16"
    width: int = 1080
    height: int = 1920
    language: str = "en"
    voice: str = "en-IN-PrabhatNeural"
    voiceover_enabled: bool = True
    timing_source: str = "narration"  # narration | visual_storyboard
    preset: str = "cinematic_realism"
    profile: str = "FLOW_BALANCED"
    visual_style: str = ""
    color_palette: str = ""
    lighting_language: str = ""
    camera_language: str = ""
    pace: str = ""
    audio_mood: str = ""
    continuity_rules: list[str] = Field(default_factory=list)
    negative_constraints: list[str] = Field(default_factory=list)
    shots: list[Shot] = Field(default_factory=list)
    status: str = "created"  # created/scripted/narrated/planned/generating/review/rendering/done/failed/paused
    dry_run: bool = False

    def pending_shots(self) -> list[Shot]:
        return [s for s in self.shots if s.status in ("planned", "approved", "generating", "qc", "failed")]

    def accepted_count(self) -> int:
        return sum(1 for s in self.shots if s.status == "accepted")


class TakeRecord(BaseModel):
    shot_id: str
    take_id: str = "take_01"
    path: str = ""
    provider: str = ""
    model: str = ""
    prompt: str = ""
    seed: str | None = None
    created_at: str = ""
    duration: float = 0.0
    qc_overall: float = 0.0
    qc_decision: str = "pending"
