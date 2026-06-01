"""Models for diagnostic native SOL proxy price quality review."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


@dataclass
class NativeSolProxyQualityConfig:
    max_abs_forward_return: float | None = 2.0
    max_abs_runup: float | None = 5.0
    max_price_jump_ratio: float | None = 25.0
    min_proxy_price_points_in_horizon: int = 2
    max_gap_between_proxy_points_sec: int = 300
    require_non_proxy_anchor: bool = False
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NativeSolProxyRowDecision:
    row_id: str
    token_mint: str
    passed: bool
    is_native_sol_proxy_backed: bool = False
    proxy_price_point_count: int = 0
    non_proxy_price_point_count: int = 0
    max_proxy_gap_sec: int | None = None
    max_price_jump_ratio_observed: float | None = None
    reasons_failed: list[str] = field(default_factory=list)
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NativeSolProxyQualityReport:
    report_id: str
    created_at: str
    dataset_path: str
    row_count: int = 0
    native_proxy_backed_count: int = 0
    native_proxy_passed_count: int = 0
    native_proxy_failed_count: int = 0
    non_proxy_count: int = 0
    pass_rate: float | None = None
    failure_reason_counts: dict[str, int] = field(default_factory=dict)
    token_counts: dict[str, int] = field(default_factory=dict)
    config: NativeSolProxyQualityConfig = field(default_factory=NativeSolProxyQualityConfig)
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["config"] = self.config.to_dict()
        return payload


def make_native_sol_proxy_quality_report_id(prefix: str = "native_sol_proxy_quality") -> str:
    created = datetime.now(timezone.utc).isoformat()
    digest = sha256(f"{prefix}|{created}".encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"
