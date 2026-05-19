#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wallets.historical_market_context_backfill import relative_path  # noqa: E402


DEFAULT_PLAN_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_supply_recovery_plan.json"
DEFAULT_REPORT_PATH = ROOT / "data" / "reports" / "historical_backfill" / "current_mint_supply_collection_report.json"
DEFAULT_SNAPSHOTS_PATH = ROOT / "data" / "reports" / "historical_backfill" / "current_mint_supply_snapshots.jsonl"
DEFAULT_RPC_URL = "https://api.mainnet-beta.solana.com"


class JsonRpcClient:
    def __init__(self, rpc_url: str, *, timeout: float = 15.0, sleep_seconds: float = 0.05):
        self.rpc_url = rpc_url
        self.timeout = timeout
        self.sleep_seconds = sleep_seconds
        self.request_id = 0

    def call(self, method: str, params: list[Any]) -> dict[str, Any]:
        self.request_id += 1
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params,
        }).encode("utf-8")
        request = urllib.request.Request(
            self.rpc_url,
            data=payload,
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def get_token_supply(self, mint: str) -> dict[str, Any]:
        if self.sleep_seconds > 0:
            time.sleep(self.sleep_seconds)
        return self.call("getTokenSupply", [mint, {"commitment": "finalized"}])


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def ready_mints(plan: dict[str, Any]) -> list[str]:
    rows = plan.get("token_requirements") if isinstance(plan, dict) else []
    mints = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if row.get("status") != "ready_for_archival_supply_fetch":
            continue
        mint = str(row.get("token_mint") or row.get("mint") or "").strip()
        if mint:
            mints.append(mint)
    return list(dict.fromkeys(mints))


def parse_supply_response(mint: str, response: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not isinstance(response, dict) or response.get("error"):
        return None, {
            "token_mint": mint,
            "status": "blocked_rpc_error",
            "error": str((response or {}).get("error") or "missing_rpc_response"),
        }
    result = response.get("result") if isinstance(response.get("result"), dict) else {}
    context = result.get("context") if isinstance(result.get("context"), dict) else {}
    value = result.get("value") if isinstance(result.get("value"), dict) else {}
    raw_supply = value.get("amount")
    decimals = value.get("decimals")
    slot = context.get("slot")
    if raw_supply in (None, "") or not isinstance(decimals, int) or not isinstance(slot, int):
        return None, {
            "token_mint": mint,
            "status": "blocked_invalid_supply_response",
            "error": "missing_amount_decimals_or_slot",
        }
    return {
        "version": "current_mint_supply_snapshot.v1",
        "token_mint": mint,
        "slot": slot,
        "raw_supply": str(raw_supply),
        "decimals": decimals,
        "ui_supply": value.get("uiAmount"),
        "ui_amount_string": str(value.get("uiAmountString") or ""),
        "source": "current_getTokenSupply",
        "decision_time_safe": False,
        "can_mutate_wallet_trust": False,
        "collected_at": time.time(),
    }, None


def should_retry_error(message: str) -> bool:
    lowered = message.lower()
    return "429" in lowered or "too many requests" in lowered or "rate" in lowered


def build_current_mint_supply_snapshots(
    archival_supply_plan: dict[str, Any],
    rpc: Any,
    *,
    generated_at: float | None = None,
    limit: int | None = None,
    retry_attempts: int = 3,
    retry_sleep_seconds: float = 1.0,
) -> dict[str, Any]:
    targets = ready_mints(archival_supply_plan)
    if limit is not None:
        targets = targets[: max(0, int(limit))]
    snapshots: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for mint in targets:
        response: dict[str, Any] | None = None
        last_error = ""
        for attempt in range(max(1, int(retry_attempts))):
            try:
                response = rpc.get_token_supply(mint)
            except Exception as exc:
                response = None
                last_error = str(exc)
            if response and not response.get("error"):
                break
            if response and response.get("error"):
                last_error = str(response.get("error"))
                if not should_retry_error(last_error):
                    break
            elif last_error and not should_retry_error(last_error):
                break
            if attempt < max(1, int(retry_attempts)) - 1 and retry_sleep_seconds > 0:
                time.sleep(retry_sleep_seconds)
        if response is None:
            response = {"error": {"message": last_error or "missing_rpc_response"}}
        snapshot, error = parse_supply_response(mint, response)
        if snapshot:
            snapshots.append(snapshot)
        if error:
            blocked.append(error)
    statuses = Counter(str(row.get("status") or "unknown") for row in blocked)
    return {
        "generated_at": time.time() if generated_at is None else float(generated_at),
        "mode": "CURRENT_MINT_SUPPLY_COLLECTION_REVIEW_ONLY",
        "review_only": True,
        "read_only": True,
        "live_execution_locked": True,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "summary": {
            "tokens_requested": len(targets),
            "snapshots_collected": len(snapshots),
            "blocked_rows": len(blocked),
            "blocked_rpc_error": statuses.get("blocked_rpc_error", 0),
            "blocked_invalid_supply_response": statuses.get("blocked_invalid_supply_response", 0),
            "status_counts": dict(sorted(statuses.items())),
        },
        "snapshots": snapshots,
        "blocked": blocked,
        "operator_note": (
            "Current supply snapshots are not decision-time safe by themselves. They can only support replay proof "
            "through the supply-stability evidence lane when post-decision mint/burn history is complete."
        ),
    }


def rpc_url_from_env() -> str:
    explicit = os.getenv("SOLANA_RPC_URL") or os.getenv("HELIUS_RPC_URL")
    if explicit:
        return explicit
    helius_key = os.getenv("HELIUS_API_KEY")
    if helius_key:
        return f"https://mainnet.helius-rpc.com/?api-key={helius_key}"
    return DEFAULT_RPC_URL


def write_current_mint_supply_snapshots(
    *,
    plan_path: Path | str = DEFAULT_PLAN_PATH,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    snapshots_path: Path | str = DEFAULT_SNAPSHOTS_PATH,
    rpc: Any | None = None,
    limit: int | None = None,
    retry_attempts: int = 3,
    retry_sleep_seconds: float = 1.0,
    generated_at: float | None = None,
) -> dict[str, Any]:
    plan_path = Path(plan_path)
    report_path = Path(report_path)
    snapshots_path = Path(snapshots_path)
    rpc = rpc or JsonRpcClient(rpc_url_from_env())
    report = build_current_mint_supply_snapshots(
        read_json(plan_path, {"token_requirements": []}),
        rpc,
        generated_at=generated_at,
        limit=limit,
        retry_attempts=retry_attempts,
        retry_sleep_seconds=retry_sleep_seconds,
    )
    report["input_paths"] = {"plan": relative_path(plan_path, ROOT)}
    report["output_paths"] = {
        "report": relative_path(report_path, ROOT),
        "snapshots": relative_path(snapshots_path, ROOT),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    snapshots_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with snapshots_path.open("w", encoding="utf-8") as handle:
        for snapshot in report.get("snapshots") or []:
            snapshot = {**snapshot, "source_file": relative_path(snapshots_path, ROOT)}
            handle.write(json.dumps(snapshot, sort_keys=True) + "\n")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect current getTokenSupply snapshots for archival supply targets.")
    parser.add_argument("--plan-path", type=Path, default=DEFAULT_PLAN_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--snapshots-path", type=Path, default=DEFAULT_SNAPSHOTS_PATH)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--retry-attempts", type=int, default=4)
    parser.add_argument("--retry-sleep-seconds", type=float, default=2.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_current_mint_supply_snapshots(
        plan_path=args.plan_path,
        report_path=args.report_path,
        snapshots_path=args.snapshots_path,
        limit=args.limit,
        retry_attempts=args.retry_attempts,
        retry_sleep_seconds=args.retry_sleep_seconds,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
