from __future__ import annotations

import time
from collections import Counter
from typing import Any

from wallets.wallet_history_backfill import rpc_call_failures
from wallets.wallet_history_parser import parse_wallet_token_deltas


MODE = "FORWARD_WALLET_ACTIVITY_REVIEW_ONLY"
FORWARD_OUTCOME_SOURCE = "forward_wallet_activity"


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


def wallet_address(row: Any) -> str:
    if isinstance(row, str):
        return row.strip()
    if not isinstance(row, dict):
        return ""
    for key in ("wallet", "address", "wallet_address", "owner"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def paper_watch_rows(paper_watch_wallets: Any) -> list[Any]:
    if isinstance(paper_watch_wallets, dict):
        rows = paper_watch_wallets.get("wallets")
        return rows if isinstance(rows, list) else []
    return paper_watch_wallets if isinstance(paper_watch_wallets, list) else []


def select_forward_wallets(
    *,
    tracked_wallets: Any,
    paper_watch_wallets: Any,
    max_wallets: int = 100,
) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for source_rows in (tracked_wallets if isinstance(tracked_wallets, list) else [], paper_watch_rows(paper_watch_wallets)):
        for row in source_rows:
            wallet = wallet_address(row)
            if not wallet or wallet in seen:
                continue
            seen.add(wallet)
            out.append(wallet)
            if len(out) >= max(0, int(max_wallets)):
                return out
    return out


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


def pending_forward_outcome() -> dict[str, Any]:
    return {
        "source": FORWARD_OUTCOME_SOURCE,
        "outcome_type": "pending_forward_outcome",
        "runner": False,
        "rug": False,
        "dead": False,
        "windows": {},
    }


def tag_forward_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tagged = []
    for row in rows:
        next_row = dict(row)
        next_row["collection_source"] = FORWARD_OUTCOME_SOURCE
        next_row["forward_observation"] = True
        next_row["later_token_outcome"] = pending_forward_outcome()
        risk_flags = list(next_row.get("risk_flags") or [])
        if "forward_current_activity" not in risk_flags:
            risk_flags.append("forward_current_activity")
        next_row["risk_flags"] = risk_flags
        missing = [field for field in next_row.get("missing_fields") or [] if field != "later_token_outcome"]
        next_row["missing_fields"] = missing
        tagged.append(next_row)
    return tagged


def build_forward_wallet_activity_report(
    *,
    tracked_wallets: Any,
    paper_watch_wallets: Any,
    rpc: Any | None = None,
    generated_at: float | None = None,
    lookback_seconds: int = 86400,
    execute: bool = False,
    max_wallets: int = 100,
    signature_limit: int = 40,
    max_transactions_per_wallet: int = 20,
    request_pause_seconds: float = 0.0,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    cutoff = generated_at - max(0, int(lookback_seconds))
    wallets = select_forward_wallets(
        tracked_wallets=tracked_wallets,
        paper_watch_wallets=paper_watch_wallets,
        max_wallets=max_wallets,
    )
    wallet_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    raw_transactions: list[dict[str, Any]] = []
    old_signatures_skipped = 0

    for wallet in wallets:
        if not execute:
            wallet_rows.append({
                "wallet": wallet,
                "status": "DRY_RUN",
                "signatures_fetched": 0,
                "transactions_inspected": 0,
                "evidence_rows_created": 0,
                "next_action": "run with --execute to collect recent read-only wallet activity",
            })
            continue
        if rpc is None:
            wallet_rows.append({
                "wallet": wallet,
                "status": "BLOCKED_RPC_ERROR",
                "block_reason": "missing_rpc_client",
                "signatures_fetched": 0,
                "transactions_inspected": 0,
                "evidence_rows_created": 0,
            })
            continue

        if request_pause_seconds > 0:
            time.sleep(request_pause_seconds)
        signatures = fetch_wallet_signatures(rpc, wallet, signature_limit)
        wallet_evidence: list[dict[str, Any]] = []
        inspected = 0
        for item in signatures[: max(0, int(max_transactions_per_wallet))]:
            signature = str(as_dict(item).get("signature") or "").strip()
            block_time = safe_float(as_dict(item).get("blockTime"))
            if block_time and block_time < cutoff:
                old_signatures_skipped += 1
                continue
            if not signature:
                continue
            if request_pause_seconds > 0:
                time.sleep(request_pause_seconds)
            tx = fetch_transaction(rpc, signature)
            if not isinstance(tx, dict):
                continue
            tx_time = safe_float(tx.get("blockTime"), block_time)
            if tx_time and tx_time < cutoff:
                old_signatures_skipped += 1
                continue
            inspected += 1
            raw_transactions.append({"wallet": wallet, "signature": signature, "transaction": tx})
            wallet_evidence.extend(tag_forward_rows(parse_wallet_token_deltas(tx, wallet=wallet, signature=signature)))

        evidence_rows.extend(wallet_evidence)
        status = "COLLECTED" if wallet_evidence else "NO_RECENT_TOKEN_ACTIVITY"
        if rpc_call_failures(rpc) and not signatures:
            status = "BLOCKED_RPC_ERROR"
        wallet_rows.append({
            "wallet": wallet,
            "status": status,
            "signatures_fetched": len(signatures),
            "transactions_inspected": inspected,
            "evidence_rows_created": len(wallet_evidence),
            "buy_events": sum(1 for row in wallet_evidence if row.get("observed_action") == "buy"),
            "sell_events": sum(1 for row in wallet_evidence if row.get("observed_action") == "sell"),
            "unique_mints": len({row.get("token_mint") for row in wallet_evidence if row.get("token_mint")}),
            "rpc_failures": rpc_call_failures(rpc),
        })

    statuses = Counter(str(row.get("status") or "UNKNOWN") for row in wallet_rows)
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "review_only": True,
        "live_execution_locked": True,
        "execute": bool(execute),
        "collection_window": {
            "lookback_seconds": int(lookback_seconds),
            "cutoff_epoch": cutoff,
        },
        "limits": {
            "max_wallets": max_wallets,
            "signature_limit": signature_limit,
            "max_transactions_per_wallet": max_transactions_per_wallet,
            "request_pause_seconds": request_pause_seconds,
        },
        "summary": {
            "wallets_selected": len(wallets),
            "wallets_processed": len(wallet_rows),
            "dry_run_wallets": statuses["DRY_RUN"],
            "wallets_collected": statuses["COLLECTED"],
            "wallets_without_recent_token_activity": statuses["NO_RECENT_TOKEN_ACTIVITY"],
            "wallets_blocked_rpc_error": statuses["BLOCKED_RPC_ERROR"],
            "evidence_rows_created": len(evidence_rows),
            "raw_transactions_preserved": len(raw_transactions),
            "old_signatures_skipped": old_signatures_skipped,
        },
        "wallets": wallet_rows,
        "evidence_records": evidence_rows,
        "raw_transactions": raw_transactions,
    }
