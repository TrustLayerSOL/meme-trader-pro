"""T012 paper position ledger scaffolding and principal recovery accounting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from research.mtp_research.validation.t012_paper_snapshot_contract import GUARDRAILS, STAGE

LEDGER_FIELDS = [
    "paper_position_id", "run_id", "rule_id", "rule_version", "rule_hash", "mint", "position_status",
    "entry_snapshot_id", "entry_time", "entry_market_cap", "entry_curve_progress", "entry_token_age_seconds",
    "total_buy_quote", "total_sell_quote", "estimated_fees_quote", "net_cost_remaining_quote",
    "token_amount_bought", "token_amount_sold", "token_amount_remaining", "principal_recovered",
    "principal_recovery_time", "time_to_first_sell_seconds", "time_to_principal_recovered_seconds",
    "realized_pnl_quote", "unrealized_pnl_quote_proxy", "runner_remaining_pct", "accounting_confidence",
    "decision_time_safe", "source_provenance",
]
PRINCIPAL_FIELDS = [
    "paper_position_id", "mint", "total_cost_basis_quote", "estimated_fees_quote", "total_sell_proceeds_quote",
    "principal_recovered", "principal_recovered_at", "principal_recovery_ratio", "principal_recovery_status",
    "accounting_confidence",
]


def _schema_marker(artifact: str, fields: list[str], run_id: str | None) -> dict[str, Any]:
    return {
        **GUARDRAILS,
        "schema_marker": True,
        "artifact": artifact,
        "run_id": run_id,
        "required_fields": fields,
        "paper_trade_generated": False,
        "position_status": "schema_only_no_position",
        **{field: None for field in fields if field not in GUARDRAILS},
    }


def _ensure_jsonl_with_marker(path: Path, marker: dict[str, Any]) -> None:
    if path.exists() and path.stat().st_size > 0:
        return
    with path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(marker, sort_keys=True, default=str) + "\n")


def ensure_paper_position_artifacts(output_root: Path | str, *, run_id: str | None = None) -> dict[str, Path]:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    paths = paper_position_artifact_paths(root)
    _ensure_jsonl_with_marker(paths["paper_position_ledger"], _schema_marker("paper_position_ledger", LEDGER_FIELDS, run_id))
    _ensure_jsonl_with_marker(paths["paper_position_events"], _schema_marker("paper_position_events", LEDGER_FIELDS, run_id))
    _ensure_jsonl_with_marker(
        paths["paper_position_accounting_snapshots"],
        _schema_marker("paper_position_accounting_snapshots", LEDGER_FIELDS, run_id),
    )
    _ensure_jsonl_with_marker(
        paths["paper_principal_recovery_events"],
        _schema_marker("paper_principal_recovery_events", PRINCIPAL_FIELDS, run_id),
    )
    return paths


def paper_position_artifact_paths(output_root: Path | str) -> dict[str, Path]:
    root = Path(output_root)
    return {
        "paper_position_ledger": root / "paper_position_ledger.jsonl",
        "paper_position_events": root / "paper_position_events.jsonl",
        "paper_position_accounting_snapshots": root / "paper_position_accounting_snapshots.jsonl",
        "paper_principal_recovery_events": root / "paper_principal_recovery_events.jsonl",
    }


def _first_jsonl(path: Path) -> dict[str, Any] | None:
    if not path.exists() or path.stat().st_size <= 0:
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            return json.loads(line)
    return None


def validate_paper_position_accounting_schema(output_root: Path | str) -> dict[str, Any]:
    root = Path(output_root)
    paths = paper_position_artifact_paths(root)
    row = _first_jsonl(paths["paper_position_accounting_snapshots"])
    missing = [field for field in LEDGER_FIELDS if not row or field not in row]
    return {
        **GUARDRAILS,
        "schema_valid": not missing,
        "missing_fields": missing,
        "artifact_path": str(paths["paper_position_accounting_snapshots"]),
        "artifact_exists": paths["paper_position_accounting_snapshots"].exists(),
    }


def validate_principal_recovery_schema(output_root: Path | str) -> dict[str, Any]:
    root = Path(output_root)
    paths = paper_position_artifact_paths(root)
    row = _first_jsonl(paths["paper_principal_recovery_events"])
    missing = [field for field in PRINCIPAL_FIELDS if not row or field not in row]
    return {
        **GUARDRAILS,
        "schema_valid": not missing,
        "missing_fields": missing,
        "artifact_path": str(paths["paper_principal_recovery_events"]),
        "artifact_exists": paths["paper_principal_recovery_events"].exists(),
    }


def evaluate_principal_recovery(
    *,
    paper_position_id: str | None,
    mint: str | None,
    total_cost_basis_quote: float | None,
    estimated_fees_quote: float | None,
    total_sell_proceeds_quote: float | None,
    principal_recovered_at: float | None = None,
) -> dict[str, Any]:
    if paper_position_id is None:
        status = "not_applicable_no_position"
        ratio = None
        recovered = False
    elif total_cost_basis_quote is None:
        status = "unknown_missing_cost_basis"
        ratio = None
        recovered = False
    elif total_sell_proceeds_quote is None:
        status = "unknown_missing_sell_proceeds"
        ratio = None
        recovered = False
    else:
        required = float(total_cost_basis_quote) + float(estimated_fees_quote or 0.0)
        ratio = float(total_sell_proceeds_quote) / required if required > 0 else None
        recovered = bool(ratio is not None and ratio >= 1.0)
        if recovered:
            status = "principal_recovered"
        elif float(total_sell_proceeds_quote) > 0:
            status = "partially_recovered"
        else:
            status = "not_recovered"
    return {
        **GUARDRAILS,
        "paper_position_id": paper_position_id,
        "mint": mint,
        "total_cost_basis_quote": total_cost_basis_quote,
        "estimated_fees_quote": estimated_fees_quote,
        "total_sell_proceeds_quote": total_sell_proceeds_quote,
        "principal_recovered": recovered,
        "principal_recovered_at": principal_recovered_at,
        "principal_recovery_ratio": ratio,
        "principal_recovery_status": status,
        "accounting_confidence": "schema_only" if status == "not_applicable_no_position" else "available",
    }
