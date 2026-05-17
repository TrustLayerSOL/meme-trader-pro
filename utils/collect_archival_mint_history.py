#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.env_loader import load_env  # noqa: E402
from utils.discover_candidate_wallets import SyncRpcClient  # noqa: E402
from wallets.archival_mint_history_collector import build_archival_mint_history_collection_report  # noqa: E402
from wallets.historical_market_context_backfill import relative_path  # noqa: E402


DEFAULT_PLAN_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_supply_recovery_plan.json"
DEFAULT_REPORT_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_mint_history_collection_report.json"
DEFAULT_RAW_TRANSACTIONS_PATH = ROOT / "data" / "wallet_backfills" / "raw_transactions" / "archival_mint_history_raw.jsonl"
DEFAULT_COMPLETENESS_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_mint_history_completeness.json"
DEFAULT_SIGNATURE_CHECKPOINT_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_mint_history_signature_checkpoint.json"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def write_archival_mint_history_collection_report(
    *,
    plan_path: Path | str = DEFAULT_PLAN_PATH,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    raw_transactions_path: Path | str = DEFAULT_RAW_TRANSACTIONS_PATH,
    completeness_path: Path | str = DEFAULT_COMPLETENESS_PATH,
    signature_checkpoint_path: Path | str = DEFAULT_SIGNATURE_CHECKPOINT_PATH,
    rpc: Any | None = None,
    execute: bool = False,
    signature_page_limit: int = 100,
    max_pages_per_mint: int = 5,
    max_transactions_per_mint: int = 500,
    max_targets: int | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    plan_path = Path(plan_path)
    report_path = Path(report_path)
    raw_transactions_path = Path(raw_transactions_path)
    completeness_path = Path(completeness_path)
    signature_checkpoint_path = Path(signature_checkpoint_path)
    report = build_archival_mint_history_collection_report(
        archival_supply_plan=read_json(plan_path, {"token_requirements": []}),
        rpc=rpc,
        execute=execute,
        signature_page_limit=signature_page_limit,
        max_pages_per_mint=max_pages_per_mint,
        max_transactions_per_mint=max_transactions_per_mint,
        max_targets=max_targets,
        existing_signature_checkpoint=read_json(signature_checkpoint_path, {}),
        generated_at=generated_at,
    )
    raw_rows = report.pop("raw_transactions", [])
    completeness = report.get("history_completeness") if isinstance(report.get("history_completeness"), dict) else {}
    signature_checkpoint = report.pop("signature_checkpoint", {})
    report["input_paths"] = {"plan": relative_path(plan_path, ROOT)}
    report["output_paths"] = {
        "report": relative_path(report_path, ROOT),
        "raw_transactions": relative_path(raw_transactions_path, ROOT),
        "history_completeness": relative_path(completeness_path, ROOT),
        "signature_checkpoint": relative_path(signature_checkpoint_path, ROOT),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    completeness_path.parent.mkdir(parents=True, exist_ok=True)
    signature_checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    completeness_path.write_text(json.dumps(completeness, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    signature_checkpoint_path.write_text(json.dumps(signature_checkpoint, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_jsonl(raw_transactions_path, raw_rows)
    report["raw_transactions"] = raw_rows
    report["signature_checkpoint"] = signature_checkpoint
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect read-only mint transaction history for archival supply reconstruction.")
    parser.add_argument("--execute", action="store_true", help="Fetch read-only signatures/transactions. Default is dry-run.")
    parser.add_argument("--plan-path", type=Path, default=DEFAULT_PLAN_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--raw-transactions-path", type=Path, default=DEFAULT_RAW_TRANSACTIONS_PATH)
    parser.add_argument("--completeness-path", type=Path, default=DEFAULT_COMPLETENESS_PATH)
    parser.add_argument("--signature-checkpoint-path", type=Path, default=DEFAULT_SIGNATURE_CHECKPOINT_PATH)
    parser.add_argument("--signature-page-limit", type=int, default=100)
    parser.add_argument("--max-pages-per-mint", type=int, default=5)
    parser.add_argument("--max-transactions-per-mint", type=int, default=500)
    parser.add_argument("--max-targets", type=int, default=None, help="Limit how many mint targets are processed in this run.")
    parser.add_argument("--rpc-timeout", type=int, default=15)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    load_env()
    rpc = SyncRpcClient(timeout=args.rpc_timeout) if args.execute else None
    report = write_archival_mint_history_collection_report(
        plan_path=args.plan_path,
        report_path=args.report_path,
        raw_transactions_path=args.raw_transactions_path,
        completeness_path=args.completeness_path,
        signature_checkpoint_path=args.signature_checkpoint_path,
        rpc=rpc,
        execute=args.execute,
        signature_page_limit=args.signature_page_limit,
        max_pages_per_mint=args.max_pages_per_mint,
        max_transactions_per_mint=args.max_transactions_per_mint,
        max_targets=args.max_targets,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
