from __future__ import annotations

import time
from collections import Counter
from typing import Any

from wallets.wallet_history_backfill import rpc_call_failures
from wallets.wallet_history_parser import parse_wallet_token_deltas


MODE = "FORWARD_WALLET_ACTIVITY_REVIEW_ONLY"
FORWARD_OUTCOME_SOURCE = "forward_wallet_activity"
DEFAULT_MAX_RPC_CALLS_PER_CYCLE = 2500
DEFAULT_MAX_RPC_CALLS_PER_DAY = 120000
DEFAULT_FORWARD_MAX_WALLETS = 50
DEFAULT_ADAPTIVE_DEGRADED_MAX_WALLETS = 10


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
    max_wallets: int = DEFAULT_FORWARD_MAX_WALLETS,
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


def estimate_api_budget(
    *,
    selected_wallets: int,
    signature_limit: int,
    max_transactions_per_wallet: int,
    interval_seconds: int | None = None,
    max_rpc_calls_per_cycle: int = DEFAULT_MAX_RPC_CALLS_PER_CYCLE,
    max_rpc_calls_per_day: int = DEFAULT_MAX_RPC_CALLS_PER_DAY,
) -> dict[str, Any]:
    wallets = max(0, int(selected_wallets))
    per_wallet_calls = 1 + max(0, min(int(signature_limit), int(max_transactions_per_wallet)))
    estimated_cycle = wallets * per_wallet_calls
    interval = int(interval_seconds or 0)
    projected_day = int((estimated_cycle * 86400) / interval) if interval > 0 else None

    execute_allowed = True
    status = "within_budget"
    block_reason = None
    if estimated_cycle > int(max_rpc_calls_per_cycle):
        execute_allowed = False
        status = "blocked_cycle_limit"
        block_reason = "estimated_rpc_calls_per_cycle_exceeds_limit"
    elif projected_day is not None and projected_day > int(max_rpc_calls_per_day):
        execute_allowed = False
        status = "blocked_daily_limit"
        block_reason = "projected_rpc_calls_per_day_exceeds_limit"

    return {
        "selected_wallets": wallets,
        "per_wallet_estimated_rpc_calls": per_wallet_calls,
        "estimated_rpc_calls_per_cycle": estimated_cycle,
        "interval_seconds": interval if interval > 0 else None,
        "projected_rpc_calls_per_day": projected_day,
        "max_rpc_calls_per_cycle": int(max_rpc_calls_per_cycle),
        "max_rpc_calls_per_day": int(max_rpc_calls_per_day),
        "budget_status": status,
        "block_reason": block_reason,
        "execute_allowed": execute_allowed,
    }


def build_rpc_preflight_report(*, rpc: Any | None, execute: bool = False) -> dict[str, Any]:
    if not execute:
        return {
            "status": "skipped_dry_run",
            "execute_allowed": True,
            "successful_probes": 0,
            "failure_count": 0,
            "failures": [],
        }
    if rpc is None:
        return {
            "status": "blocked_missing_rpc_client",
            "execute_allowed": False,
            "successful_probes": 0,
            "failure_count": 0,
            "failures": [],
        }

    result = rpc.call("getSlot", [])
    failures = rpc_call_failures(rpc)
    if result is None:
        return {
            "status": "blocked_unhealthy",
            "execute_allowed": False,
            "successful_probes": 0,
            "failure_count": len(failures),
            "failures": failures[:5],
        }

    return {
        "status": "degraded" if failures else "healthy",
        "execute_allowed": True,
        "successful_probes": 1,
        "failure_count": len(failures),
        "failures": failures[:5],
    }


