"""Source-health model for T007 production lifecycle collection."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Any

LANE_HEALTHY = "healthy"
LANE_CONNECTING = "connecting"
LANE_STALLED = "stalled"
LANE_DISABLED = "disabled"
LANE_DEGRADED = "degraded"

@dataclass
class LaneHealth:
    name: str
    required: bool = True
    status: str = LANE_CONNECTING
    connected_at: float | None = None
    last_message_at: float | None = None
    last_event_at: float | None = None
    messages: int = 0
    decoded_events: int = 0
    queue_high_water: int = 0
    queue_dropped: int = 0
    reconnects: int = 0
    websocket_disconnects: int = 0
    rpc_failures: int = 0
    http_429: int = 0
    timeouts: int = 0
    decode_failures: int = 0
    source_gaps: int = 0
    keepalive_misses: int = 0
    reason: str | None = None

    def mark_connected(self, now: float | None = None) -> None:
        ts = now or time()
        self.connected_at = self.connected_at or ts
        self.last_message_at = ts
        self.status = LANE_HEALTHY
        self.reason = None

    def record_message(self, *, decoded: bool = False, now: float | None = None) -> None:
        ts = now or time()
        self.messages += 1
        self.last_message_at = ts
        if decoded:
            self.decoded_events += 1
            self.last_event_at = ts
        if self.status in {LANE_CONNECTING, LANE_STALLED, LANE_DEGRADED}:
            self.status = LANE_HEALTHY
            self.reason = None

    def record_queue(self, *, size: int | None = None, dropped: int = 0) -> None:
        if size is not None and size > self.queue_high_water:
            self.queue_high_water = int(size)
        if dropped:
            self.queue_dropped += int(dropped)
            self.status = LANE_DEGRADED
            self.reason = "queue_dropped"

    def record_rpc_failure(self, *, status: int | None = None, timeout: bool = False) -> None:
        if status == 429:
            self.http_429 += 1
        elif timeout:
            self.timeouts += 1
        else:
            self.rpc_failures += 1
        self.status = LANE_DEGRADED
        self.reason = "rpc_or_http_failure"

    def mark_stalled(self, reason: str) -> None:
        self.status = LANE_STALLED
        self.reason = reason
        self.source_gaps += 1

    def ready(self) -> bool:
        if not self.required:
            return True
        return self.status == LANE_HEALTHY and self.queue_dropped == 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "required": self.required,
            "status": self.status,
            "connected_at": self.connected_at,
            "last_message_at": self.last_message_at,
            "last_event_at": self.last_event_at,
            "messages": self.messages,
            "decoded_events": self.decoded_events,
            "queue_high_water": self.queue_high_water,
            "queue_dropped": self.queue_dropped,
            "reconnects": self.reconnects,
            "websocket_disconnects": self.websocket_disconnects,
            "rpc_failures": self.rpc_failures,
            "http_429": self.http_429,
            "timeouts": self.timeouts,
            "decode_failures": self.decode_failures,
            "source_gaps": self.source_gaps,
            "keepalive_misses": self.keepalive_misses,
            "reason": self.reason,
            "ready": self.ready(),
        }

@dataclass
class T007SourceHealth:
    lanes: dict[str, LaneHealth] = field(default_factory=dict)

    @classmethod
    def default(cls) -> "T007SourceHealth":
        health = cls()
        for lane in (
            "pump_transaction_subscribe",
            "pump_logs_sentinel",
            "curve_account_subscribe",
            "pumpswap_pool_program_subscribe",
            "post_migration_pool_state",
            "bounded_readonly_replay",
        ):
            health.ensure_lane(lane, required=lane != "bounded_readonly_replay")
        return health

    def ensure_lane(self, name: str, *, required: bool = True) -> LaneHealth:
        lane = self.lanes.get(name)
        if lane is None:
            lane = LaneHealth(name=name, required=required)
            self.lanes[name] = lane
        return lane

    def ready(self) -> bool:
        return all(lane.ready() for lane in self.lanes.values())

    def blocking_reasons(self) -> list[str]:
        reasons: list[str] = []
        for lane in self.lanes.values():
            if lane.required and not lane.ready():
                reasons.append(f"{lane.name}:{lane.status}:{lane.reason or 'not_ready'}")
        return reasons

    def totals(self) -> dict[str, int]:
        return {
            "queue_dropped_total": sum(l.queue_dropped for l in self.lanes.values()),
            "queue_high_water_max": max((l.queue_high_water for l in self.lanes.values()), default=0),
            "rpc_failures_total": sum(l.rpc_failures for l in self.lanes.values()),
            "http_429_total": sum(l.http_429 for l in self.lanes.values()),
            "timeouts_total": sum(l.timeouts for l in self.lanes.values()),
            "reconnects_total": sum(l.reconnects for l in self.lanes.values()),
            "websocket_disconnects_total": sum(l.websocket_disconnects for l in self.lanes.values()),
            "source_gaps_total": sum(l.source_gaps for l in self.lanes.values()),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_health_ready": self.ready(),
            "source_health_blocking_reasons": self.blocking_reasons(),
            "lanes": {name: lane.as_dict() for name, lane in sorted(self.lanes.items())},
            **self.totals(),
        }
