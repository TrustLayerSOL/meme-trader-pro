"""Discovery-source bias audit for launch-regime lifecycle artifacts."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.launch_regime.models import LaunchRegimeCandidate
from research.mtp_research.launch_regime.store import JsonlArtifactStore
from research.mtp_research.validation.launch_timestamp_confidence import (
    classify_launch_timestamp_source,
    is_verified_launch_timestamp,
)


DEFAULT_REGISTRY_PATH = Path("data/normalized/candidate_registry.jsonl")
DEFAULT_LIFECYCLE_LAUNCHES_PATH = Path("data/normalized/launch_regime/launch_regime_candidates.jsonl")
DEFAULT_REPORT_DIR = Path("data/backtests/diagnostics/reports")


SOURCE_BUCKETS = {
    "dexscreener_real",
    "dexscreener",
    "jupiter_recent",
    "pumpfun",
    "pumpswap",
    "raydium",
    "event_inferred",
    "manual",
    "mock",
    "unknown",
}


def run_discovery_source_bias_audit(
    registry_path: Path | str = DEFAULT_REGISTRY_PATH,
    lifecycle_launches_path: Path | str = DEFAULT_LIFECYCLE_LAUNCHES_PATH,
    output_dir: Path | str = DEFAULT_REPORT_DIR,
) -> dict[str, Any]:
    registry_path = Path(registry_path)
    lifecycle_launches_path = Path(lifecycle_launches_path)
    output_dir = Path(output_dir)

    candidates = CandidateRegistry(registry_path).load_all()
    launches = JsonlArtifactStore(lifecycle_launches_path).load_all(LaunchRegimeCandidate.from_dict)

    registry_source_counts = Counter(_source_bucket(candidate.source, candidate.metadata_json) for candidate in candidates)
    lifecycle_source_counts = Counter(_source_bucket(launch.source, launch.metadata_json) for launch in launches)
    venue_counts = Counter(launch.venue or "unknown" for launch in launches)
    launch_regime_counts = Counter(launch.launch_regime or "unknown" for launch in launches)
    pool_address_counts = Counter("with_pool_address" if launch.pool_address else "missing_pool_address" for launch in launches)

    timestamp_source_counts: Counter[str] = Counter()
    timestamp_confidence_counts: Counter[str] = Counter()
    for launch in launches:
        source = classify_launch_timestamp_source(launch.to_dict())
        timestamp_source_counts[source] += 1
        timestamp_confidence_counts["verified" if is_verified_launch_timestamp(source) else "inferred"] += 1

    warning_flags = _warning_flags(registry_source_counts, lifecycle_source_counts, len(launches), timestamp_confidence_counts)
    report = {
        "registry_candidate_count": len(candidates),
        "lifecycle_launch_count": len(launches),
        "registry_source_counts": dict(sorted(registry_source_counts.items())),
        "lifecycle_source_counts": dict(sorted(lifecycle_source_counts.items())),
        "venue_counts": dict(sorted(venue_counts.items())),
        "launch_regime_counts": dict(sorted(launch_regime_counts.items())),
        "pool_address_counts": dict(sorted(pool_address_counts.items())),
        "launch_timestamp_source_counts": dict(sorted(timestamp_source_counts.items())),
        "launch_timestamp_confidence_counts": dict(sorted(timestamp_confidence_counts.items())),
        "warning_flags": warning_flags,
        "recommended_next_source": "program_signature_discovery",
        "network_calls": 0,
    }
    _write_reports(report, output_dir)
    return report


def _source_bucket(source: str | None, metadata_json: dict[str, Any] | None = None) -> str:
    text = (source or "").lower()
    metadata = metadata_json or {}
    discovered_sources = [str(item).lower() for item in metadata.get("discovered_sources", [])]
    all_sources = [text, *discovered_sources]
    if metadata.get("is_mock") or "mock" in all_sources:
        return "mock"
    if any(item in {"normalized_event_first_seen", "event_inferred"} for item in all_sources):
        return "event_inferred"
    if any("dexscreener_real" == item for item in all_sources):
        return "dexscreener_real"
    if any("dexscreener" in item for item in all_sources):
        return "dexscreener"
    if any("jupiter" in item for item in all_sources):
        return "jupiter_recent"
    if any("pumpfun" in item or "pump.fun" in item or item == "pump" for item in all_sources):
        return "pumpfun"
    if any("pumpswap" in item for item in all_sources):
        return "pumpswap"
    if any("raydium" in item for item in all_sources):
        return "raydium"
    if any("manual" in item for item in all_sources):
        return "manual"
    return "unknown"


def _warning_flags(
    registry_counts: Counter[str],
    lifecycle_counts: Counter[str],
    lifecycle_count: int,
    timestamp_confidence_counts: Counter[str],
) -> list[str]:
    warnings: list[str] = []
    dexscreener_visible = sum(
        lifecycle_counts.get(source, 0)
        for source in ("dexscreener_real", "dexscreener")
    )
    if lifecycle_count and dexscreener_visible / lifecycle_count >= 0.6:
        warnings.append("source_concentration_dexscreener_visible")
        warnings.append("dexscreener_survivorship_risk")
    registry_dex = sum(registry_counts.get(source, 0) for source in ("dexscreener_real", "dexscreener"))
    if registry_counts and registry_dex / sum(registry_counts.values()) >= 0.6 and "dexscreener_survivorship_risk" not in warnings:
        warnings.append("dexscreener_survivorship_risk")
    if timestamp_confidence_counts.get("verified", 0) == 0 and lifecycle_count:
        warnings.append("no_verified_launch_timestamps")
    if lifecycle_count == 0:
        warnings.append("no_lifecycle_launches_found")
    return warnings


def _write_reports(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "discovery_source_bias_audit.json"
    md_path = output_dir / "discovery_source_bias_audit.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Discovery Source Bias Audit",
        "",
        f"- registry_candidate_count: {report['registry_candidate_count']}",
        f"- lifecycle_launch_count: {report['lifecycle_launch_count']}",
        f"- recommended_next_source: {report['recommended_next_source']}",
        f"- warning_flags: {report['warning_flags']}",
        "",
        "## Registry Sources",
        _format_counts(report["registry_source_counts"]),
        "",
        "## Lifecycle Sources",
        _format_counts(report["lifecycle_source_counts"]),
        "",
        "## Launch Timestamp Confidence",
        _format_counts(report["launch_timestamp_confidence_counts"]),
        "",
        "This audit is research-only. It does not produce trade signals, thesis promotions, or validation claims.",
        "",
    ]
    return "\n".join(lines)


def _format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "- none"
    return "\n".join(f"- {key}: {value}" for key, value in sorted(counts.items()))
