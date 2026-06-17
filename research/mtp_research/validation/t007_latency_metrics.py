"""Latency helpers for T007 watcher/readiness payloads."""

from __future__ import annotations

from statistics import median
from typing import Iterable, Mapping, Any

LATENCY_FIELDS = (
    "birth_seen_lag_ms",
    "raw_to_domain_lag_ms",
    "domain_to_identity_lag_ms",
    "curve_resolution_lag_ms",
    "curve_decode_lag_ms",
    "migration_link_lag_ms",
    "quote_observation_lag_ms",
    "db_commit_lag_ms",
)


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return ordered[idx]


def summarize_latency(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, list[float]] = {field: [] for field in LATENCY_FIELDS}
    for row in rows:
        for field in LATENCY_FIELDS:
            try:
                value = row.get(field)
                if value is not None and value != "":
                    buckets[field].append(float(value))
            except (TypeError, ValueError):
                continue
    summary: dict[str, Any] = {}
    for field, values in buckets.items():
        summary[f"{field}_count"] = len(values)
        summary[f"{field}_p50"] = median(values) if values else None
        summary[f"{field}_p95"] = _percentile(values, 95)
        summary[f"{field}_p99"] = _percentile(values, 99)
    return summary


def derive_basic_latency_fields(row: Mapping[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    def f(key: str) -> float | None:
        value = row.get(key)
        try:
            return float(value) if value is not None and value != "" else None
        except (TypeError, ValueError):
            return None
    received = f("source_received_at") or f("received_at")
    block_time = f("block_time")
    raw_inserted = f("raw_inserted_at")
    domain_inserted = f("domain_inserted_at")
    identity_updated = f("identity_updated_at")
    if received is not None and block_time is not None:
        out["birth_seen_lag_ms"] = max(0.0, (received - block_time) * 1000.0)
    if raw_inserted is not None and domain_inserted is not None:
        out["raw_to_domain_lag_ms"] = max(0.0, (domain_inserted - raw_inserted) * 1000.0)
    if domain_inserted is not None and identity_updated is not None:
        out["domain_to_identity_lag_ms"] = max(0.0, (identity_updated - domain_inserted) * 1000.0)
    return out
