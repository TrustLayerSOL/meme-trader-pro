from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def evaluate_t007_lifecycle_readiness_v2(summary: Mapping[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(summary or {})
    level_a = _int(payload.get("level_a_migration_count"))
    pool_ready = _int(payload.get("pool_state_ready_count"))
    quote_ready = _int(payload.get("quote_ready_count"))
    trade_ready = _int(payload.get("trade_data_ready_count"))
    unbackfilled = _int(payload.get("unbackfilled_gap_count"))
    source_gap_passed = _bool(payload.get("source_gap_gate_passed"), True)
    counter_match = _bool(payload.get("summary_raw_counter_match"), True)
    decoder_schema_ok = _bool(payload.get("decoder_schema_ok"), True)
    watcher_schema_ok = _bool(payload.get("watcher_schema_ok"), True)
    valuation_suppressed = _bool(payload.get("valuation_ladder_suppressed"), True)
    mayhem_untouched = _bool(payload.get("mayhem_untouched"), True)
    trading_disabled = _bool(payload.get("trading_disabled"), True)
    paper_disabled = _bool(payload.get("paper_trading_disabled"), True)
    wallet_disabled = _bool(payload.get("wallet_signing_disabled"), True)
    queue_drops = _int(payload.get("queue_drops") or payload.get("queue_dropped"))
    rpc_failures = _int(payload.get("rpc_failures") or payload.get("rpc_failure_count"))
    http_429 = _int(payload.get("http_429_count"))
    thin_probe_queue_drops = _int(payload.get("thin_probe_queue_drops") or payload.get("thin_queue_drops"))
    global_lane_required = _bool(payload.get("global_migration_lane_required"), True)
    global_lane_enabled = _bool(payload.get("global_migration_lane_enabled"), False)
    dual_lane_reconciliation_enabled = _bool(payload.get("dual_lane_reconciliation_enabled"), False)
    dual_lane_eligible = _int(payload.get("dual_lane_eligible_live_decision_count") or payload.get("decision_time_evidence_complete_count"))
    tracked_lookup_enabled = _bool(payload.get("tracked_mint_migration_lookup_enabled"), False)
    tracked_lookup_passed = _bool(payload.get("tracked_mint_lookup_gate_passed"), False)
    tracked_total = _int(payload.get("tracked_mints_total"))
    graduation_candidates = _int(payload.get("graduation_candidates_total"))
    lookup_terminal = _int(payload.get("migration_lookup_terminal_count"))
    lookup_cap_exhausted = _int(payload.get("migration_lookup_cap_exhausted_count"))
    pool_binding_ambiguous = _int(payload.get("pool_binding_ambiguous_count"))
    blocking: list[str] = []
    coverage_warnings: list[str] = []
    if not valuation_suppressed:
        blocking.append("valuation_ladder_not_suppressed")
    if not mayhem_untouched:
        blocking.append("mayhem_not_untouched")
    if not trading_disabled:
        blocking.append("trading_not_disabled")
    if not paper_disabled:
        blocking.append("paper_trading_not_disabled")
    if not wallet_disabled:
        blocking.append("wallet_signing_not_disabled")
    if not counter_match:
        blocking.append("summary_raw_counter_mismatch")
    if not decoder_schema_ok:
        blocking.append("decoder_schema_not_ok")
    if not watcher_schema_ok:
        blocking.append("watcher_schema_not_ok")
    if global_lane_required and not global_lane_enabled:
        blocking.append("global_pumpswap_migration_lane_disabled")
    if not dual_lane_reconciliation_enabled:
        blocking.append("dual_lane_reconciliation_missing")
    if tracked_lookup_enabled:
        if tracked_total <= 0:
            blocking.append("tracked_mints_total_zero")
        if not tracked_lookup_passed:
            blocking.append("tracked_mint_lookup_gate_failed")
        if lookup_cap_exhausted > 0:
            blocking.append("tracked_mint_lookup_cap_exhausted")
        if pool_binding_ambiguous > 0:
            blocking.append("tracked_pool_binding_ambiguous")
    elif level_a <= 0:
        blocking.append("level_a_migration_count_zero")
    if level_a > 0 and pool_ready < level_a:
        blocking.append("pool_state_ready_below_level_a_migrations")
    source_gap_reclassifiable = tracked_lookup_enabled and tracked_lookup_passed and tracked_total > 0 and lookup_terminal >= tracked_total
    if not source_gap_passed:
        if source_gap_reclassifiable:
            coverage_warnings.append("source_gap_reclassified_as_tracked_coverage_warning")
        blocking.append("source_gap_gate_failed")
    if unbackfilled > 0:
        if source_gap_reclassifiable:
            if "source_gap_reclassified_as_tracked_coverage_warning" not in coverage_warnings:
                coverage_warnings.append("source_gap_reclassified_as_tracked_coverage_warning")
        blocking.append("unbackfilled_gap_count_nonzero")
    if queue_drops > 0:
        blocking.append("queue_drops_nonzero")
    if thin_probe_queue_drops > 0:
        blocking.append("thin_probe_queue_drops_nonzero")
    if rpc_failures > 0:
        blocking.append("rpc_failures_nonzero")
    if http_429 > 0:
        blocking.append("http_429_nonzero")
    if level_a > 0 and pool_ready >= level_a and dual_lane_eligible <= 0:
        blocking.append("dual_lane_eligible_live_decision_count_zero")
    safety_ok = valuation_suppressed and mayhem_untouched and trading_disabled and paper_disabled and wallet_disabled
    can_run_10m = safety_ok and decoder_schema_ok and watcher_schema_ok
    if tracked_lookup_enabled:
        can_run_60m = can_run_10m and not blocking and graduation_candidates > 0 and lookup_terminal >= graduation_candidates and level_a > 0 and pool_ready >= level_a and dual_lane_eligible > 0
    else:
        can_run_60m = can_run_10m and not blocking and level_a > 0 and pool_ready >= level_a and dual_lane_eligible > 0
    valid_60m = _bool(payload.get("valid_60m_thesis_scan_passed"), False)
    can_run_2h = can_run_60m and valid_60m
    if "decoder_schema_not_ok" in blocking:
        decision = "T007_DECODER_SCHEMA_BROKEN"
    elif "watcher_schema_not_ok" in blocking:
        decision = "T007_WATCHER_SCHEMA_BROKEN"
    elif "global_pumpswap_migration_lane_disabled" in blocking:
        decision = "T007_GLOBAL_MIGRATION_LANE_DISABLED"
    elif "dual_lane_reconciliation_missing" in blocking:
        decision = "T007_DUAL_LANE_RECONCILIATION_MISSING"
    elif "source_gap_gate_failed" in blocking or "unbackfilled_gap_count_nonzero" in blocking:
        decision = "T007_SOURCE_GAP_BACKFILL_BROKEN"
    elif "thin_probe_queue_drops_nonzero" in blocking:
        decision = "T007_THIN_PROBE_CAPACITY_BROKEN"
    elif tracked_lookup_enabled and "tracked_mint_lookup_gate_failed" in blocking:
        decision = "T007_TRACKED_MINT_MIGRATION_LOOKUP_BROKEN"
    elif tracked_lookup_enabled and graduation_candidates <= 0:
        decision = "T007_TRACKED_MINT_PIPELINE_READY_NO_GRADUATION_VOLUME"
    elif tracked_lookup_enabled and level_a <= 0:
        decision = "T007_TRACKED_MINT_LOOKUP_READY_NO_LEVEL_A_VOLUME"
    elif "level_a_migration_count_zero" in blocking:
        decision = "T007_LEVEL_A_MIGRATION_SOURCE_STILL_BROKEN"
    elif "dual_lane_eligible_live_decision_count_zero" in blocking:
        decision = "T007_DUAL_LANE_READY_NO_DECISION_ELIGIBLE_VOLUME"
    elif can_run_60m and tracked_lookup_enabled:
        decision = "T007_DUAL_LANE_TRACKED_MINT_LEVEL_A_PROOF_READY"
    elif can_run_60m:
        decision = "T007_DUAL_LANE_LEVEL_A_PROOF_READY"
    else:
        decision = "T007_NOT_READY_FOR_LONG_SCAN"
    full_exit_allowed = can_run_60m and quote_ready >= level_a and trade_ready >= level_a and str(payload.get("fee_model_confidence") or "").lower() in {"medium", "high"}
    return {
        "gate_id": "T007_LEVEL_A_PUMPSWAP_MIGRATION_WATCHER_V2",
        "decision_label": decision,
        "can_run_10m_feature_proof": can_run_10m,
        "can_run_60m_thesis_scan": can_run_60m,
        "can_run_2h_plus_scan": can_run_2h,
        "full_post_migration_exit_thesis_allowed": full_exit_allowed,
        "blocking_reasons": blocking,
        "coverage_warnings": coverage_warnings,
        "level_a_migration_count": level_a,
        "pool_state_ready_count": pool_ready,
        "quote_ready_count": quote_ready,
        "trade_data_ready_count": trade_ready,
        "source_gap_gate_passed": source_gap_passed,
        "unbackfilled_gap_count": unbackfilled,
        "summary_raw_counter_match": counter_match,
        "valuation_ladder_suppressed": valuation_suppressed,
        "trading_disabled": trading_disabled,
        "paper_trading_disabled": paper_disabled,
        "wallet_signing_disabled": wallet_disabled,
        "mayhem_untouched": mayhem_untouched,
        "thin_probe_queue_drops": thin_probe_queue_drops,
        "tracked_mint_migration_lookup_enabled": tracked_lookup_enabled,
        "tracked_mint_lookup_gate_passed": tracked_lookup_passed,
        "tracked_mints_total": tracked_total,
        "graduation_candidates_total": graduation_candidates,
        "migration_lookup_terminal_count": lookup_terminal,
        "global_migration_lane_required": global_lane_required,
        "global_migration_lane_enabled": global_lane_enabled,
        "dual_lane_reconciliation_enabled": dual_lane_reconciliation_enabled,
        "dual_lane_eligible_live_decision_count": dual_lane_eligible,
        "global_pumpswap_completeness_required": True,
        "edge_claim_allowed": False,
    }


def write_t007_lifecycle_readiness_gate_v2(output_root: str | Path, summary: Mapping[str, Any] | None = None) -> dict[str, Any]:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    gate = evaluate_t007_lifecycle_readiness_v2(summary)
    (root / "thesis_ready_gate_v2.json").write_text(json.dumps(gate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return gate


def _int(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "enabled"}
