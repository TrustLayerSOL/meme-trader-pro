from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceLaneRuntime:
    lane: str
    requested_duration_seconds: float
    actual_duration_seconds: float
    reconnect_count: int = 0
    disconnected_intervals: list[dict[str, Any]] = field(default_factory=list)
    subscription_acknowledged: bool = True
    backfill_attempted: bool = False
    backfill_succeeded: bool = False


@dataclass(frozen=True)
class ReadOnlyBackfillConfig:
    enabled: bool = False
    explicit_read_only_rpc_flag: bool = False
    max_signatures: int = 100
    wallet_signing_enabled: bool = False

    def __post_init__(self) -> None:
        if self.enabled and not self.explicit_read_only_rpc_flag:
            raise ValueError("read-only RPC backfill requires explicit flag")
        if self.max_signatures < 1 or self.max_signatures > 100:
            raise ValueError("max_signatures must be between 1 and 100")
        if self.wallet_signing_enabled:
            raise ValueError("wallet/signing is forbidden in T007 source backfill")


def evaluate_source_gap_health(
    lanes: list[SourceLaneRuntime],
    *,
    required_duration_ratio: float = 0.98,
) -> dict[str, Any]:
    lane_statuses: list[dict[str, Any]] = []
    blocking_reasons: list[str] = []
    unbackfilled_gap_count = 0
    for lane in lanes:
        requested = float(lane.requested_duration_seconds or 0)
        actual = float(lane.actual_duration_seconds or 0)
        ratio = actual / requested if requested > 0 else 0.0
        lane_unbackfilled = 0
        for interval in lane.disconnected_intervals:
            status = str(interval.get("backfill_status") or "")
            if status not in {"succeeded", "covered", "not_needed"}:
                lane_unbackfilled += 1
        if lane_unbackfilled:
            unbackfilled_gap_count += lane_unbackfilled
            if "unbackfilled_source_gap" not in blocking_reasons:
                blocking_reasons.append("unbackfilled_source_gap")
        if ratio < required_duration_ratio:
            blocking_reasons.append(f"{lane.lane}_duration_ratio_below_0_98")
        if not lane.subscription_acknowledged:
            blocking_reasons.append(f"{lane.lane}_subscription_not_acknowledged")
        lane_statuses.append(
            {
                "lane": lane.lane,
                "requested_duration_seconds": requested,
                "actual_duration_seconds": actual,
                "duration_ratio": ratio,
                "reconnect_count": int(lane.reconnect_count),
                "disconnected_interval_count": len(lane.disconnected_intervals),
                "unbackfilled_gap_count": lane_unbackfilled,
                "subscription_acknowledged": bool(lane.subscription_acknowledged),
            }
        )
    return {
        "source_gap_gate_passed": not blocking_reasons,
        "unbackfilled_gap_count": unbackfilled_gap_count,
        "blocking_reasons": blocking_reasons,
        "lane_statuses": lane_statuses,
    }

