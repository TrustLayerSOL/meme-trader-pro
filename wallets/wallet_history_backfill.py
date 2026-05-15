from __future__ import annotations

import time
from typing import Any

from wallets.wallet_evidence_models import replay_outcomes_by_mint
from wallets.wallet_evidence_reporter import summarize_wallet_report, wallet_metrics
from wallets.wallet_history_parser import parse_wallet_token_deltas


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def candidate_wallet_targets(backfill_targets: Any, *, max_wallets: int = 45) -> list[dict[str, Any]]:
    targets = []
    for row in as_dict(backfill_targets).get("targets") or []:
        if not isinstance(row, dict):
            continue
        if row.get("next_collection_step") != "COLLECT_WALLET_HISTORY":
            continue
        wallet = str(row.get("wallet") or "").strip()
        if not wallet:
            continue
        targets.append(row)
    targets.sort(key=lambda item: safe_float(item.get("priority_score")), reverse=True)
    return targets[:max(0, int(max_wallets))]


def rpc_call_failures(rpc: Any) -> list[dict[str, Any]]:
    failures = getattr(rpc, "failures", [])
    return failures if isinstance(failures, list) else []


def fetch_wallet_signatures(rpc: Any, wallet: str, signature_limit: int) -> list[dict[str, Any]]:
    result = rpc.call("getSignaturesForAddress", [wallet, {"limit": int(signature_limit)}])
    return result if isinstance(result, list) else []


def fetch_transaction(rpc: Any, signature: str) -> dict[str, Any] | None:
    result = rpc.call(
        "getTransaction",
        [
            signature,
            {
                "encoding": "jsonParsed",
                "maxSupportedTransactionVersion": 0,
                "commitment": "confirmed",
            },
        ],
    )
    return result if isinstance(result, dict) else None


def status_for_wallet(*, signature_count: int, tx_count: int, evidence_count: int, failures: list[dict[str, Any]]) -> tuple[str, str]:
    if failures and signature_count == 0:
        return "BLOCKED_RPC_ERROR", "blocked_rpc_error"
    if signature_count == 0:
        return "INSUFFICIENT_HISTORY", "insufficient_history"
    if evidence_count == 0:
        return "BLOCKED_MISSING_DATA", "blocked_missing_data"
    if tx_count < signature_count:
        return "PARTIAL_WALLET_HISTORY_COLLECTED", "partial_wallet_history_collected"
    return "COLLECTED", "wallet_history_collected"


def build_wallet_history_backfill_report(
    *,
    backfill_targets: Any,
    rpc: Any | None = None,
    replay_events: list[dict[str, Any]] | None = None,
    execute: bool = False,
    generated_at: float | None = None,
    max_wallets: int = 45,
    signature_limit: int = 40,
    max_transactions_per_wallet: int = 20,
    request_pause_seconds: float = 0.0,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    targets = candidate_wallet_targets(backfill_targets, max_wallets=max_wallets)
    outcome_by_mint = replay_outcomes_by_mint(replay_events or [])
    evidence_rows: list[dict[str, Any]] = []
    wallet_rows: list[dict[str, Any]] = []
    raw_transactions: list[dict[str, Any]] = []

    for target in targets:
        wallet = str(target.get("wallet") or "").strip()
        if not execute:
            wallet_rows.append({
                "wallet": wallet,
                "priority_score": safe_float(target.get("priority_score")),
                "status": "DRY_RUN",
                "target_status": "needs_wallet_history",
                "signatures_fetched": 0,
                "transactions_inspected": 0,
                "evidence_rows_created": 0,
                "next_action": "run with --execute to fetch read-only wallet history",
                "metrics": wallet_metrics(wallet, []),
            })
            continue

        if rpc is None:
            wallet_rows.append({
                "wallet": wallet,
                "priority_score": safe_float(target.get("priority_score")),
                "status": "BLOCKED_RPC_ERROR",
                "target_status": "blocked_rpc_error",
                "block_reason": "missing_rpc_client",
                "signatures_fetched": 0,
                "transactions_inspected": 0,
                "evidence_rows_created": 0,
                "metrics": wallet_metrics(wallet, []),
            })
            continue

        if request_pause_seconds > 0:
            time.sleep(request_pause_seconds)
        signatures = fetch_wallet_signatures(rpc, wallet, signature_limit)
        inspected = 0
        wallet_evidence: list[dict[str, Any]] = []
        for item in signatures[: max(0, int(max_transactions_per_wallet))]:
            signature = item.get("signature") if isinstance(item, dict) else None
            if not signature:
                continue
            if request_pause_seconds > 0:
                time.sleep(request_pause_seconds)
            tx = fetch_transaction(rpc, str(signature))
            if not isinstance(tx, dict):
                continue
            inspected += 1
            raw_transactions.append({"wallet": wallet, "signature": str(signature), "transaction": tx})
            wallet_evidence.extend(
                parse_wallet_token_deltas(
                    tx,
                    wallet=wallet,
                    signature=str(signature),
                    outcome_by_mint=outcome_by_mint,
                    risk_flags=target.get("risk_flags") if isinstance(target.get("risk_flags"), list) else [],
                )
            )

        evidence_rows.extend(wallet_evidence)
        status, target_status = status_for_wallet(
            signature_count=len(signatures),
            tx_count=inspected,
            evidence_count=len(wallet_evidence),
            failures=rpc_call_failures(rpc),
        )
        wallet_rows.append({
            "wallet": wallet,
            "priority_score": safe_float(target.get("priority_score")),
            "status": status,
            "target_status": target_status,
            "signatures_fetched": len(signatures),
            "transactions_inspected": inspected,
            "evidence_rows_created": len(wallet_evidence),
            "buy_events": sum(1 for row in wallet_evidence if row.get("observed_action") == "buy"),
            "sell_events": sum(1 for row in wallet_evidence if row.get("observed_action") == "sell"),
            "unique_mints": len({row.get("token_mint") for row in wallet_evidence if row.get("token_mint")}),
            "rpc_failures": rpc_call_failures(rpc),
            "metrics": wallet_metrics(wallet, wallet_evidence),
        })

    summary = summarize_wallet_report(wallet_rows, evidence_rows)
    summary["target_wallets"] = len(targets)
    summary["dry_run_wallets"] = sum(1 for row in wallet_rows if row.get("status") == "DRY_RUN")
    summary["ready_for_candidate_review"] = sum(
        1 for row in wallet_rows
        if as_dict(row.get("metrics")).get("minimum_additional_evidence_needed") == 0
        and row.get("target_status") in {"wallet_history_collected", "partial_wallet_history_collected"}
    )
    return {
        "generated_at": generated_at,
        "mode": "WALLET_HISTORY_BACKFILL_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "execute": bool(execute),
        "limits": {
            "max_wallets": max_wallets,
            "signature_limit": signature_limit,
            "max_transactions_per_wallet": max_transactions_per_wallet,
            "request_pause_seconds": request_pause_seconds,
        },
        "summary": summary,
        "wallets": wallet_rows,
        "evidence_records": evidence_rows,
        "raw_transactions": raw_transactions,
    }