def adaptive_wallet_limit(
    *,
    requested_max_wallets: int,
    rpc_preflight: dict[str, Any],
    adaptive_free_rpc_throttle: bool = False,
    adaptive_degraded_max_wallets: int = DEFAULT_ADAPTIVE_DEGRADED_MAX_WALLETS,
) -> int:
    requested = max(0, int(requested_max_wallets))
    if not adaptive_free_rpc_throttle:
        return requested
    if rpc_preflight.get("status") != "degraded":
        return requested
    return min(requested, max(1, int(adaptive_degraded_max_wallets)))


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
    max_wallets: int = DEFAULT_FORWARD_MAX_WALLETS,
    signature_limit: int = 40,
    max_transactions_per_wallet: int = 20,
    request_pause_seconds: float = 0.0,
    interval_seconds: int | None = None,
    max_rpc_calls_per_cycle: int = DEFAULT_MAX_RPC_CALLS_PER_CYCLE,
    max_rpc_calls_per_day: int = DEFAULT_MAX_RPC_CALLS_PER_DAY,
    rpc_preflight: bool = False,
    adaptive_free_rpc_throttle: bool = False,
    adaptive_degraded_max_wallets: int = DEFAULT_ADAPTIVE_DEGRADED_MAX_WALLETS,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    cutoff = generated_at - max(0, int(lookback_seconds))
    preflight = build_rpc_preflight_report(rpc=rpc, execute=execute) if rpc_preflight else {
        "status": "disabled",
        "execute_allowed": True,
        "successful_probes": 0,
        "failure_count": 0,
        "failures": [],
    }
    effective_max_wallets = adaptive_wallet_limit(
        requested_max_wallets=max_wallets,
        rpc_preflight=preflight,
        adaptive_free_rpc_throttle=adaptive_free_rpc_throttle,
        adaptive_degraded_max_wallets=adaptive_degraded_max_wallets,
    )
    wallets = select_forward_wallets(
        tracked_wallets=tracked_wallets,
        paper_watch_wallets=paper_watch_wallets,
        max_wallets=effective_max_wallets,
    )
    requested_wallets = select_forward_wallets(
        tracked_wallets=tracked_wallets,
        paper_watch_wallets=paper_watch_wallets,
        max_wallets=max_wallets,
    )
    api_budget = estimate_api_budget(
        selected_wallets=len(wallets),
        signature_limit=signature_limit,
        max_transactions_per_wallet=max_transactions_per_wallet,
        interval_seconds=interval_seconds,
        max_rpc_calls_per_cycle=max_rpc_calls_per_cycle,
        max_rpc_calls_per_day=max_rpc_calls_per_day,
    )
    wallet_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    raw_transactions: list[dict[str, Any]] = []
    old_signatures_skipped = 0

    if execute and not preflight["execute_allowed"]:
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
                "requested_max_wallets": max_wallets,
                "max_wallets": effective_max_wallets,
                "signature_limit": signature_limit,
                "max_transactions_per_wallet": max_transactions_per_wallet,
                "request_pause_seconds": request_pause_seconds,
                "max_rpc_calls_per_cycle": max_rpc_calls_per_cycle,
                "max_rpc_calls_per_day": max_rpc_calls_per_day,
                "rpc_preflight": bool(rpc_preflight),
                "adaptive_free_rpc_throttle": bool(adaptive_free_rpc_throttle),
                "adaptive_degraded_max_wallets": int(adaptive_degraded_max_wallets),
            },
            "rpc_preflight": preflight,
            "api_budget": api_budget,
            "summary": {
                "wallets_selected": len(requested_wallets),
                "wallets_processed": 0,
                "dry_run_wallets": 0,
                "wallets_collected": 0,
                "wallets_without_recent_token_activity": 0,
                "wallets_blocked_rpc_error": 0,
                "wallets_blocked_rpc_preflight": len(requested_wallets),
                "wallets_blocked_api_budget": 0,
                "wallets_throttled_by_rpc_preflight": 0,
                "evidence_rows_created": 0,
                "raw_transactions_preserved": 0,
                "old_signatures_skipped": 0,
            },
            "wallets": [
                {
                    "wallet": wallet,
                    "status": "BLOCKED_RPC_PREFLIGHT",
                    "block_reason": preflight["status"],
                    "signatures_fetched": 0,
                    "transactions_inspected": 0,
                    "evidence_rows_created": 0,
                }
                for wallet in requested_wallets
            ],
            "evidence_records": [],
            "raw_transactions": [],
            "next_actions": [
                "RPC preflight failed; skip this collection cycle instead of scanning wallets through an unhealthy public provider.",
                "Retry later, lower max_wallets, or provide an explicitly approved provider before broader collection.",
            ],
        }

    if execute and not api_budget["execute_allowed"]:
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
                "requested_max_wallets": max_wallets,
                "max_wallets": effective_max_wallets,
                "signature_limit": signature_limit,
                "max_transactions_per_wallet": max_transactions_per_wallet,
                "request_pause_seconds": request_pause_seconds,
                "max_rpc_calls_per_cycle": max_rpc_calls_per_cycle,
                "max_rpc_calls_per_day": max_rpc_calls_per_day,
                "rpc_preflight": bool(rpc_preflight),
                "adaptive_free_rpc_throttle": bool(adaptive_free_rpc_throttle),
                "adaptive_degraded_max_wallets": int(adaptive_degraded_max_wallets),
            },
            "rpc_preflight": preflight,
            "api_budget": api_budget,
            "summary": {
                "wallets_selected": len(wallets),
                "wallets_processed": 0,
                "dry_run_wallets": 0,
                "wallets_collected": 0,
                "wallets_without_recent_token_activity": 0,
                "wallets_blocked_rpc_error": 0,
                "wallets_blocked_rpc_preflight": 0,
                "wallets_blocked_api_budget": len(wallets),
                "wallets_throttled_by_rpc_preflight": max(0, len(requested_wallets) - len(wallets)),
                "evidence_rows_created": 0,
                "raw_transactions_preserved": 0,
                "old_signatures_skipped": 0,
            },
            "wallets": [
                {
                    "wallet": wallet,
                    "status": "BLOCKED_API_BUDGET",
                    "block_reason": api_budget["block_reason"],
                    "signatures_fetched": 0,
                    "transactions_inspected": 0,
                    "evidence_rows_created": 0,
                }
                for wallet in wallets
            ],
            "evidence_records": [],
            "raw_transactions": [],
            "next_actions": [
                "Reduce the forward wallet activity api budget by lowering max_wallets, signature_limit, max_transactions_per_wallet, or run frequency.",
                "Use slower rotation for lower-priority wallets instead of scanning the full watch list every cycle.",
            ],
        }

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
            "requested_max_wallets": max_wallets,
            "max_wallets": effective_max_wallets,
            "signature_limit": signature_limit,
            "max_transactions_per_wallet": max_transactions_per_wallet,
            "request_pause_seconds": request_pause_seconds,
            "max_rpc_calls_per_cycle": max_rpc_calls_per_cycle,
            "max_rpc_calls_per_day": max_rpc_calls_per_day,
            "rpc_preflight": bool(rpc_preflight),
            "adaptive_free_rpc_throttle": bool(adaptive_free_rpc_throttle),
            "adaptive_degraded_max_wallets": int(adaptive_degraded_max_wallets),
        },
        "rpc_preflight": preflight,
        "api_budget": api_budget,
        "summary": {
            "wallets_selected": len(wallets),
            "wallets_processed": len(wallet_rows),
            "dry_run_wallets": statuses["DRY_RUN"],
            "wallets_collected": statuses["COLLECTED"],
            "wallets_without_recent_token_activity": statuses["NO_RECENT_TOKEN_ACTIVITY"],
            "wallets_blocked_rpc_error": statuses["BLOCKED_RPC_ERROR"],
            "wallets_blocked_rpc_preflight": 0,
            "wallets_blocked_api_budget": statuses["BLOCKED_API_BUDGET"],
            "wallets_throttled_by_rpc_preflight": max(0, len(requested_wallets) - len(wallets)),
            "evidence_rows_created": len(evidence_rows),
            "raw_transactions_preserved": len(raw_transactions),
            "old_signatures_skipped": old_signatures_skipped,
        },
        "wallets": wallet_rows,
        "evidence_records": evidence_rows,
        "raw_transactions": raw_transactions,
    }
