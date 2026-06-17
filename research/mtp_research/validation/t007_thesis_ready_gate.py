from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


DEFAULT_REQUIRED_FULL_PATH_MIGRATED_RATE = 0.80
DEFAULT_REQUIRED_BIRTH_SEEN_RATE = 0.90
DEFAULT_REQUIRED_CURVE_OBSERVATION_RATE = 0.80
DEFAULT_REQUIRED_TRADE_FLOW_RATE = 0.80
DEFAULT_REQUIRED_POST_MIGRATION_QUOTE_RATE = 0.80
DEFAULT_REQUIRED_EXECUTION_COST_JOIN_RATE = 0.95
DEFAULT_REQUIRED_EVIDENCE_COMPLETENESS_RATE = 0.99


def _int(value: Any, default: int = 0) -> int:
    if value in (None, ""):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "enabled"}


def _rate(numerator: int, denominator: int) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def _append_if(condition: bool, reasons: list[str], reason: str) -> None:
    if condition:
        reasons.append(reason)


def evaluate_t007_full_path_readiness_gate(summary: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Evaluate the strict no-long-scan gate for T007 lifecycle collection.

    This gate is intentionally separate from profitability, trading, paper
    trading, Mayhem, and valuation ladder logic. It only answers whether the
    collector has proven full-path data quality well enough to justify scans
    beyond a bounded 10-minute feature proof.
    """

    payload = dict(summary or {})
    migrated = _int(payload.get("migrated_unique_mints"))
    full = _int(payload.get("full_path_migrated_mints") or payload.get("strict_full_paths"))
    full_rate = _float(payload.get("full_path_migrated_rate"), _rate(full, migrated))
    source_miss_count = _int(payload.get("source_miss_count"))
    sample_loss_count = _int(payload.get("sample_loss_count"))
    curve_missing_count = _int(payload.get("curve_observation_missing_count"))
    trade_flow_missing_count = _int(payload.get("trade_flow_missing_count"))
    migration_backfill_failed_count = _int(payload.get("migration_backfill_failed_count"))
    queue_drops = _int(payload.get("queue_drops") or payload.get("queue_dropped_count"))
    thin_queue_drops = _int(payload.get("thin_queue_drops") or payload.get("thin_probe_queue_drops"))
    capacity_rejected = _int(payload.get("capacity_rejected") or payload.get("capacity_rejected_births"))
    source_duration_quality_status = str(payload.get("source_duration_quality_status") or "not_evaluated")
    source_ended_early = _bool(payload.get("source_ended_early"), False)
    websocket_keepalive_timeout_count = _int(payload.get("websocket_keepalive_timeout_count"))
    websocket_reconnect_count = _int(payload.get("websocket_reconnect_count"))
    subscription_connect_status = str(payload.get("subscription_connect_status") or "")
    persistent_lifecycle_store_required = _bool(payload.get("persistent_lifecycle_store_required"), False)
    persistent_lifecycle_store_status = str(payload.get("persistent_lifecycle_store_status") or "not_required")

    required_full_path_rate = _float(payload.get("required_full_path_migrated_rate"), DEFAULT_REQUIRED_FULL_PATH_MIGRATED_RATE)
    required_birth_seen_rate = _float(payload.get("required_migrated_birth_seen_rate"), DEFAULT_REQUIRED_BIRTH_SEEN_RATE)
    required_curve_rate = _float(payload.get("required_migrated_curve_observation_rate"), DEFAULT_REQUIRED_CURVE_OBSERVATION_RATE)
    required_trade_rate = _float(payload.get("required_migrated_trade_flow_rate"), DEFAULT_REQUIRED_TRADE_FLOW_RATE)
    required_quote_rate = _float(payload.get("required_migrated_post_migration_quote_rate"), DEFAULT_REQUIRED_POST_MIGRATION_QUOTE_RATE)
    required_execution_cost_rate = _float(payload.get("required_migrated_execution_cost_join_rate"), DEFAULT_REQUIRED_EXECUTION_COST_JOIN_RATE)
    required_evidence_completeness_rate = _float(payload.get("required_evidence_completeness_rate"), DEFAULT_REQUIRED_EVIDENCE_COMPLETENESS_RATE)

    birth_seen_rate = _float(payload.get("migrated_birth_seen_rate"))
    curve_rate = _float(payload.get("migrated_curve_observation_rate"))
    trade_rate = _float(payload.get("migrated_trade_flow_rate"))
    quote_rate = _float(payload.get("migrated_post_migration_quote_rate"))
    execution_cost_rate = _float(payload.get("migrated_execution_cost_join_rate"))
    evidence_completeness_rate = _float(payload.get("evidence_completeness_rate"))

    valuation_ladder_suppressed = _bool(payload.get("valuation_ladder_suppressed"), True)
    mayhem_untouched = _bool(payload.get("mayhem_untouched"), True)
    trading_disabled = _bool(payload.get("trading_disabled"), True)
    paper_trading_disabled = _bool(payload.get("paper_trading_disabled"), True)
    wallet_signing_disabled = _bool(payload.get("wallet_signing_disabled"), True)

    blocking_60m: list[str] = []
    _append_if(not valuation_ladder_suppressed, blocking_60m, "valuation_ladder_not_suppressed")
    _append_if(not mayhem_untouched, blocking_60m, "mayhem_not_untouched")
    _append_if(not trading_disabled, blocking_60m, "trading_not_disabled")
    _append_if(not paper_trading_disabled, blocking_60m, "paper_trading_not_disabled")
    _append_if(not wallet_signing_disabled, blocking_60m, "wallet_signing_not_disabled")
    _append_if(queue_drops > 0, blocking_60m, "queue_drops_nonzero")
    _append_if(thin_queue_drops > 0, blocking_60m, "thin_queue_drops_nonzero")
    _append_if(capacity_rejected > 0, blocking_60m, "capacity_rejected_nonzero")
    _append_if(source_duration_quality_status == "failed", blocking_60m, "source_duration_failed")
    _append_if(source_duration_quality_status == "partial", blocking_60m, "source_duration_partial")
    _append_if(source_ended_early, blocking_60m, "source_ended_early")
    _append_if(subscription_connect_status.startswith("unavailable:"), blocking_60m, "source_subscription_unavailable")
    _append_if(
        persistent_lifecycle_store_required and persistent_lifecycle_store_status != "available",
        blocking_60m,
        "persistent_lifecycle_store_unavailable",
    )
    _append_if(migrated <= 0, blocking_60m, "no_migrations_observed_for_lifecycle_proof")
    if migrated > 0:
        _append_if(full <= 0, blocking_60m, "full_path_migrated_mints_zero")
        _append_if(full_rate < required_full_path_rate, blocking_60m, "full_path_migrated_rate_below_threshold")
        _append_if(source_miss_count > 0, blocking_60m, "migrated_source_miss_count_nonzero")
        _append_if(sample_loss_count > 0, blocking_60m, "migrated_sample_loss_count_nonzero")
        _append_if(curve_missing_count > 0, blocking_60m, "migrated_curve_observation_missing_count_nonzero")
        _append_if(trade_flow_missing_count > 0, blocking_60m, "migrated_trade_flow_missing_count_nonzero")
        _append_if(migration_backfill_failed_count > 0, blocking_60m, "migration_backfill_failed_count_nonzero")
        _append_if(birth_seen_rate < required_birth_seen_rate, blocking_60m, "migrated_birth_seen_rate_below_threshold")
        _append_if(curve_rate < required_curve_rate, blocking_60m, "migrated_curve_observation_rate_below_threshold")
        _append_if(trade_rate < required_trade_rate, blocking_60m, "migrated_trade_flow_rate_below_threshold")
        _append_if(quote_rate < required_quote_rate, blocking_60m, "migrated_post_migration_quote_rate_below_threshold")
        _append_if(execution_cost_rate < required_execution_cost_rate, blocking_60m, "migrated_execution_cost_join_rate_below_threshold")
    _append_if(migrated > 0 and evidence_completeness_rate < required_evidence_completeness_rate, blocking_60m, "evidence_completeness_rate_below_threshold")

    can_run_10m = valuation_ladder_suppressed and mayhem_untouched and trading_disabled and paper_trading_disabled and wallet_signing_disabled
    can_run_60m = can_run_10m and not blocking_60m
    valid_60m_passed = _bool(payload.get("valid_60m_thesis_scan_passed"), False)
    blocking_2h: list[str] = []
    if can_run_60m and not valid_60m_passed:
        blocking_2h.append("valid_60m_thesis_scan_not_yet_passed_for_2h_plus")
    can_run_2h = can_run_60m and valid_60m_passed
    blocking_reasons = [*blocking_60m, *blocking_2h]

    return {
        "gate_id": "T007BD_FULL_PATH_LIFECYCLE_READINESS_GATE",
        "can_run_10m_feature_proof": can_run_10m,
        "can_run_60m_thesis_scan": can_run_60m,
        "can_run_2h_plus_scan": can_run_2h,
        "long_scan_status": "READY_FOR_60M_ONLY" if can_run_60m and not can_run_2h else ("READY_FOR_2H_PLUS" if can_run_2h else "BLOCKED_FOR_LONG_SCAN"),
        "blocking_reasons": blocking_reasons,
        "minimum_next_action": "run_one_bounded_10m_feature_proof" if not can_run_60m else ("run_one_60m_thesis_scan" if not can_run_2h else "long_scan_allowed_after_user_approval"),
        "migrated_unique_mints": migrated,
        "full_path_migrated_mints": full,
        "full_path_migrated_rate": full_rate,
        "required_full_path_migrated_rate": required_full_path_rate,
        "migrated_birth_seen_rate": birth_seen_rate,
        "required_migrated_birth_seen_rate": required_birth_seen_rate,
        "migrated_curve_observation_rate": curve_rate,
        "required_migrated_curve_observation_rate": required_curve_rate,
        "migrated_trade_flow_rate": trade_rate,
        "required_migrated_trade_flow_rate": required_trade_rate,
        "migrated_post_migration_quote_rate": quote_rate,
        "required_migrated_post_migration_quote_rate": required_quote_rate,
        "migrated_execution_cost_join_rate": execution_cost_rate,
        "required_migrated_execution_cost_join_rate": required_execution_cost_rate,
        "evidence_completeness_rate": evidence_completeness_rate,
        "required_evidence_completeness_rate": required_evidence_completeness_rate,
        "source_miss_count": source_miss_count,
        "sample_loss_count": sample_loss_count,
        "curve_observation_missing_count": curve_missing_count,
        "trade_flow_missing_count": trade_flow_missing_count,
        "migration_backfill_failed_count": migration_backfill_failed_count,
        "queue_drops": queue_drops,
        "thin_queue_drops": thin_queue_drops,
        "capacity_rejected": capacity_rejected,
        "source_duration_quality_status": source_duration_quality_status,
        "source_ended_early": source_ended_early,
        "websocket_keepalive_timeout_count": websocket_keepalive_timeout_count,
        "websocket_reconnect_count": websocket_reconnect_count,
        "subscription_connect_status": subscription_connect_status,
        "persistent_lifecycle_store_required": persistent_lifecycle_store_required,
        "persistent_lifecycle_store_status": persistent_lifecycle_store_status,
        "valuation_ladder_suppressed": valuation_ladder_suppressed,
        "mayhem_untouched": mayhem_untouched,
        "trading_disabled": trading_disabled,
        "paper_trading_disabled": paper_trading_disabled,
        "wallet_signing_disabled": wallet_signing_disabled,
        "helius_developer_source_supported": True,
        "helius_developer_source_usage": "configured_source_capability_only_no_live_scan_started_by_gate",
        "edge_claim_allowed": False,
    }


def write_t007_full_path_readiness_gate(output_root: Path | str, summary: Mapping[str, Any] | None = None) -> dict[str, Any]:
    output = Path(output_root)
    output.mkdir(parents=True, exist_ok=True)
    gate = evaluate_t007_full_path_readiness_gate(summary)
    (output / "thesis_ready_gate.json").write_text(json.dumps(gate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    blocking = gate.get("blocking_reasons") or []
    lines = [
        "# T007 Full Path Lifecycle Readiness Gate",
        "",
        "No live scan was run by this gate writer.",
        "",
        f"- Can run 10m feature proof: `{gate['can_run_10m_feature_proof']}`",
        f"- Can run 60m thesis scan: `{gate['can_run_60m_thesis_scan']}`",
        f"- Can run 2h+ scan: `{gate['can_run_2h_plus_scan']}`",
        f"- Long scan status: `{gate['long_scan_status']}`",
        f"- Minimum next action: `{gate['minimum_next_action']}`",
        f"- Helius developer source supported: `{gate['helius_developer_source_supported']}`",
        "",
        "## Blocking reasons",
        "",
        *[f"- `{reason}`" for reason in blocking],
    ]
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return gate

# --- T007_PRODUCTION_READY_GATE_OVERRIDES_V2 --------------------------------
def t007_production_gate_decision(summary, *, duration_seconds=None):
    summary = dict(summary or {})
    blockers = []
    duration = duration_seconds or summary.get("source_duration_seconds") or summary.get("requested_source_duration_seconds") or 0
    try:
        duration = float(duration)
    except (TypeError, ValueError):
        duration = 0
    if not summary.get("db_writer_alive", True):
        blockers.append("db_writer_not_alive")
    if not summary.get("db_ledger_consistent", True):
        blockers.append("db_ledger_inconsistent")
    if int(summary.get("queue_dropped_total") or summary.get("queue_dropped") or 0) > 0:
        blockers.append("queue_dropped")
    if int(summary.get("source_gap_detected_count") or 0) > int(summary.get("source_gap_backfilled_count") or 0):
        blockers.append("unbackfilled_source_gap")
    if int(summary.get("curve_state_decoded") or summary.get("progress_decoded_count") or 0) == 0:
        blockers.append("no_curve_state_decoded")
    if int(summary.get("market_cap_available") or summary.get("market_cap_progress_count") or 0) == 0:
        blockers.append("no_market_cap_progress")
    if duration >= 1800 and int(summary.get("global_migrations_seen") or summary.get("migrations_seen") or 0) == 0:
        blockers.append("no_migrations_seen_in_controlled_window")
    if int(summary.get("global_migrations_seen") or 0) > 0 and int(summary.get("migrations_with_decision_safe_full_path") or 0) == 0:
        blockers.append("migrations_not_linked_to_decision_safe_full_path")
    label = "T007_PRODUCTION_LIFECYCLE_READY_FOR_10M_PROOF" if not blockers else "T007_PRODUCTION_LIFECYCLE_BLOCKED"
    return {"decision_label": label, "blockers": blockers, "execution_cost_required_for_readiness": False}

# If the module exposes a direct gate function with a conventional name, wrap it
# to preserve existing fields and add production blockers.
for _gate_name in ("evaluate_t007_thesis_ready_gate", "evaluate_readiness_gate", "build_readiness_gate"):
    _gate_fn = globals().get(_gate_name)
    if callable(_gate_fn) and not getattr(_gate_fn, "_t007_production_wrapped", False):
        def _make_gate_wrapper(fn):
            def _wrapped(*args, **kwargs):
                result = fn(*args, **kwargs)
                summary = args[0] if args else kwargs.get("summary") or {}
                production = t007_production_gate_decision(summary)
                if isinstance(result, dict):
                    result.setdefault("production_decision_label", production["decision_label"])
                    result.setdefault("production_blockers", production["blockers"])
                    result["execution_cost_required_for_readiness"] = False
                    if production["blockers"]:
                        result["decision_label"] = production["decision_label"]
                        result["blockers"] = sorted(set(result.get("blockers") or []) | set(production["blockers"]))
                return result
            _wrapped._t007_production_wrapped = True
            return _wrapped
        globals()[_gate_name] = _make_gate_wrapper(_gate_fn)
