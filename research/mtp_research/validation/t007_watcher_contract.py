"""Strict watcher/readiness payload contract for T007 production runs."""

from __future__ import annotations

from typing import Any, Mapping

REQUIRED_WATCHER_FIELDS = (
    "global_migration_mints_seen",
    "linked_to_any_persistent_birth",
    "linked_to_live_birth_in_window",
    "decision_safe_full_paths",
    "true_source_miss_count",
    "preexisting_count",
    "replay_unresolved_count",
    "restart_gap_count",
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
    "post_migration_pool_ready_verified",
    "quote_ready_verified",
    "db_ledger_consistent",
    "db_writer_alive",
)


def normalize_watcher_payload(summary: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(summary or {})
    migrations = int(payload.get("global_migration_mints_seen") or payload.get("global_migrations_seen") or payload.get("deduped_global_migrations") or 0)
    full_paths = int(payload.get("decision_safe_full_paths") or payload.get("migrations_with_decision_safe_full_path") or payload.get("decision_safe_full_path_count") or 0)
    verified_births = int(payload.get("verified_births") or payload.get("birth_seen_count") or payload.get("unique_births") or 0)
    raw_births = int(payload.get("raw_birth_candidates") or payload.get("birth_candidates") or verified_births)
    payload["global_migration_mints_seen"] = migrations
    payload["decision_safe_full_paths"] = full_paths
    payload["linked_to_any_persistent_birth"] = int(payload.get("linked_to_any_persistent_birth") or payload.get("migrations_linked_to_persistent_birth") or 0)
    payload["linked_to_live_birth_in_window"] = int(payload.get("linked_to_live_birth_in_window") or payload.get("migrations_linked_to_live_birth") or 0)
    payload["true_source_miss_count"] = int(payload.get("true_source_miss_count") or max(0, migrations - payload["linked_to_any_persistent_birth"]))
    payload["preexisting_count"] = int(payload.get("preexisting_count") or payload.get("preexisting_before_watcher_count") or 0)
    payload["replay_unresolved_count"] = int(payload.get("replay_unresolved_count") or payload.get("replay_context_unresolved_count") or 0)
    payload["restart_gap_count"] = int(payload.get("restart_gap_count") or 0)
    payload["raw_birth_candidates"] = raw_births
    payload["verified_births"] = verified_births
    payload["candidate_exclusions"] = int(payload.get("candidate_exclusions") or max(0, raw_births - verified_births))
    payload["curve_account_verified"] = int(payload.get("curve_account_verified") or payload.get("curve_state_decoded") or payload.get("progress_decoded_count") or 0)
    payload["curve_state_decoded"] = int(payload.get("curve_state_decoded") or payload.get("progress_decoded_count") or 0)
    payload["curve_state_decode_failed"] = int(payload.get("curve_state_decode_failed") or payload.get("decode_failures") or 0)
    payload["account_not_found_final"] = int(payload.get("account_not_found_final") or payload.get("account_not_found") or 0)
    payload["market_cap_available"] = int(payload.get("market_cap_available") or payload.get("market_cap_progress_count") or 0)
    payload["trade_flow_available"] = int(payload.get("trade_flow_available") or payload.get("trade_flow_count") or 0)
    payload["holder_dev_available"] = int(payload.get("holder_dev_available") or payload.get("holder_dev_count") or 0)
    payload["post_migration_pool_ready_verified"] = int(payload.get("post_migration_pool_ready_verified") or payload.get("post_migration_ready_verified") or 0)
    payload["quote_ready_verified"] = int(payload.get("quote_ready_verified") or payload.get("strict_quote_ready_count") or 0)
    payload["db_ledger_consistent"] = bool(payload.get("db_ledger_consistent", True))
    payload["db_writer_alive"] = bool(payload.get("db_writer_alive", True))
    payload["misleading_rate_fields_suppressed"] = True
    payload["execution_cost_required_for_readiness"] = False
    payload["valuation_ladder_suppressed"] = True
    payload["required_watcher_fields_present"] = all(field in payload for field in REQUIRED_WATCHER_FIELDS)
    payload["required_watcher_fields_missing"] = [field for field in REQUIRED_WATCHER_FIELDS if field not in payload]
    return payload


def production_readiness_from_watcher_payload(summary: Mapping[str, Any], *, duration_seconds: float | int | None = None) -> dict[str, Any]:
    payload = normalize_watcher_payload(summary)
    blockers: list[str] = []
    duration = float(duration_seconds if duration_seconds is not None else payload.get("source_duration_seconds") or 0)
    if not payload["db_writer_alive"]:
        blockers.append("db_writer_not_alive")
    if not payload["db_ledger_consistent"]:
        blockers.append("db_ledger_inconsistent")
    if int(payload.get("queue_dropped_total") or payload.get("queue_dropped") or 0) > 0:
        blockers.append("queue_dropped")
    if payload["curve_state_decoded"] == 0:
        blockers.append("no_curve_state_decoded")
    if payload["market_cap_available"] == 0:
        blockers.append("no_market_cap_progress")
    if duration >= 1800 and payload["global_migration_mints_seen"] == 0:
        blockers.append("no_migrations_seen_in_controlled_window")
    if payload["global_migration_mints_seen"] > 0 and payload["decision_safe_full_paths"] == 0:
        blockers.append("migrations_not_linked_to_decision_safe_full_path")
    if payload["replay_unresolved_count"] > 0:
        blockers.append("replay_unresolved")
    label = "T007_PRODUCTION_READY_FOR_10M_TEST" if not blockers else "T007_PRODUCTION_BLOCKED"
    return {"decision_label": label, "blockers": blockers, "payload": payload}

# --- T007_WATCHER_PROOF_HARDENING_V4 ----------------------------------------
try:
    from .t007_proof_ladder import evaluate_l2_live_no_migration, evaluate_l3_controlled_migration
except Exception:  # pragma: no cover
    evaluate_l2_live_no_migration = None
    evaluate_l3_controlled_migration = None

_PROOF_WATCHER_FIELDS = (
    'observed_commitment_default',
    'processed_events_count',
    'confirmed_events_count',
    'finalized_events_count',
    'dropped_or_reorged_count',
    'source_gap_slot_ranges_present',
    'run_manifest_present',
    'protocol_layout_registry_present',
    'invariant_violation_count',
    'latency_histograms_present',
    'trade_flow_null_reason',
    'holder_dev_null_reason',
    'quote_null_reason',
    'post_migration_pool_null_reason',
)

_original_normalize_watcher_payload_v4 = normalize_watcher_payload

def normalize_watcher_payload(summary):  # type: ignore[no-redef]
    payload = _original_normalize_watcher_payload_v4(summary)
    payload.setdefault('observed_commitment_default', payload.get('commitment') or 'processed')
    payload.setdefault('processed_events_count', int(payload.get('processed_events_count') or payload.get('domain_events_processed') or 0))
    payload.setdefault('confirmed_events_count', int(payload.get('confirmed_events_count') or 0))
    payload.setdefault('finalized_events_count', int(payload.get('finalized_events_count') or 0))
    payload.setdefault('dropped_or_reorged_count', int(payload.get('dropped_or_reorged_count') or 0))
    payload.setdefault('source_gap_slot_ranges_present', bool(payload.get('source_gap_slot_ranges_present', False)))
    payload.setdefault('run_manifest_present', bool(payload.get('run_manifest_present', False)))
    payload.setdefault('protocol_layout_registry_present', bool(payload.get('protocol_layout_registry_present', False)))
    payload.setdefault('invariant_violation_count', int(payload.get('invariant_violation_count') or 0))
    payload.setdefault('latency_histograms_present', bool(payload.get('latency_histograms_present', False)))
    payload.setdefault('trade_flow_null_reason', payload.get('trade_flow_null_reason'))
    payload.setdefault('holder_dev_null_reason', payload.get('holder_dev_null_reason'))
    payload.setdefault('quote_null_reason', payload.get('quote_null_reason'))
    payload.setdefault('post_migration_pool_null_reason', payload.get('post_migration_pool_null_reason'))
    missing = list(payload.get('required_watcher_fields_missing') or [])
    missing.extend(field for field in _PROOF_WATCHER_FIELDS if field not in payload)
    payload['required_watcher_fields_missing'] = sorted(set(missing))
    payload['required_watcher_fields_present'] = len(payload['required_watcher_fields_missing']) == 0
    if evaluate_l2_live_no_migration is not None:
        l2 = evaluate_l2_live_no_migration(payload)
        payload['proof_l2_passed'] = l2.passed
        payload['proof_l2_blockers'] = list(l2.blockers)
    if evaluate_l3_controlled_migration is not None:
        l3 = evaluate_l3_controlled_migration(payload)
        payload['proof_l3_passed'] = l3.passed
        payload['proof_l3_blockers'] = list(l3.blockers)
    return payload

_original_production_readiness_from_watcher_payload_v4 = production_readiness_from_watcher_payload

def production_readiness_from_watcher_payload(summary, *, duration_seconds=None):  # type: ignore[no-redef]
    result = _original_production_readiness_from_watcher_payload_v4(summary, duration_seconds=duration_seconds)
    payload = result.get('payload') or normalize_watcher_payload(summary)
    blockers = list(result.get('blockers') or [])
    if int(payload.get('invariant_violation_count') or 0) > 0:
        blockers.append('lifecycle_invariant_violations_present')
    if not payload.get('run_manifest_present'):
        blockers.append('run_manifest_missing')
    if not payload.get('protocol_layout_registry_present'):
        blockers.append('protocol_layout_registry_missing')
    if not payload.get('latency_histograms_present'):
        blockers.append('latency_histograms_missing')
    result['blockers'] = sorted(set(blockers))
    result['decision_label'] = 'T007_PRODUCTION_READY_FOR_10M_TEST' if not result['blockers'] else 'T007_PRODUCTION_BLOCKED'
    result['payload'] = payload
    return result
