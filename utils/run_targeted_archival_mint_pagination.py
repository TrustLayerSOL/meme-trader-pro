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
from utils.collect_archival_mint_history import DEFAULT_COMPLETENESS_PATH  # noqa: E402
from utils.collect_archival_mint_history import DEFAULT_RAW_TRANSACTIONS_PATH  # noqa: E402
from utils.collect_archival_mint_history import DEFAULT_REPORT_PATH as DEFAULT_COLLECTION_REPORT_PATH  # noqa: E402
from utils.collect_archival_mint_history import DEFAULT_SIGNATURE_CHECKPOINT_PATH  # noqa: E402
from utils.collect_archival_mint_history import read_json  # noqa: E402
from utils.collect_archival_mint_history import write_archival_mint_history_collection_report  # noqa: E402
from utils.discover_candidate_wallets import SyncRpcClient  # noqa: E402
from wallets.historical_market_context_backfill import relative_path  # noqa: E402


DEFAULT_SUPPLY_PLAN_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_supply_recovery_plan.json"
DEFAULT_PAGINATION_PLAN_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_mint_pagination_plan_report.json"
DEFAULT_FILTERED_PLAN_PATH = ROOT / "data" / "reports" / "historical_backfill" / "targeted_archival_mint_pagination_plan.json"
DEFAULT_REPORT_PATH = ROOT / "data" / "reports" / "historical_backfill" / "targeted_archival_mint_pagination_report.json"
CONTINUE_ACTION = "CONTINUE_PAGINATION_TOWARD_DECISION_SLOT"


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def token_mint(row: dict[str, Any]) -> str:
    return str(row.get("token_mint") or row.get("mint") or "").strip()


def sorted_target_rows(
    pagination_plan: dict[str, Any],
    *,
    max_estimated_pages: int | None = None,
) -> list[dict[str, Any]]:
    rows = [row for row in pagination_plan.get("rows", []) if isinstance(row, dict)]
    targets: list[dict[str, Any]] = []
    for row in rows:
        if row.get("recommended_action") != CONTINUE_ACTION:
            continue
        mint = token_mint(row)
        if not mint:
            continue
        estimated_pages = row.get("estimated_pages_to_decision_slot")
        if max_estimated_pages is not None:
            if estimated_pages is None or safe_int(estimated_pages, 10**9) > int(max_estimated_pages):
                continue
        targets.append(row)
    targets.sort(
        key=lambda row: (
            safe_int(row.get("estimated_pages_to_decision_slot"), 10**9),
            -safe_int(row.get("priority"), 0),
            token_mint(row),
        )
    )
    return targets


