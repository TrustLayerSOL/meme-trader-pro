from __future__ import annotations

import json
import time
from typing import Any


MODE = "ARCHIVAL_SUPPLY_PROOF_EXPORT_REVIEW_ONLY"
VERSION = "archival_supply_proof_exports.v1"


VALID_EVIDENCE_COLUMNS = [
    "evidence_key",
    "wallet",
    "token_mint",
    "transaction_signature",
    "decision_slot",
    "snapshot_slot",
    "raw_supply",
    "ui_supply",
    "decimals",
    "status",
    "source",
    "decision_time_safe",
]

REJECTED_COLUMNS = [
    "evidence_key",
    "token_mint",
    "request_id",
    "status",
    "block_reasons",
    "requested_snapshot_slot",
    "requested_snapshot_time",
    "provider_response_slot",
    "max_acceptable_snapshot_slot",
    "decision_time_safe",
]


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def json_cell(value: Any) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True)
    if value is None:
        return ""
    return str(value)


def valid_evidence_rows(archival_supply_evidence_report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in as_list(archival_supply_evidence_report.get("records")):
        if isinstance(row, dict) and row.get("status") == "archival_supply_recovered":
            rows.append({column: row.get(column) for column in VALID_EVIDENCE_COLUMNS})
    return rows


def rejected_import_rows(response_import_report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in as_list(response_import_report.get("import_rows")):
        if not isinstance(row, dict) or row.get("status") == "archival_snapshot_imported":
            continue
        rows.append({column: row.get(column) for column in REJECTED_COLUMNS})
    return rows


def rejected_evidence_rows(
    archival_supply_evidence_report: dict[str, Any],
    *,
    existing_keys: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in as_list(archival_supply_evidence_report.get("records")):
        if not isinstance(row, dict) or row.get("status") == "archival_supply_recovered":
            continue
        key = str(row.get("evidence_key") or "")
        if key and key in existing_keys:
            continue
        rows.append(
            {
                "evidence_key": row.get("evidence_key"),
                "token_mint": row.get("token_mint"),
                "request_id": row.get("request_id"),
                "status": row.get("status"),
                "block_reasons": row.get("block_reasons"),
                "requested_snapshot_slot": row.get("decision_slot"),
                "requested_snapshot_time": row.get("timestamp"),
                "provider_response_slot": row.get("snapshot_slot"),
                "max_acceptable_snapshot_slot": row.get("decision_slot"),
                "decision_time_safe": row.get("decision_time_safe"),
            }
        )
    return rows


def rows_upgraded_by_archival_supply(score_ready_market_context_report: dict[str, Any]) -> int:
    return sum(
        1
        for row in as_list(score_ready_market_context_report.get("records"))
        if isinstance(row, dict)
        and row.get("readiness_status") == "score_ready"
        and row.get("supply_source") == "archival_supply_evidence"
    )


def matched_import_rows(response_import_report: dict[str, Any]) -> int:
    return sum(
        1
        for row in as_list(response_import_report.get("import_rows"))
        if isinstance(row, dict) and row.get("status") != "blocked_missing_response"
    )


def top_blockers(proof_readiness_report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [row for row in as_list(proof_readiness_report.get("reduction_queue")) if isinstance(row, dict)]
    rows.sort(key=lambda row: safe_int(row.get("priority"), 999))
    return [
        {
            "priority": row.get("priority"),
            "category": row.get("category"),
            "gap": row.get("gap"),
            "next_action": row.get("next_action"),
        }
        for row in rows[:5]
    ]


def render_markdown(summary: dict[str, Any], blockers: list[dict[str, Any]]) -> str:
    lines = [
        "# Archival Supply Proof Readiness",
        "",
        "Review-only evidence recovery report. Live execution, wallet trust mutation, and wallet-list mutation remain locked.",
        "",
        "## Summary",
        "",
        f"- Total request rows: `{summary['total_request_rows']}`",
        f"- Imported provider responses: `{summary['imported_provider_responses']}`",
        f"- Matched rows: `{summary['matched_rows']}`",
        f"- Valid archival supply rows: `{summary['valid_archival_supply_rows']}`",
        f"- Rejected or quarantined rows: `{summary['rejected_or_quarantined_rows']}`",
        f"- Rows upgraded from near-score-ready to score-ready: `{summary['rows_upgraded_from_near_score_ready_to_score_ready']}`",
        f"- Updated proof-readiness percentage: `{summary['updated_proof_readiness_pct']}%`",
        "",
        "## Top Remaining Blockers",
        "",
    ]
    if blockers:
        for blocker in blockers:
            lines.append(
                f"- `{blocker.get('category')}` gap `{blocker.get('gap')}`: {blocker.get('next_action') or 'No action text recorded.'}"
            )
    else:
        lines.append("- No blocker rows were present in the proof-readiness report.")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- Live execution locked: `true`",
            "- Wallet trust mutations: `0`",
            "- Wallet list mutations: `0`",
            "- Current/future supply substitution: `blocked`",
            "",
        ]
    )
    return "\n".join(lines)


def build_archival_supply_proof_export(
    *,
    request_bundle_report: dict[str, Any],
    response_import_report: dict[str, Any],
    archival_supply_evidence_report: dict[str, Any],
    score_ready_market_context_report: dict[str, Any],
    proof_readiness_report: dict[str, Any],
    generated_at: float | None = None,
) -> dict[str, Any]:
    bundle_summary = as_dict(request_bundle_report.get("summary"))
    import_summary = as_dict(response_import_report.get("summary"))
    evidence_summary = as_dict(archival_supply_evidence_report.get("summary"))
    proof_summary = as_dict(proof_readiness_report.get("summary"))

    valid_rows = valid_evidence_rows(archival_supply_evidence_report)
    rejected_rows = rejected_import_rows(response_import_report)
    rejected_keys = {str(row.get("evidence_key") or "") for row in rejected_rows}
    rejected_rows.extend(rejected_evidence_rows(archival_supply_evidence_report, existing_keys=rejected_keys))
    blockers = top_blockers(proof_readiness_report)

    summary = {
        "total_request_rows": safe_int(bundle_summary.get("requests_bundled")),
        "request_chunk_count": safe_int(bundle_summary.get("request_chunk_count")),
        "target_tokens": safe_int(bundle_summary.get("target_tokens")),
        "imported_provider_responses": safe_int(import_summary.get("raw_responses_scanned")),
        "matched_rows": matched_import_rows(response_import_report),
        "valid_archival_supply_rows": safe_int(evidence_summary.get("supply_recovered_records")) or len(valid_rows),
        "rejected_or_quarantined_rows": len(rejected_rows),
        "rows_upgraded_from_near_score_ready_to_score_ready": rows_upgraded_by_archival_supply(score_ready_market_context_report),
        "updated_proof_readiness_pct": safe_int(proof_summary.get("proof_readiness_pct")),
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
    }

    return {
        "mode": MODE,
        "version": VERSION,
        "generated_at": time.time() if generated_at is None else float(generated_at),
        "review_only": True,
        "read_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "current_supply_substitution_allowed": False,
        "summary": summary,
        "top_remaining_blockers": blockers,
        "valid_evidence_rows": valid_rows,
        "rejected_rows": rejected_rows,
        "markdown": render_markdown(summary, blockers),
        "operator_note": (
            "This export summarizes archival supply evidence recovery only. It cannot score wallets, "
            "promote trust, mutate wallet lists, enable execution, or substitute current supply."
        ),
    }
