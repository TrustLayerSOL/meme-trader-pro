"""Timing profile models for offline evidence rebuilds."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_profile_id(created_at: str | None = None) -> str:
    value = created_at or utc_now_iso()
    digest = sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"offline-rebuild-profile-{digest}"


@dataclass
class OfflineRebuildStepProfile:
    step_name: str
    started_at: str
    ended_at: str | None = None
    elapsed_seconds: float | None = None
    input_count: int = 0
    output_count: int = 0
    skipped: bool = False
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def finish(self, output_count: int | None = None, warning_flags: list[str] | None = None) -> None:
        self.ended_at = utc_now_iso()
        self.elapsed_seconds = (
            datetime.fromisoformat(self.ended_at) - datetime.fromisoformat(self.started_at)
        ).total_seconds()
        if output_count is not None:
            self.output_count = output_count
        if warning_flags:
            self.warning_flags.extend(warning_flags)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_name": self.step_name,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "elapsed_seconds": self.elapsed_seconds,
            "input_count": self.input_count,
            "output_count": self.output_count,
            "skipped": self.skipped,
            "warning_flags": list(self.warning_flags),
            "metadata_json": dict(self.metadata_json),
        }


@dataclass
class OfflineRebuildProfile:
    profile_id: str
    created_at: str
    steps: list[OfflineRebuildStepProfile] = field(default_factory=list)
    total_elapsed_seconds: float | None = None
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, metadata_json: dict[str, Any] | None = None) -> "OfflineRebuildProfile":
        created_at = utc_now_iso()
        return cls(
            profile_id=make_profile_id(created_at),
            created_at=created_at,
            metadata_json=dict(metadata_json or {}),
        )

    def finish(self) -> None:
        ended_at = utc_now_iso()
        self.total_elapsed_seconds = (
            datetime.fromisoformat(ended_at) - datetime.fromisoformat(self.created_at)
        ).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "created_at": self.created_at,
            "steps": [step.to_dict() for step in self.steps],
            "total_elapsed_seconds": self.total_elapsed_seconds,
            "warning_flags": list(self.warning_flags),
            "metadata_json": dict(self.metadata_json),
        }