def select_target_requirements(
    *,
    supply_plan: dict[str, Any],
    pagination_plan: dict[str, Any],
    max_estimated_pages: int | None = None,
    max_targets: int | None = None,
) -> list[dict[str, Any]]:
    target_rows = sorted_target_rows(pagination_plan, max_estimated_pages=max_estimated_pages)
    if max_targets is not None:
        target_rows = target_rows[: max(0, int(max_targets))]
    selected_mints = {token_mint(row) for row in target_rows}
    requirements = [row for row in supply_plan.get("token_requirements", []) if isinstance(row, dict)]
    by_mint = {token_mint(row): row for row in requirements if token_mint(row)}
    return [by_mint[mint] for mint in [token_mint(row) for row in target_rows] if mint in by_mint]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_targeted_archival_mint_pagination_report(
    *,
    supply_plan_path: Path | str = DEFAULT_SUPPLY_PLAN_PATH,
    pagination_plan_path: Path | str = DEFAULT_PAGINATION_PLAN_PATH,
    filtered_plan_path: Path | str = DEFAULT_FILTERED_PLAN_PATH,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    collection_report_path: Path | str = DEFAULT_COLLECTION_REPORT_PATH,
    raw_transactions_path: Path | str = DEFAULT_RAW_TRANSACTIONS_PATH,
    completeness_path: Path | str = DEFAULT_COMPLETENESS_PATH,
    signature_checkpoint_path: Path | str = DEFAULT_SIGNATURE_CHECKPOINT_PATH,
    rpc: Any | None = None,
    execute: bool = False,
    max_estimated_pages: int | None = 10,
    max_targets: int | None = None,
    signature_page_limit: int = 100,
    max_pages_per_mint: int = 10,
    max_transactions_per_mint: int = 900,
    generated_at: float | None = None,
) -> dict[str, Any]:
    supply_plan_path = Path(supply_plan_path)
    pagination_plan_path = Path(pagination_plan_path)
    filtered_plan_path = Path(filtered_plan_path)
    report_path = Path(report_path)
    collection_report_path = Path(collection_report_path)
    raw_transactions_path = Path(raw_transactions_path)
    completeness_path = Path(completeness_path)
    signature_checkpoint_path = Path(signature_checkpoint_path)

    supply_plan = read_json(supply_plan_path, {"token_requirements": []})
    pagination_plan = read_json(pagination_plan_path, {"rows": []})
    selected_requirements = select_target_requirements(
        supply_plan=supply_plan,
        pagination_plan=pagination_plan,
        max_estimated_pages=max_estimated_pages,
        max_targets=max_targets,
    )
    filtered_plan = {
        **(supply_plan if isinstance(supply_plan, dict) else {}),
        "mode": "TARGETED_ARCHIVAL_MINT_PAGINATION_PLAN_REVIEW_ONLY",
        "source_supply_plan": relative_path(supply_plan_path, ROOT),
        "source_pagination_plan": relative_path(pagination_plan_path, ROOT),
        "target_selection": {
            "recommended_action": CONTINUE_ACTION,
            "max_estimated_pages": max_estimated_pages,
            "max_targets": max_targets,
            "selected_targets": len(selected_requirements),
        },
        "token_requirements": selected_requirements,
    }
    write_json(filtered_plan_path, filtered_plan)

    collection_report = write_archival_mint_history_collection_report(
        plan_path=filtered_plan_path,
        report_path=collection_report_path,
        raw_transactions_path=raw_transactions_path,
        completeness_path=completeness_path,
        signature_checkpoint_path=signature_checkpoint_path,
        rpc=rpc,
        execute=execute,
        signature_page_limit=signature_page_limit,
        max_pages_per_mint=max_pages_per_mint,
        max_transactions_per_mint=max_transactions_per_mint,
        generated_at=generated_at,
    )
    collection_summary = collection_report.get("summary", {}) if isinstance(collection_report, dict) else {}
    report = {
        "generated_at": generated_at,
        "mode": "TARGETED_ARCHIVAL_MINT_PAGINATION_REVIEW_ONLY",
        "review_only": True,
        "read_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "execute_requested": bool(execute),
        "summary": {
            "selected_targets": len(selected_requirements),
            "collection_mint_history_targets": safe_int(collection_summary.get("mint_history_targets"), 0),
            "collection_mint_histories_complete": safe_int(collection_summary.get("mint_histories_complete"), 0),
            "collection_blocked_incomplete_history": safe_int(collection_summary.get("blocked_incomplete_history"), 0),
            "collection_raw_transactions_preserved": safe_int(collection_summary.get("raw_transactions_preserved"), 0),
            "wallet_list_mutations": 0,
            "auto_trust_mutations": 0,
        },
        "input_paths": {
            "supply_plan": relative_path(supply_plan_path, ROOT),
            "pagination_plan": relative_path(pagination_plan_path, ROOT),
        },
        "output_paths": {
            "filtered_plan": relative_path(filtered_plan_path, ROOT),
            "report": relative_path(report_path, ROOT),
            "collection_report": relative_path(collection_report_path, ROOT),
        },
        "selected_mints": [token_mint(row) for row in selected_requirements],
        "operator_note": (
            "This runner is read-only. It targets only continue-pagination mint accounts, "
            "preserves existing collection artifacts, and cannot mutate wallet trust or execution."
        ),
    }
    write_json(report_path, report)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run targeted read-only archival mint pagination from the current pagination plan.")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--supply-plan-path", type=Path, default=DEFAULT_SUPPLY_PLAN_PATH)
    parser.add_argument("--pagination-plan-path", type=Path, default=DEFAULT_PAGINATION_PLAN_PATH)
    parser.add_argument("--filtered-plan-path", type=Path, default=DEFAULT_FILTERED_PLAN_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--collection-report-path", type=Path, default=DEFAULT_COLLECTION_REPORT_PATH)
    parser.add_argument("--raw-transactions-path", type=Path, default=DEFAULT_RAW_TRANSACTIONS_PATH)
    parser.add_argument("--completeness-path", type=Path, default=DEFAULT_COMPLETENESS_PATH)
    parser.add_argument("--signature-checkpoint-path", type=Path, default=DEFAULT_SIGNATURE_CHECKPOINT_PATH)
    parser.add_argument("--max-estimated-pages", type=int, default=10)
    parser.add_argument("--max-targets", type=int, default=None)
    parser.add_argument("--signature-page-limit", type=int, default=100)
    parser.add_argument("--max-pages-per-mint", type=int, default=10)
    parser.add_argument("--max-transactions-per-mint", type=int, default=900)
    parser.add_argument("--rpc-timeout", type=int, default=25)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    load_env()
    rpc = SyncRpcClient(timeout=args.rpc_timeout) if args.execute else None
    report = write_targeted_archival_mint_pagination_report(
        supply_plan_path=args.supply_plan_path,
        pagination_plan_path=args.pagination_plan_path,
        filtered_plan_path=args.filtered_plan_path,
        report_path=args.report_path,
        collection_report_path=args.collection_report_path,
        raw_transactions_path=args.raw_transactions_path,
        completeness_path=args.completeness_path,
        signature_checkpoint_path=args.signature_checkpoint_path,
        rpc=rpc,
        execute=args.execute,
        max_estimated_pages=args.max_estimated_pages,
        max_targets=args.max_targets,
        signature_page_limit=args.signature_page_limit,
        max_pages_per_mint=args.max_pages_per_mint,
        max_transactions_per_mint=args.max_transactions_per_mint,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
