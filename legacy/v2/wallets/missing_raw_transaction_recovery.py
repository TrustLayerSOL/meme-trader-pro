from __future__ import annotations

import time
from collections import Counter, defaultdict
from typing import Any

from wallets.wallet_evidence_models import as_dict, safe_float


MODE = "MISSING_RAW_TRANSACTION_RECOVERY_REVIEW_ONLY"
RECOVERY_VERSION = "missing_raw_transaction_recovery.v1"


def missing_transaction_targets(historical_backfill_report: Any) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    wallets_by_signature: dict[str, set[str]] = defaultdict(set)
    mints_by_signature: dict[str, set[str]] = defaultdict(set)
    timestamps_by_signature: dict[str, list[float]] = defaultdict(list)
    for row in as_dict(historical_backfill_report).get("records") or []:
        if not isinstance(row, dict) or row.get("status") != "blocked_missing_transaction":
            continue
        signature = str(row.get("transaction_signature") or "").strip()
        if not signature:
            continue
        grouped.setdefault(
            signature,
            {
                "transaction_signature": signature,
                "status": "pending",
            },
        )
        wallet = str(row.get("wallet") or "").strip()
        mint = str(row.get("token_mint") or "").strip()
        timestamp = safe_float(row.get("timestamp"), None)
        if wallet:
            wallets_by_signature[signature].add(wallet)
        if mint:
            mints_by_signature[signature].add(mint)
        if timestamp is not None:
            timestamps_by_signature[signature].append(timestamp)

    targets = []
    for signature in sorted(grouped):
        timestamps = timestamps_by_signature.get(signature) or []
        target = dict(grouped[signature])
        target["wallets"] = sorted(wallets_by_signature.get(signature) or [])
        target["wallet"] = target["wallets"][0] if target["wallets"] else None
        target["token_mints"] = sorted(mints_by_signature.get(signature) or [])
        target["first_timestamp"] = min(timestamps) if timestamps else None
        target["last_timestamp"] = max(timestamps) if timestamps else None
        targets.append(target)
    return targets


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


def rpc_failures(rpc: Any) -> list[dict[str, Any]]:
    failures = getattr(rpc, "failures", [])
    return failures if isinstance(failures, list) else []


def build_missing_raw_transaction_recovery_report(
    *,
    historical_backfill_report: Any,
    rpc: Any | None = None,
    execute: bool = False,
    generated_at: float | None = None,
    request_pause_seconds: float = 0.0,
    limit: int | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    targets = missing_transaction_targets(historical_backfill_report)
    if limit is not None:
        targets = targets[: max(0, int(limit))]

    rows: list[dict[str, Any]] = []
    raw_transactions: list[dict[str, Any]] = []
    for target in targets:
        row = dict(target)
        if not execute:
            row["status"] = "dry_run"
            row["next_action"] = "run with --execute to fetch read-only getTransaction history"
            rows.append(row)
            continue
        if rpc is None:
            row["status"] = "blocked_rpc_error"
            row["block_reason"] = "missing_rpc_client"
            rows.append(row)
            continue
        if request_pause_seconds > 0:
            time.sleep(request_pause_seconds)
        signature = str(target.get("transaction_signature") or "")
        transaction = fetch_transaction(rpc, signature)
        if transaction:
            row["status"] = "recovered"
            row["block_reason"] = None
            raw_transactions.append(
                {
                    "recovery_version": RECOVERY_VERSION,
                    "wallet": row.get("wallet"),
                    "wallets": row.get("wallets") or [],
                    "token_mints": row.get("token_mints") or [],
                    "signature": signature,
                    "transaction": transaction,
                }
            )
        else:
            row["status"] = "blocked_missing_transaction"
            row["block_reason"] = "rpc_returned_no_transaction"
            failures = rpc_failures(rpc)
            if failures:
                row["rpc_failures"] = failures[:3]
        rows.append(row)

    return {
        "generated_at": generated_at,
        "mode": MODE,
        "review_only": True,
        "live_execution_locked": True,
        "execute": bool(execute),
        "recovery_version": RECOVERY_VERSION,
        "summary": build_summary(rows, raw_transactions),
        "targets": rows,
        "raw_transactions": raw_transactions,
    }


def build_summary(targets: list[dict[str, Any]], raw_transactions: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(row.get("status") or "unknown") for row in targets)
    return {
        "targets": len(targets),
        "dry_run_targets": statuses.get("dry_run", 0),
        "transactions_recovered": statuses.get("recovered", 0),
        "transactions_blocked": sum(count for status, count in statuses.items() if status.startswith("blocked_")),
        "status_counts": dict(sorted(statuses.items())),
        "raw_transactions_preserved": len(raw_transactions),
        "wallets_affected": len({wallet for row in targets for wallet in row.get("wallets") or []}),
        "tokens_affected": len({mint for row in targets for mint in row.get("token_mints") or []}),
    }
