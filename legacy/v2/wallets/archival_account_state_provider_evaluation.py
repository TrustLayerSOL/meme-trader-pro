from __future__ import annotations

import time
from collections import Counter
from typing import Any

from wallets.wallet_evidence_models import safe_int


MODE = "ARCHIVAL_ACCOUNT_STATE_PROVIDER_EVALUATION_REVIEW_ONLY"
VERSION = "archival_account_state_provider_evaluation.v1"

SAFETY_CRITERIA = [
    "provider_response_must_be_at_or_before_decision_slot",
    "raw_provider_response_must_be_preserved",
    "mint_supply_must_come_from_historical_account_state_or_complete_mint_burn_history",
    "current_account_state_must_not_be_substituted_for_historical_state",
    "provider_probe_must_use_known_mint_and_known_decision_slot_before_import",
]

SOURCE_LINKS = {
    "helius_getaccountinfo": "https://helius.mintlify.app/api-reference/rpc/http/getaccountinfo",
    "helius_transaction_history": "https://www.helius.dev/docs/api-reference/enhanced-transactions/gettransactions",
    "quicknode_solana_docs": "https://www.quicknode.com/docs/solana",
    "solana_getaccountinfo": "https://solana.com/docs/rpc/http/getaccountinfo",
}


def summary_value(pagination_plan: dict[str, Any], key: str) -> int:
    summary = pagination_plan.get("summary") if isinstance(pagination_plan, dict) else {}
    return safe_int(summary.get(key), 0) if isinstance(summary, dict) else 0


def provider_rows(pagination_plan: dict[str, Any]) -> list[dict[str, Any]]:
    provider_recommended = summary_value(pagination_plan, "provider_recommended_tokens")
    tokens_planned = summary_value(pagination_plan, "tokens_planned")
    initial_pagination = summary_value(pagination_plan, "initial_pagination_tokens")
    continue_pagination = summary_value(pagination_plan, "continue_pagination_tokens")

    return [
        {
            "version": VERSION,
            "provider_id": "home_built_mint_history_reconstruction",
            "provider_type": "local_reconstruction_lane",
            "status": "active_but_incomplete",
            "can_unlock_archival_supply": False,
            "validated_for_supply_import": False,
            "manual_probe_required": False,
            "tokens_planned": tokens_planned,
            "initial_pagination_tokens": initial_pagination,
            "continue_pagination_tokens": continue_pagination,
            "provider_recommended_tokens": provider_recommended,
            "blockers": ["complete_mint_history_not_proven"],
            "recommended_next_action": "CONTINUE_BOUNDED_PAGINATION_OR_USE_PROVIDER_FOR_HIGH_COST_TARGETS",
            "source_links": [],
            "notes": "Safe local lane remains preferred, but high-activity mints may require too much pagination to prove complete history cheaply.",
        },
        {
            "version": VERSION,
            "provider_id": "helius_getaccountinfo_current_rpc",
            "provider_type": "current_or_incremental_account_rpc",
            "status": "not_sufficient_for_historical_supply_snapshot",
            "can_unlock_archival_supply": False,
            "validated_for_supply_import": False,
            "manual_probe_required": False,
            "blockers": ["does_not_prove_point_in_time_account_state"],
            "recommended_next_action": "DO_NOT_IMPORT_AS_HISTORICAL_SUPPLY",
            "source_links": [SOURCE_LINKS["helius_getaccountinfo"], SOURCE_LINKS["solana_getaccountinfo"]],
            "notes": "Useful RPC surface, but current/incremental account reads do not by themselves prove mint supply at a historical decision slot.",
        },
        {
            "version": VERSION,
            "provider_id": "quicknode_solana_mainnet_archive",
            "provider_type": "archival_rpc_candidate",
            "status": "candidate_needs_manual_probe",
            "can_unlock_archival_supply": False,
            "validated_for_supply_import": False,
            "manual_probe_required": True,
            "blockers": ["historical_account_state_semantics_unverified_locally"],
            "recommended_next_action": "RUN_ARCHIVAL_ACCOUNT_STATE_PROVIDER_PROBE",
            "source_links": [SOURCE_LINKS["quicknode_solana_docs"], SOURCE_LINKS["solana_getaccountinfo"]],
            "notes": "Candidate only. Before import, run a known mint/slot probe and reject any response whose context slot is after the requested decision slot.",
        },
    ]


def build_summary(rows: list[dict[str, Any]], pagination_plan: dict[str, Any]) -> dict[str, Any]:
    statuses = Counter(str(row.get("status") or "unknown") for row in rows)
    return {
        "providers_evaluated": len(rows),
        "candidate_providers": statuses.get("candidate_needs_manual_probe", 0),
        "providers_rejected": statuses.get("not_sufficient_for_historical_supply_snapshot", 0),
        "active_local_lanes": statuses.get("active_but_incomplete", 0),
        "provider_probe_required": statuses.get("candidate_needs_manual_probe", 0) > 0,
        "tokens_planned": summary_value(pagination_plan, "tokens_planned"),
        "provider_recommended_tokens": summary_value(pagination_plan, "provider_recommended_tokens"),
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
        "status_counts": dict(sorted(statuses.items())),
    }


def build_archival_account_state_provider_evaluation_report(
    *,
    pagination_plan: dict[str, Any],
    generated_at: float | None = None,
) -> dict[str, Any]:
    rows = provider_rows(pagination_plan)
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
        "safety_criteria": SAFETY_CRITERIA,
        "source_links": SOURCE_LINKS,
        "summary": build_summary(rows, pagination_plan),
        "providers": rows,
        "operator_note": (
            "This report does not choose or call a provider. It records which provider lanes are candidates "
            "for historical mint supply validation and preserves the rule that current account state cannot "
            "be substituted for decision-time state."
        ),
    }
