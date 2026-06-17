"""Run manifest and source-gap helpers for T007 production runs."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping

RUN_MANIFEST_SCHEMA_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

@dataclass(frozen=True)
class RunManifest:
    collector_run_id: str
    git_sha: str | None = None
    schema_version: int = RUN_MANIFEST_SCHEMA_VERSION
    codec_version: str | None = None
    parser_git_sha: str | None = None
    program_ids: dict[str, str] | None = None
    quote_mints: dict[str, str] | None = None
    helius_endpoint: str | None = None
    provider_region: str | None = None
    commitment_config: str | None = None
    subscription_config_hash: str | None = None
    rate_limit_config: dict[str, Any] | None = None
    campaign_start_time: float | None = None
    campaign_end_time: float | None = None
    machine_id: str | None = None
    started_at: str | None = None
    stopped_at: str | None = None
    stop_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["created_at"] = _now()
        data["manifest_hash"] = stable_hash({k: v for k, v in data.items() if k not in {"created_at", "manifest_hash"}})
        return data

@dataclass(frozen=True)
class SourceGap:
    source_lane: str
    subscription_id: str | None
    connection_id: str | None
    provider_region: str | None
    commitment: str | None
    missed_slot_start: int | None
    missed_slot_end: int | None
    gap_reason: str
    gap_repair_status: str = "unrepaired"

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["gap_id"] = stable_hash(data)
        return data
