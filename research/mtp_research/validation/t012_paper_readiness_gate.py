"""T012 rule-agnostic pre-migration paper-readiness audit and gate."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from research.mtp_research.validation.t012_paper_position_ledger import (
    paper_position_artifact_paths,
    validate_paper_position_accounting_schema,
    validate_principal_recovery_schema,
)
from research.mtp_research.validation.t012_paper_snapshot_contract import GUARDRAILS, STAGE


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _hist(summary: dict[str, Any], name: str) -> dict[str, Any]:
    direct = summary.get(name)
    if isinstance(direct, dict):
        return direct
    nested = summary.get("route_latency_histograms")
    if isinstance(nested, dict) and isinstance(nested.get(name), dict):
        return nested[name]
    return {}


def _p95(summary: dict[str, Any], name: str) -> float | None:
    value = _hist(summary, name).get("p95")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _source_duration_status(summary: dict[str, Any], live_status: dict[str, Any]) -> str:
    for row in [summary, live_status]:
        value = row.get("source_duration_quality_status") or row.get("validation_run_quality_label")
        if isinstance(value, str) and value:
            lowered = value.lower()
            if "complete" in lowered or "passed" in lowered:
                return "complete"
            return value
    if summary.get("completed_requested_duration") is True or live_status.get("completed_requested_duration") is True:
        return "complete"
    return "unknown"


def build_t012_paper_readiness_gate(run_root: Path | str, *, collector_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    root = Path(run_root)
    summary = collector_summary or _read_json(root / "collector_summary.json")
    live_status = _read_json(root / "live_status.json")
    pre_rows = _read_jsonl(root / "pre_entry_decision_snapshots.jsonl")
    post_rows = _read_jsonl(root / "post_entry_hot_flow_snapshots.jsonl")
    wallet_rows = _read_jsonl(root / "wallet_dev_checkpoints.jsonl")
    paper_paths = paper_position_artifact_paths(root)
    accounting_schema = validate_paper_position_accounting_schema(root)
    principal_schema = validate_principal_recovery_schema(root)

    post_counts = Counter(int(row.get("snapshot_offset_seconds") or 0) for row in post_rows if not row.get("schema_marker"))
    pre_real_rows = [row for row in pre_rows if not row.get("schema_marker")]
    dev_safe = sum(1 for row in pre_real_rows if row.get("dev_previous_migrations_decision_time_safe") is True)
    creator_safe = sum(1 for row in pre_real_rows if row.get("creator_sold_before_entry_decision_time_safe") is True)
    if dev_safe <= 0:
        dev_safe = sum(1 for row in wallet_rows if row.get("dev_previous_migrations_decision_time_safe") is True)
    if creator_safe <= 0:
        creator_safe = sum(1 for row in wallet_rows if row.get("creator_sold_before_entry_decision_time_safe") is True)

    queue_drops = int(summary.get("queue_drops") or summary.get("queue_dropped_count") or live_status.get("queue_drops") or 0)
    birth_queue_drops = int(summary.get("birth_priority_queue_dropped_count") or summary.get("birth_admission_queue_dropped_count") or 0)
    trade_flow_hot_lane_drops = int(summary.get("near_entry_hot_flow_ring_buffer_dropped_count") or 0)
    rpc_failures = int(summary.get("rpc_failures") or live_status.get("rpc_failures") or 0)
    http_429_count = int(summary.get("http_429_count") or summary.get("http_429") or live_status.get("http_429") or 0)
    run_finalized = bool(summary.get("run_finalized") or str(summary.get("run_status") or "").startswith("finalized"))
    source_duration_quality_status = _source_duration_status(summary, live_status)

    gate = {
        **GUARDRAILS,
        "gate_id": "T012_PRE_MIGRATION_PAPER_READINESS_GATE",
        "gate_passed": False,
        "paper_ready_status": "blocked",
        "blocking_reasons": [],
        "warning_reasons": [],
        "source_duration_quality_status": source_duration_quality_status,
        "run_finalized": run_finalized,
        "queue_drops": queue_drops,
        "birth_queue_drops": birth_queue_drops,
        "trade_flow_hot_lane_drops": trade_flow_hot_lane_drops,
        "rpc_failures": rpc_failures,
        "http_429_count": http_429_count,
        "birth_to_admission_enqueue_p95_ms": _p95(summary, "birth_to_admission_enqueue_latency_ms"),
        "birth_to_admission_complete_p95_ms": _p95(summary, "birth_to_admission_complete_latency_ms"),
        "birth_to_first_curve_observation_p95_ms": _p95(summary, "birth_to_first_curve_observation_latency_ms"),
        "normalized_birth_to_probe_start_p95_ms": _p95(summary, "normalized_birth_to_probe_start_latency_ms"),
        "pre_entry_snapshot_count": len(pre_real_rows),
        "pre_entry_30s_snapshot_count": sum(1 for row in pre_real_rows if row.get("event_count_30s_since_birth") is not None),
        "pre_entry_60s_snapshot_count": sum(1 for row in pre_real_rows if row.get("event_count_60s") is not None),
        "post_entry_hot_flow_snapshot_count": sum(post_counts.values()),
        "post_entry_1s_snapshot_count": post_counts.get(1, 0),
        "post_entry_5s_snapshot_count": post_counts.get(5, 0),
        "post_entry_10s_snapshot_count": post_counts.get(10, 0),
        "post_entry_30s_snapshot_count": post_counts.get(30, 0),
        "post_entry_60s_snapshot_count": post_counts.get(60, 0),
        "dev_previous_migrations_decision_safe_count": dev_safe,
        "creator_sold_before_entry_decision_safe_count": creator_safe,
        "paper_position_ledger_exists": paper_paths["paper_position_ledger"].exists(),
        "paper_position_accounting_schema_valid": bool(accounting_schema.get("schema_valid")),
        "principal_recovery_tracking_schema_valid": bool(principal_schema.get("schema_valid")),
        "wallet_private_key_signing_execution_absent": True,
        "paper_trading_enabled": bool(summary.get("paper_trading_enabled", False)),
        "live_trading_enabled": bool(summary.get("live_trading_enabled", False)),
        "wallet_signing_execution_present": False,
    }
    reasons: list[str] = []
    if gate["source_duration_quality_status"] != "complete":
        reasons.append("source_duration_not_complete")
    if not gate["run_finalized"]:
        reasons.append("run_not_finalized")
    if queue_drops != 0:
        reasons.append("queue_drops_nonzero")
    if birth_queue_drops != 0:
        reasons.append("birth_queue_drops_nonzero")
    if trade_flow_hot_lane_drops != 0:
        reasons.append("trade_flow_hot_lane_drops_nonzero")
    if rpc_failures != 0:
        reasons.append("rpc_failures_nonzero")
    if http_429_count != 0:
        reasons.append("http_429_nonzero")
    thresholds = [
        ("birth_to_admission_complete", gate["birth_to_admission_complete_p95_ms"], 1500.0),
        ("birth_to_first_curve_observation", gate["birth_to_first_curve_observation_p95_ms"], 3000.0),
        ("normalized_birth_to_probe_start", gate["normalized_birth_to_probe_start_p95_ms"], 1500.0),
    ]
    for label, value, limit in thresholds:
        if value is None:
            reasons.append(f"{label}_p95_missing")
        elif float(value) > limit:
            reasons.append(f"{label}_p95_exceeded")
    for offset in [30, 60]:
        if gate[f"pre_entry_{offset}s_snapshot_count"] <= 0:
            reasons.append(f"pre_entry_{offset}s_snapshot_missing")
    for offset in [1, 5, 10, 30, 60]:
        if gate[f"post_entry_{offset}s_snapshot_count"] <= 0:
            reasons.append(f"post_entry_{offset}s_snapshot_missing")
    if dev_safe <= 0:
        reasons.append("dev_previous_migrations_decision_safe_missing")
    if creator_safe <= 0:
        reasons.append("creator_sold_before_entry_decision_safe_missing")
    if not gate["paper_position_ledger_exists"]:
        reasons.append("paper_position_ledger_missing")
    if not gate["paper_position_accounting_schema_valid"]:
        reasons.append("paper_position_accounting_schema_invalid")
    if not gate["principal_recovery_tracking_schema_valid"]:
        reasons.append("principal_recovery_tracking_schema_invalid")
    if not gate["wallet_private_key_signing_execution_absent"]:
        reasons.append("wallet_private_key_signing_execution_present")
    if gate["paper_trading_enabled"]:
        reasons.append("paper_trading_enabled_must_remain_false")
    if gate["live_trading_enabled"]:
        reasons.append("live_trading_enabled_must_remain_false")
    gate["blocking_reasons"] = reasons
    gate["gate_passed"] = not reasons
    gate["paper_infrastructure_ready"] = not reasons
    gate["paper_ready_status"] = "paper_infrastructure_ready" if not reasons else "blocked"
    return gate


def run_t012_paper_readiness_audit(run_root: Path | str) -> dict[str, Any]:
    root = Path(run_root)
    materialization: dict[str, Any] | None = None
    try:
        from research.mtp_research.validation.t012_paper_artifact_materializer import (
            materialize_t012_paper_readiness_artifacts,
        )

        materialization = materialize_t012_paper_readiness_artifacts(root)
    except Exception as exc:
        materialization = {
            "materialized_snapshot_artifacts": False,
            "materialization_error": f"{type(exc).__name__}: {exc}",
        }
    gate = build_t012_paper_readiness_gate(root)
    gate["t012_paper_artifact_materialization"] = materialization
    gate["paper_readiness_gate_path"] = str(root / "paper_readiness_gate.json")
    gate["paper_readiness_audit_json_path"] = str(root / "paper_readiness_audit.json")
    gate["paper_readiness_audit_md_path"] = str(root / "paper_readiness_audit.md")
    for name in ["paper_readiness_gate.json", "paper_readiness_audit.json"]:
        (root / name).write_text(json.dumps(gate, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    (root / "paper_readiness_summary.md").write_text(
        "# T012 Pre-Migration Paper Readiness Summary\n\n"
        f"- Stage: `{STAGE}`\n"
        f"- Gate passed: `{gate['gate_passed']}`\n"
        f"- Status: `{gate['paper_ready_status']}`\n"
        f"- Blocking reasons: `{gate['blocking_reasons']}`\n"
        f"- Pre-entry snapshots: `{gate['pre_entry_snapshot_count']}`\n"
        f"- Post-entry hot-flow snapshots: `{gate['post_entry_hot_flow_snapshot_count']}`\n"
        f"- Paper position ledger exists: `{gate['paper_position_ledger_exists']}`\n"
        f"- Principal recovery schema valid: `{gate['principal_recovery_tracking_schema_valid']}`\n"
        "- Paper trading enabled: `false`\n"
        "- Live trading enabled: `false`\n",
        encoding="utf-8",
    )
    (root / "paper_readiness_audit.md").write_text(
        "# T012 Pre-Migration Paper Readiness Audit\n\n"
        f"- Gate passed: `{gate['gate_passed']}`\n"
        f"- Status: `{gate['paper_ready_status']}`\n"
        f"- Blocking reasons: `{gate['blocking_reasons']}`\n"
        f"- Pre-entry snapshots: `{gate['pre_entry_snapshot_count']}`\n"
        f"- Post-entry hot-flow snapshots: `{gate['post_entry_hot_flow_snapshot_count']}`\n"
        f"- Paper trading enabled: `{gate['paper_trading_enabled']}`\n"
        f"- Live trading enabled: `{gate['live_trading_enabled']}`\n",
        encoding="utf-8",
    )
    return gate
