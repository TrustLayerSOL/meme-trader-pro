"""In-process event bus for Rule Runtime v1 hot-path events."""

from __future__ import annotations

from collections import deque
from typing import Any
import time
import uuid


HOT_PATH_EVENT_TYPES = {
    "birth_seen",
    "fdv_path_update",
    "confirmed_10k_update",
    "confirmed_20k_update",
    "milestone_update",
    "drawdown_update",
    "inactivity_update",
}
BACKGROUND_EVENT_TYPES = {"metadata_update_background"}


class RuleRuntimeEventBus:
    def __init__(self, *, max_queue_size: int = 10_000) -> None:
        self.max_queue_size = max(1, int(max_queue_size))
        self._queue: deque[dict[str, Any]] = deque()
        self._seen_keys: set[str] = set()
        self._metrics = {
            "emitted": 0,
            "deduped": 0,
            "dropped_backpressure": 0,
            "background_skipped": 0,
            "drained": 0,
        }

    def emit(self, event: dict[str, Any], *, block: bool = False) -> bool:
        normalized = normalize_bus_event(event)
        dedupe_key = _dedupe_key(normalized)
        if dedupe_key in self._seen_keys:
            self._metrics["deduped"] += 1
            return False
        if len(self._queue) >= self.max_queue_size:
            if not block:
                self._metrics["dropped_backpressure"] += 1
                return False
            while len(self._queue) >= self.max_queue_size:
                time.sleep(0.001)
        self._seen_keys.add(dedupe_key)
        self._queue.append(normalized)
        self._metrics["emitted"] += 1
        return True

    def drain(self, *, max_events: int | None = None, include_background: bool = False) -> list[dict[str, Any]]:
        limit = len(self._queue) if max_events is None else max(0, int(max_events))
        rows: list[dict[str, Any]] = []
        deferred: deque[dict[str, Any]] = deque()
        while self._queue and len(rows) < limit:
            event = self._queue.popleft()
            if event.get("source_event_type") in BACKGROUND_EVENT_TYPES and not include_background:
                self._metrics["background_skipped"] += 1
                continue
            if event.get("source_event_type") not in HOT_PATH_EVENT_TYPES:
                deferred.append(event)
                continue
            rows.append(event)
        while deferred:
            self._queue.appendleft(deferred.pop())
        self._metrics["drained"] += len(rows)
        return rows

    def metrics(self) -> dict[str, Any]:
        return {**self._metrics, "queue_depth": len(self._queue), "max_queue_size": self.max_queue_size}


def normalize_bus_event(event: dict[str, Any]) -> dict[str, Any]:
    payload = dict(event)
    observed = _num(payload.get("observed_at") or payload.get("timestamp") or payload.get("event_observed_at")) or time.time()
    monotonic_observed = _num(payload.get("monotonic_observed_at")) or time.monotonic()
    mint = str(payload.get("mint") or "")
    fdv = _event_fdv_proxy(payload)
    milestone_fdv = _event_fdv_usd(payload)
    event_type = str(payload.get("source_event_type") or "fdv_path_update")
    payload["event_id"] = str(payload.get("event_id") or f"{mint}-{observed}-{fdv}-{uuid.uuid4().hex[:8]}")
    payload["mint"] = mint
    payload["observed_at"] = float(observed)
    payload["timestamp"] = float(_num(payload.get("timestamp")) or observed)
    payload["event_observed_at"] = float(_num(payload.get("event_observed_at")) or observed)
    payload["monotonic_observed_at"] = float(monotonic_observed)
    payload["bus_emit_monotonic_at"] = time.monotonic()
    payload["bus_emit_at"] = time.time()
    payload["source_adapter"] = str(payload.get("source_adapter") or payload.get("data_source") or "rule_runtime_live_bus")
    payload["data_source"] = str(payload.get("data_source") or payload.get("source_adapter") or "rule_runtime_live_bus")
    payload["source_event_type"] = event_type
    payload["fdv_proxy"] = fdv
    payload["event_count"] = int(_num(payload.get("event_count")) or 0)
    payload["buy_count"] = int(_num(payload.get("buy_count")) or 0)
    payload["sell_count"] = int(_num(payload.get("sell_count")) or 0)
    payload["active_wallet_count"] = int(_num(payload.get("active_wallet_count") or payload.get("active_wallets")) or 0)
    payload["path_evidence_count"] = int(_num(payload.get("path_evidence_count")) or 1)
    payload["source_provenance"] = str(payload.get("source_provenance") or payload.get("source_adapter") or "rule_runtime_live_bus")
    payload["milestone_provenance"] = payload.get("milestone_provenance") or payload["source_provenance"]
    for level, threshold in [
        ("10k", 10_000),
        ("15k", 15_000),
        ("20k", 20_000),
        ("50k", 50_000),
        ("100k", 100_000),
        ("500k", 500_000),
        ("1m", 1_000_000),
    ]:
        key = f"raw_crossed_{level}"
        if payload.get(key) is None and milestone_fdv is not None:
            payload[key] = milestone_fdv >= threshold
    return payload


def _event_fdv_proxy(payload: dict[str, Any]) -> float | None:
    fdv_usd = _num(payload.get("fdv_usd") or payload.get("fdv_proxy_usd"))
    if fdv_usd is not None:
        payload["fdv_units"] = "usd"
        payload["fdv_usd"] = fdv_usd
        return fdv_usd
    return _num(payload.get("fdv_proxy"))


def _event_fdv_usd(payload: dict[str, Any]) -> float | None:
    fdv_usd = _num(payload.get("fdv_usd") or payload.get("fdv_proxy_usd"))
    if fdv_usd is not None:
        return fdv_usd
    units = str(payload.get("fdv_units") or "").strip().lower()
    if units in {"sol", "quote", "fdv_sol", "fdv_quote"}:
        return None
    return _num(payload.get("fdv_proxy"))


def _dedupe_key(event: dict[str, Any]) -> str:
    if event.get("event_id"):
        return str(event["event_id"])
    return "|".join(
        [
            str(event.get("mint") or ""),
            str(event.get("timestamp") or ""),
            str(event.get("source_adapter") or ""),
            str(event.get("source_event_type") or ""),
        ]
    )


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
