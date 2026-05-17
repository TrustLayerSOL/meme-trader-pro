from __future__ import annotations

import time
from collections import Counter
from typing import Any

from wallets.wallet_evidence_models import as_dict, safe_float, safe_int


MODE = "ARCHIVAL_SUPPLY_EVIDENCE_REVIEW_ONLY"
VERSION = "archival_supply_evidence.v1"


def token_mint(row: dict[str, Any]) -> str:
    return str(row.get("token_mint") or row.get("mint") or "").strip()


def candidate_rows(plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows = plan.get("candidate_rows") if isinstance(plan, dict) else []
    return [row for row in rows or [] if isinstance(row, dict)]


def snapshot_token(row: dict[str, Any]) -> str:
    token = token_mint(row)
    if token:
        return token
    params = row.get("params") if isinstance(row.get("params"), dict) else {}
    return token_mint(params)


def nested_result(row: dict[str, Any]) -> dict[str, Any]:
    result = row.get("result")
    return result if isinstance(result, dict) else row


def parsed_mint_info(row: dict[str, Any]) -> dict[str, Any]:
    result = nested_result(row)
    value = as_dict(result.get("value"))
    data = value.get("data")
    if isinstance(data, dict):
        parsed = as_dict(data.get("parsed"))
        return as_dict(parsed.get("info"))
    return {}


def snapshot_slot(row: dict[str, Any]) -> int | None:
    result = nested_result(row)
    context = as_dict(result.get("context"))
    slot = safe_int(row.get("slot", context.get("slot")), 0)
    return slot if slot > 0 else None


def snapshot_supply(row: dict[str, Any]) -> tuple[str | None, int | None, float | None]:
    info = parsed_mint_info(row)
    raw_supply = row.get("raw_supply", row.get("supply", info.get("supply")))
    decimals = row.get("decimals", info.get("decimals"))
    parsed_decimals = safe_int(decimals, -1)
    if raw_supply in (None, "") or parsed_decimals < 0:
        return None, None, None
    raw_supply_text = str(raw_supply)
    raw_supply_float = safe_float(raw_supply_text, None)
    if raw_supply_float is None or raw_supply_float < 0:
        return None, None, None
    ui_supply = raw_supply_float / (10**parsed_decimals)
    return raw_supply_text, parsed_decimals, ui_supply


def index_snapshots(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        token = snapshot_token(row)
        if token:
            indexed.setdefault(token, []).append(row)
    for token in indexed:
        indexed[token].sort(key=lambda row: snapshot_slot(row) or 0, reverse=True)
    return indexed


def best_snapshot_for_candidate(candidate: dict[str, Any], snapshots: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    decision_slot = safe_int(candidate.get("decision_slot"), 0)
    if decision_slot <= 0:
        return None, "missing_decision_slot"
    if not snapshots:
        return None, "missing_archival_snapshot"
    before_or_at = [row for row in snapshots if (snapshot_slot(row) or 0) <= decision_slot]
    if before_or_at:
        return before_or_at[0], "ok"
    return snapshots[-1], "snapshot_after_decision_slot"


def classify_candidate(candidate: dict[str, Any], snapshots_by_token: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    token = token_mint(candidate)
    decision_slot = safe_int(candidate.get("decision_slot"), 0)
    snapshot, reason = best_snapshot_for_candidate(candidate, snapshots_by_token.get(token, []))
    raw_supply = None
    decimals = None
    ui_supply = None
    snapshot_at = snapshot_slot(snapshot) if snapshot else None
    source = snapshot.get("source") if isinstance(snapshot, dict) else None
    source_file = snapshot.get("source_file") if isinstance(snapshot, dict) else None
    block_reasons: list[str] = []
    status = "archival_supply_recovered"

    if snapshot and reason == "ok":
        raw_supply, decimals, ui_supply = snapshot_supply(snapshot)
        if raw_supply is None or decimals is None or ui_supply is None:
            status = "blocked_invalid_archival_snapshot"
            block_reasons.append("invalid_supply_snapshot")
    elif reason == "snapshot_after_decision_slot":
        status = "blocked_snapshot_after_decision_slot"
        block_reasons.append("snapshot_slot_after_decision_slot")
    elif reason == "missing_decision_slot":
        status = "blocked_missing_decision_slot"
        block_reasons.append("missing_decision_slot")
    else:
        status = "blocked_missing_archival_snapshot"
        block_reasons.append("missing_archival_snapshot")

    return {
        "version": VERSION,
        "wallet": str(candidate.get("wallet") or "").strip(),
        "token_mint": token,
        "timestamp": safe_float(candidate.get("timestamp"), None),
        "transaction_signature": str(candidate.get("transaction_signature") or "").strip(),
        "decision_slot": decision_slot or None,
        "snapshot_slot": snapshot_at,
        "status": status,
        "source": source,
        "source_file": source_file,
        "decision_time_safe": status == "archival_supply_recovered",
        "raw_supply": raw_supply,
        "ui_supply": ui_supply,
        "decimals": decimals,
        "block_reasons": block_reasons,
        "can_mutate_wallet_trust": False,
    }


def build_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(row.get("status") or "unknown") for row in records)
    blocks = Counter(reason for row in records for reason in row.get("block_reasons") or [])
    return {
        "candidate_rows": len(records),
        "supply_recovered_records": statuses.get("archival_supply_recovered", 0),
        "blocked_missing_snapshot_records": statuses.get("blocked_missing_archival_snapshot", 0),
        "blocked_snapshot_after_decision_slot_records": statuses.get("blocked_snapshot_after_decision_slot", 0),
        "blocked_invalid_snapshot_records": statuses.get("blocked_invalid_archival_snapshot", 0),
        "status_counts": dict(sorted(statuses.items())),
        "block_reasons": dict(sorted(blocks.items())),
        "tokens_affected": len({row.get("token_mint") for row in records if row.get("token_mint")}),
        "tokens_recovered": len(
            {row.get("token_mint") for row in records if row.get("token_mint") and row.get("status") == "archival_supply_recovered"}
        ),
        "wallets_affected": len({row.get("wallet") for row in records if row.get("wallet")}),
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
    }


def build_archival_supply_evidence_report(
    *,
    archival_supply_plan: dict[str, Any],
    supply_snapshots: list[dict[str, Any]],
    generated_at: float | None = None,
) -> dict[str, Any]:
    snapshots_by_token = index_snapshots(supply_snapshots)
    records = [classify_candidate(row, snapshots_by_token) for row in candidate_rows(archival_supply_plan)]
    return {
        "generated_at": time.time() if generated_at is None else float(generated_at),
        "mode": MODE,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "summary": build_summary(records),
        "records": records,
        "operator_note": (
            "Archival supply evidence imports historical mint-account snapshots only. "
            "Snapshots after the candidate decision slot, current-only supply, and missing snapshots stay blocked."
        ),
    }
