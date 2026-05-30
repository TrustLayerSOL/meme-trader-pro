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
from utils.collect_archival_mint_history import merge_raw_rows, read_json, read_jsonl, write_jsonl  # noqa: E402
from utils.discover_candidate_wallets import SyncRpcClient  # noqa: E402
from wallets.historical_market_context_backfill import relative_path  # noqa: E402
from wallets.post_decision_transaction_body_collector import (  # noqa: E402
    build_post_decision_supply_transaction_collection_report,
)


DEFAULT_PLAN_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_supply_recovery_plan.json"
DEFAULT_CURRENT_SUPPLY_SNAPSHOTS_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "current_mint_supply_snapshots.jsonl"
)
DEFAULT_SIGNATURE_CHECKPOINT_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "post_decision_supply_signature_checkpoint.json"
)
DEFAULT_BASE_SIGNATURE_CHECKPOINT_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "archival_mint_history_signature_checkpoint.json"
)
DEFAULT_RAW_TRANSACTIONS_PATH = ROOT / "data" / "wallet_backfills" / "raw_transactions" / "archival_mint_history_raw.jsonl"
DEFAULT_POST_DECISION_RAW_TRANSACTIONS_PATH = (
    ROOT / "data" / "wallet_backfills" / "raw_transactions" / "post_decision_supply_transactions.jsonl"
)
DEFAULT_EXISTING_RAW_GLOB = str(ROOT / "data" / "wallet_backfills" / "raw_transactions" / "*.jsonl")
DEFAULT_REPORT_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "post_decision_supply_transaction_collection_report.json"
)


def expand_existing_raw_paths(raw_glob: str | None) -> list[Path]:
    if not raw_glob:
        return []
    import glob

    return [Path(path) for path in sorted(glob.glob(raw_glob))]


def write_post_decision_supply_transaction_collection_report(
    *,
    plan_path: Path | str = DEFAULT_PLAN_PATH,
    current_supply_snapshots_path: Path | str = DEFAULT_CURRENT_SUPPLY_SNAPSHOTS_PATH,
    base_signature_checkpoint_path: Path | str = DEFAULT_BASE_SIGNATURE_CHECKPOINT_PATH,
    signature_checkpoint_path: Path | str = DEFAULT_SIGNATURE_CHECKPOINT_PATH,
    raw_transactions_path: Path | str = DEFAULT_POST_DECISION_RAW_TRANSACTIONS_PATH,
    existing_raw_glob: str | None = DEFAULT_EXISTING_RAW_GLOB,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    rpc: Any | None = None,
    execute: bool = False,
    signature_page_limit: int = 100,
    max_pages_per_mint: int = 2,
    max_transactions_per_mint: int = 500,
    max_targets: int | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    plan_path = Path(plan_path)
    current_supply_snapshots_path = Path(current_supply_snapshots_path)
    base_signature_checkpoint_path = Path(base_signature_checkpoint_path)
    signature_checkpoint_path = Path(signature_checkpoint_path)
    raw_transactions_path = Path(raw_transactions_path)
    report_path = Path(report_path)
    output_raw_rows = read_jsonl(raw_transactions_path)
    existing_raw_rows = merge_raw_rows(
        output_raw_rows,
        [row for path in expand_existing_raw_paths(existing_raw_glob) for row in read_jsonl(path)],
    )
    base_checkpoint = read_json(base_signature_checkpoint_path, {})
    existing_post_decision_checkpoint = read_json(signature_checkpoint_path, {})
    signature_checkpoint = {
        **(base_checkpoint if isinstance(base_checkpoint, dict) else {}),
        **(existing_post_decision_checkpoint if isinstance(existing_post_decision_checkpoint, dict) else {}),
    }
    report = build_post_decision_supply_transaction_collection_report(
        archival_supply_plan=read_json(plan_path, {"token_requirements": []}),
        current_supply_snapshots=read_jsonl(current_supply_snapshots_path),
        signature_checkpoint=signature_checkpoint,
        raw_transactions=existing_raw_rows,
        rpc=rpc,
        execute=execute,
        signature_page_limit=signature_page_limit,
        max_pages_per_mint=max_pages_per_mint,
        max_transactions_per_mint=max_transactions_per_mint,
        max_targets=max_targets,
        generated_at=generated_at,
    )
    raw_rows = report.pop("raw_transactions", [])
    signature_checkpoint = report.pop("signature_checkpoint", {})
    report["input_paths"] = {
        "plan": relative_path(plan_path, ROOT),
        "current_supply_snapshots": relative_path(current_supply_snapshots_path, ROOT),
        "base_signature_checkpoint": relative_path(base_signature_checkpoint_path, ROOT),
        "signature_checkpoint": relative_path(signature_checkpoint_path, ROOT),
        "raw_transactions": relative_path(raw_transactions_path, ROOT),
        "existing_raw_glob": existing_raw_glob,
    }
    report["output_paths"] = {
        "report": relative_path(report_path, ROOT),
        "signature_checkpoint": relative_path(signature_checkpoint_path, ROOT),
        "raw_transactions": relative_path(raw_transactions_path, ROOT),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    signature_checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    raw_transactions_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    signature_checkpoint_path.write_text(json.dumps(signature_checkpoint, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_jsonl(raw_transactions_path, merge_raw_rows(output_raw_rows, raw_rows))
    report["raw_transactions"] = raw_rows
    report["signature_checkpoint"] = signature_checkpoint
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect read-only post-decision mint transaction bodies for current-supply stability proof."
    )
    parser.add_argument("--execute", action="store_true", help="Fetch read-only signatures/transactions. Default is dry-run.")
    parser.add_argument("--plan-path", type=Path, default=DEFAULT_PLAN_PATH)
    parser.add_argument("--current-supply-snapshots", type=Path, default=DEFAULT_CURRENT_SUPPLY_SNAPSHOTS_PATH)
    parser.add_argument("--base-signature-checkpoint-path", type=Path, default=DEFAULT_BASE_SIGNATURE_CHECKPOINT_PATH)
    parser.add_argument("--signature-checkpoint-path", type=Path, default=DEFAULT_SIGNATURE_CHECKPOINT_PATH)
    parser.add_argument("--raw-transactions-path", type=Path, default=DEFAULT_POST_DECISION_RAW_TRANSACTIONS_PATH)
    parser.add_argument("--existing-raw-glob", default=DEFAULT_EXISTING_RAW_GLOB)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--signature-page-limit", type=int, default=100)
    parser.add_argument("--max-pages-per-mint", type=int, default=2)
    parser.add_argument("--max-transactions-per-mint", type=int, default=500)
    parser.add_argument("--max-targets", type=int, default=None)
    parser.add_argument("--rpc-timeout", type=int, default=15)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    load_env()
    rpc = SyncRpcClient(timeout=args.rpc_timeout) if args.execute else None
    report = write_post_decision_supply_transaction_collection_report(
        plan_path=args.plan_path,
        current_supply_snapshots_path=args.current_supply_snapshots,
        base_signature_checkpoint_path=args.base_signature_checkpoint_path,
        signature_checkpoint_path=args.signature_checkpoint_path,
        raw_transactions_path=args.raw_transactions_path,
        existing_raw_glob=args.existing_raw_glob,
        report_path=args.report_path,
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
