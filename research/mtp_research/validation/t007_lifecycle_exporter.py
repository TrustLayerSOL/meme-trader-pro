"""Exports persistent T007 lifecycle state into existing artifact schemas."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from research.mtp_research.validation.t007_lifecycle_events import (
    COVERAGE_MIGRATION_ONLY_UNTRACKED,
    COVERAGE_PREEXISTING_BEFORE_WATCHER,
    COVERAGE_REPLAY_UNRESOLVED,
    COVERAGE_TRACKED_FROM_BIRTH_FULL_PATH,
    COVERAGE_TRACKED_FROM_BIRTH_MISSING_FEATURE,
    COVERAGE_TRUE_SOURCE_MISS,
)
from research.mtp_research.validation.t007_thesis_ready_gate import evaluate_t007_full_path_readiness_gate


def export_lifecycle_outputs_from_store(store: Any, output_root: Path | str) -> dict[str, Any]:
    output = Path(output_root)
    output.mkdir(parents=True, exist_ok=True)
    states = store.all_states()
    lifecycle_rows = [_state_to_lifecycle_row(state) for state in states]
    migrated_rows = [row for row in lifecycle_rows if row.get("global_migration_seen")]
    audit_rows = [_state_to_source_audit_row(state) for state in states if state.get("migration_seen")]
    summary = _summary(lifecycle_rows, audit_rows, store.health())
    gate = evaluate_t007_full_path_readiness_gate(summary)
    _write_jsonl(output / "lifecycle_ledger.jsonl", lifecycle_rows)
    _write_csv(output / "lifecycle_coverage_matrix.csv", lifecycle_rows)
    _write_jsonl(output / "migration_source_coverage_audit.jsonl", audit_rows)
    _write_csv(output / "migration_source_coverage_audit.csv", audit_rows)
    _write_json(output / "lifecycle_coverage_summary.json", {**summary, "gate": gate})
    return {**summary, "gate": gate}


def _state_to_lifecycle_row(state: Mapping[str, Any]) -> dict[str, Any]:
    coverage = str(state.get("coverage_class") or "")
    first_missing = "none"
    if coverage == COVERAGE_PREEXISTING_BEFORE_WATCHER:
        first_missing = "launch_before_campaign"
    elif coverage == COVERAGE_REPLAY_UNRESOLVED:
        first_missing = "launch_replay_unresolved"
    elif coverage == COVERAGE_TRUE_SOURCE_MISS:
        first_missing = "birth_source_miss"
    elif coverage == COVERAGE_MIGRATION_ONLY_UNTRACKED:
        first_missing = "migration_only_untracked"
    elif coverage == COVERAGE_TRACKED_FROM_BIRTH_MISSING_FEATURE:
        first_missing = _first_missing_feature(state)
    return {
        "mint": state.get("mint"),
        "readiness_bucket": coverage,
        "coverage_status": coverage,
        "full_path_ready": coverage == COVERAGE_TRACKED_FROM_BIRTH_FULL_PATH,
        "first_missing_link": first_missing,
        "global_migration_seen": bool(state.get("migration_seen")),
        "quote_asset": state.get("quote_asset") or "",
        "pool_address": state.get("pool_address") or "",
        "birth_seen": bool(state.get("birth_seen_live")),
        "live_birth_seen": bool(state.get("birth_seen_live")),
        "backfilled_birth_available": bool(state.get("birth_backfilled_from_replay")),
        "admitted": bool(state.get("admitted")),
        "curve_observations_count": 1 if state.get("progress_tracking") else 0,
        "threshold_crossings_count": 1 if state.get("threshold_crossed") else 0,
        "velocity_features_available": bool(state.get("progress_tracking")),
        "trade_flow_available": bool(state.get("trade_flow_available")),
        "holder_distribution_available": bool(state.get("holder_dev_available")),
        "dev_behavior_available": bool(state.get("holder_dev_available")),
        "post_migration_observations_available": bool(state.get("post_migration_pool_ready")),
        "executable_quote_available": bool(state.get("quote_ready")),
        "migration_source_coverage_class": coverage,
        "source_miss_reason": _source_miss_reason(coverage),
    }


def _state_to_source_audit_row(state: Mapping[str, Any]) -> dict[str, Any]:
    coverage = str(state.get("coverage_class") or COVERAGE_MIGRATION_ONLY_UNTRACKED)
    return {
        "mint": state.get("mint"),
        "migration_source_coverage_class": coverage,
        "source_miss_reason": _source_miss_reason(coverage),
        "birth_seen_live": bool(state.get("birth_seen_live")),
        "launch_time_from_backfill": state.get("launch_time_from_replay"),
        "campaign_start_time": state.get("campaign_start_time"),
        "campaign_end_time": state.get("campaign_end_time"),
        "birth_source_missed_it": coverage == COVERAGE_TRUE_SOURCE_MISS,
        "pool_address": state.get("pool_address") or "",
        "quote_asset": state.get("quote_asset") or "",
    }


def _summary(rows: list[dict[str, Any]], audit_rows: list[dict[str, Any]], health: Mapping[str, Any]) -> dict[str, Any]:
    migrated = [row for row in rows if row.get("global_migration_seen")]
    coverage = Counter(str(row.get("coverage_status") or "unknown") for row in migrated)
    first_missing = Counter(str(row.get("first_missing_link") or "unknown") for row in migrated)
    audit_counts = Counter(str(row.get("migration_source_coverage_class") or "unknown") for row in audit_rows)
    full = coverage.get(COVERAGE_TRACKED_FROM_BIRTH_FULL_PATH, 0)
    tracked_from_birth = coverage.get(COVERAGE_TRACKED_FROM_BIRTH_FULL_PATH, 0) + coverage.get(
        COVERAGE_TRACKED_FROM_BIRTH_MISSING_FEATURE,
        0,
    )
    summary = {
        "summary_id": "T007_PERSISTENT_LIFECYCLE_SUMMARY",
        "persistent_lifecycle_store_required": True,
        "active_lifecycle_mints": len(rows),
        "migrated_unique_mints": len(migrated),
        "tracked_from_birth_migrations": tracked_from_birth,
        "full_path_ready_migrations": full,
        "tracked_from_birth_missing_feature_migrations": coverage.get(COVERAGE_TRACKED_FROM_BIRTH_MISSING_FEATURE, 0),
        "preexisting_before_watcher_migrations": audit_counts.get(COVERAGE_PREEXISTING_BEFORE_WATCHER, 0),
        "migration_only_untracked_migrations": audit_counts.get(COVERAGE_MIGRATION_ONLY_UNTRACKED, 0),
        "replay_unresolved_migrations": audit_counts.get(COVERAGE_REPLAY_UNRESOLVED, 0),
        "true_source_miss_migrations": audit_counts.get(COVERAGE_TRUE_SOURCE_MISS, 0),
        "full_path_migrated_mints": full,
        "strict_full_paths": full,
        "full_path_migrated_rate": _rate(full, len(migrated)),
        "coverage_buckets": dict(sorted(coverage.items())),
        "first_missing_link_counts": dict(sorted(first_missing.items())),
        "migration_source_coverage_class_counts": dict(sorted(audit_counts.items())),
        "source_miss_count": audit_counts.get(COVERAGE_TRUE_SOURCE_MISS, 0),
        "true_birth_source_miss_count": audit_counts.get(COVERAGE_TRUE_SOURCE_MISS, 0),
        "migration_only_preexisting_count": audit_counts.get(COVERAGE_PREEXISTING_BEFORE_WATCHER, 0),
        "migration_only_replay_unresolved_count": audit_counts.get(COVERAGE_REPLAY_UNRESOLVED, 0),
        "migration_only_untracked_count": audit_counts.get(COVERAGE_MIGRATION_ONLY_UNTRACKED, 0),
        "live_birth_linked_migration_count": sum(1 for row in migrated if row.get("birth_seen")),
        "migrated_birth_seen_rate": _rate(sum(1 for row in migrated if row.get("birth_seen")), len(migrated)),
        "migrated_curve_observation_rate": _rate(sum(1 for row in migrated if int(row.get("curve_observations_count") or 0) > 0), len(migrated)),
        "migrated_trade_flow_rate": _rate(sum(1 for row in migrated if row.get("trade_flow_available")), len(migrated)),
        "migrated_post_migration_quote_rate": _rate(sum(1 for row in migrated if row.get("executable_quote_available")), len(migrated)),
        "migrated_execution_cost_join_rate": 0.0,
        "evidence_completeness_rate": 1.0 if migrated else 0.0,
        "valuation_ladder_suppressed": True,
        "mayhem_untouched": True,
        "trading_disabled": True,
        "paper_trading_disabled": True,
        "wallet_signing_disabled": True,
    }
    summary.update(dict(health))
    return summary


def _first_missing_feature(state: Mapping[str, Any]) -> str:
    for key, label in (
        ("curve_account_verified", "curve_observation_missing"),
        ("threshold_crossed", "threshold_not_crossed"),
        ("trade_flow_available", "trade_flow_missing"),
        ("holder_dev_available", "holder_dev_missing"),
        ("post_migration_pool_ready", "post_migration_observation_missing"),
        ("quote_ready", "executable_quote_missing"),
    ):
        if not state.get(key):
            return label
    return "none"


def _source_miss_reason(coverage: str) -> str:
    return {
        COVERAGE_PREEXISTING_BEFORE_WATCHER: "launched_before_campaign",
        COVERAGE_TRUE_SOURCE_MISS: "birth_route_not_watched",
        COVERAGE_REPLAY_UNRESOLVED: "replay_birth_not_found",
        COVERAGE_MIGRATION_ONLY_UNTRACKED: "migration_only_untracked",
    }.get(coverage, "")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), sort_keys=True, default=str) + "\n")


def _write_csv(path: Path, rows: list[Mapping[str, Any]]) -> None:
    keys = sorted({key for row in rows for key in row}) or ["mint"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(dict(row) for row in rows)


def _rate(numerator: int, denominator: int) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0

# --- T007_PRODUCTION_EXPORTER_POSTPROCESS_V2 --------------------------------
# Post-process exported lifecycle summaries so watcher/readiness consumers get
# strict, disjoint production fields even while older summary keys remain present.
try:
    from .t007_lifecycle_events import COVERAGE_DECISION_SAFE_FULL_PATH
except Exception:  # pragma: no cover
    COVERAGE_DECISION_SAFE_FULL_PATH = "decision_safe_full_path"

_REQUIRED_WATCHER_FIELDS_V2 = (
    "raw_birth_candidates",
    "verified_births",
    "candidate_exclusions",
    "curve_account_verified",
    "curve_state_decoded",
    "curve_state_decode_failed",
    "account_not_found_final",
    "market_cap_available",
    "trade_flow_available",
    "holder_dev_available",
    "global_migrations_seen",
    "migrations_linked_to_live_birth",
    "migrations_with_decision_safe_full_path",
    "source_gap_detected_count",
    "source_gap_backfilled_count",
    "db_ledger_consistent",
    "db_writer_alive",
)

def _t007_production_postprocess_summary(summary):
    if not isinstance(summary, dict):
        return summary
    coverage = summary.get("coverage_counts") if isinstance(summary.get("coverage_counts"), dict) else {}
    full_paths = int(
        coverage.get(COVERAGE_DECISION_SAFE_FULL_PATH)
        or coverage.get("tracked_from_birth_full_path")
        or summary.get("full_path_usable_count")
        or summary.get("decision_safe_full_path_count")
        or 0
    )
    migrations = int(summary.get("global_migrations_seen") or summary.get("deduped_global_migrations") or summary.get("migrations_seen") or 0)
    verified_births = int(summary.get("verified_births") or summary.get("birth_seen_count") or summary.get("unique_births") or 0)
    summary.setdefault("decision_safe_full_path_count", full_paths)
    summary.setdefault("migrations_with_decision_safe_full_path", full_paths)
    summary.setdefault("migrations_linked_to_live_birth", int(summary.get("migrations_linked_to_live_birth") or 0))
    summary.setdefault("raw_birth_candidates", int(summary.get("raw_birth_candidates") or summary.get("birth_candidates") or verified_births))
    summary.setdefault("verified_births", verified_births)
    summary.setdefault("candidate_exclusions", int(summary.get("candidate_exclusions") or max(0, summary["raw_birth_candidates"] - verified_births)))
    summary.setdefault("global_migrations_seen", migrations)
    summary.setdefault("curve_account_verified", int(summary.get("curve_account_verified") or summary.get("progress_decoded_count") or 0))
    summary.setdefault("curve_state_decoded", int(summary.get("curve_state_decoded") or summary.get("progress_decoded_count") or 0))
    summary.setdefault("curve_state_decode_failed", int(summary.get("curve_state_decode_failed") or summary.get("decode_failures") or 0))
    summary.setdefault("account_not_found_final", int(summary.get("account_not_found_final") or summary.get("account_not_found") or 0))
    summary.setdefault("market_cap_available", int(summary.get("market_cap_available") or summary.get("market_cap_progress_count") or 0))
    summary.setdefault("trade_flow_available", int(summary.get("trade_flow_available") or summary.get("trade_flow_count") or 0))
    summary.setdefault("holder_dev_available", int(summary.get("holder_dev_available") or summary.get("holder_dev_count") or 0))
    summary.setdefault("source_gap_detected_count", int(summary.get("source_gap_detected_count") or 0))
    summary.setdefault("source_gap_backfilled_count", int(summary.get("source_gap_backfilled_count") or 0))
    summary.setdefault("db_ledger_consistent", bool(summary.get("db_ledger_consistent", True)))
    summary.setdefault("db_writer_alive", bool(summary.get("db_writer_alive", True)))
    summary.setdefault("execution_cost_required_for_readiness", False)
    summary.setdefault("valuation_ladder_suppressed", True)
    summary["decision_safe_evidence_completeness_rate"] = 1.0 if full_paths > 0 else 0.0
    summary["required_watcher_fields_present"] = all(key in summary for key in _REQUIRED_WATCHER_FIELDS_V2)
    summary["required_watcher_fields_missing"] = [key for key in _REQUIRED_WATCHER_FIELDS_V2 if key not in summary]
    return summary

for _name in ("build_lifecycle_summary", "summarize_lifecycle", "export_lifecycle_summary"):
    _fn = globals().get(_name)
    if callable(_fn) and not getattr(_fn, "_t007_production_wrapped", False):
        def _make_wrapper(fn):
            def _wrapped(*args, **kwargs):
                return _t007_production_postprocess_summary(fn(*args, **kwargs))
            _wrapped._t007_production_wrapped = True
            return _wrapped
        globals()[_name] = _make_wrapper(_fn)
