"""Common provider interface. All video engines implement this."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class FlowState(str, Enum):
    IDLE = "IDLE"
    WAITING_FOR_UI = "WAITING_FOR_UI"
    READY = "READY"
    SETTING_MODEL = "SETTING_MODEL"
    UPLOADING_REFERENCE = "UPLOADING_REFERENCE"
    SUBMITTING = "SUBMITTING"
    GENERATING = "GENERATING"
    GENERATION_COMPLETE = "GENERATION_COMPLETE"
    DOWNLOADING = "DOWNLOADING"
    QC = "QC"
    ACCEPTED = "ACCEPTED"
    RETRYING = "RETRYING"
    FAILED = "FAILED"


@dataclass
class ProviderStatus:
    available: bool
    reason: str = ""
    detail: dict = field(default_factory=dict)


class VideoProvider(ABC):
    name: str = "base"

    @abstractmethod
    def status(self) -> ProviderStatus:
        ...

    @abstractmethod
    def generate(self, shot, compiled: dict, refs: dict, out_path: str,
                 vertical: bool, dry_run: bool = False) -> dict:
        """Generate ONE take. Returns {path|None, provider, model, seed, credits, dry_run, log}."""
        ...

    def generate_image(self, shot, compiled: dict, out_path: str,
                       vertical: bool, dry_run: bool = False) -> dict:
        """Generate ONE still image for a scene (reference-first workflow)."""
        raise NotImplementedError(f"{self.name} has no image generation")
