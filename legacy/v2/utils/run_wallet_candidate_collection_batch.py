#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
PYTHON = str(ROOT / "trading_env" / "bin" / "python")
DEFAULT_COLLECTION_PLAN = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_candidate_collection_plan.json"
DEFAULT_REPORT = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_candidate_collection_batch_report.json"

BATCH_STEPS: list[dict[str, Any]] = [
    {"name": "wallet_evidence_enrichment", "command": [PYTHON, "utils/enrich_wallet_history_evidence.py"]},
    {"name": "wallet_missing_market_context", "command": [PYTHON, "utils/build_wallet_missing_market_context_targets.py"]},
    {"name": "historical_market_context_backfill", "command": [PYTHON, "utils/backfill_historical_market_context.py"]},
    {"name": "historical_quote_price_enrichment", "command": [PYTHON, "utils/enrich_historical_quote_prices.py"]},
    {"name": "onchain_market_context_recovery", "command": [PYTHON, "utils/recover_onchain_market_context.py"]},
    {"name": "onchain_supply_evidence", "command": [PYTHON, "utils/build_onchain_supply_evidence.py"]},
    {"name": "trusted_market_context_gate", "command": [PYTHON, "utils/build_trusted_historical_market_snapshot_report.py"]},
    {"name": "wallet_evidence_readiness", "command": [PYTHON, "utils/build_wallet_evidence_readiness.py"]},
    {"name": "wallet_evidence_recommendations", "command": [PYTHON, "utils/build_wallet_evidence_recommendations.py"]},
    {"name": "wallet_evidence_lifecycle", "command": [PYTHON, "utils/build_wallet_evidence_lifecycle.py"]},
    {"name": "wallet_evidence_scorecard", "command": [PYTHON, "utils/build_wallet_evidence_scorecard.py"]},
    {"name": "stage4_review", "command": [PYTHON, "utils/build_wallet_stage4_review.py"]},
    {"name": "candidate_audit", "command": [PYTHON, "utils/build_wallet_candidate_audit.py"]},
    {"name": "candidate_decision_prep", "command": [PYTHON, "utils/build_wallet_candidate_decision_prep.py"]},
    {"name": "candidate_review_summary", "command": [PYTHON, "utils/build_wallet_candidate_review_summary.py"]},
    {"name": "candidate_collection_plan", "command": [PYTHON, "utils/build_wallet_candidate_collection_plan.py"]},
]

DISALLOWED_COMMAND_PARTS = {
    "apply_wallet_review.py",
    "paper_trade",
    "live_trade",
    "execute_trade",
    "jupiter_swap",
}


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default
    return parsed


def tail(text: str, limit: int = 3000) -> str:
    return text[-limit:] if len(text) > limit else text


def disallowed_command_present(steps: list[dict[str, Any]]) -> bool:
    for step in steps:
        command = " ".join(str(part) for part in step.get("command") or [])
        if any(part in command for part in DISALLOWED_COMMAND_PARTS):
            return True
    return False


def subprocess_runner(command: list[str], *, cwd: Path, timeout: float) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return {
        "status": "passed" if completed.returncode == 0 else "failed",
        "exit_code": completed.returncode,
        "stdout_tail": tail(completed.stdout),
        "stderr_tail": tail(completed.stderr),
    }


def build_batch_report(
    *,
    root: Path,
    collection_plan: dict[str, Any],
    command_runner: Callable[..., dict[str, Any]] = subprocess_runner,
    steps: list[dict[str, Any]] | None = None,
    generated_at: float | None = None,
    timeout: float = 120.0,
    continue_on_error: bool = False,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    steps = BATCH_STEPS if steps is None else steps
    if disallowed_command_present(steps):
        raise ValueError("Collection batch contains a disallowed command.")

    results: list[dict[str, Any]] = []
    for step in steps:
        result = command_runner([str(part) for part in step.get("command") or []], cwd=root, timeout=timeout)
        row = {
            "name": step.get("name"),
            "command": [str(part) for part in step.get("command") or []],
            **result,
        }
        results.append(row)
        if row.get("status") != "passed" and not continue_on_error:
            break

    plan_summary = collection_plan.get("summary") if isinstance(collection_plan.get("summary"), dict) else {}
    passed = len([row for row in results if row.get("status") == "passed"])
    failed = len([row for row in results if row.get("status") != "passed"])
    return {
        "generated_at": generated_at,
        "mode": "WALLET_CANDIDATE_COLLECTION_BATCH_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "summary": {
            "planned_targets": int(plan_summary.get("total_targets") or 0),
            "planned_outcome_market_targets": int(plan_summary.get("collect_outcomes_and_market_context") or 0),
            "planned_outcome_label_targets": int(plan_summary.get("collect_outcome_labels") or 0),
            "planned_risk_review_targets": int(plan_summary.get("manual_risk_review") or 0),
            "steps_planned": len(steps),
            "steps_run": len(results),
            "steps_passed": passed,
            "steps_failed": failed,
        },
        "initial_collection_plan_summary": plan_summary,
        "steps": results,
        "operator_note": "Read-only batch refresh. This rebuilds evidence reports only; it does not approve, apply, trade, or mutate wallet lists.",
    }


def write_batch_report(
    *,
    collection_plan_path: Path = DEFAULT_COLLECTION_PLAN,
    report_path: Path = DEFAULT_REPORT,
    timeout: float = 120.0,
    continue_on_error: bool = False,
) -> dict[str, Any]:
    plan = read_json(collection_plan_path, {"summary": {}})
    report = build_batch_report(
        root=ROOT,
        collection_plan=plan,
        timeout=timeout,
        continue_on_error=continue_on_error,
    )
    report["input_paths"] = {"collection_plan": str(collection_plan_path.relative_to(ROOT))}
    report["output_paths"] = {"report": str(report_path.relative_to(ROOT))}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run read-only wallet candidate evidence collection report refresh.")
    parser.add_argument("--collection-plan", type=Path, default=DEFAULT_COLLECTION_PLAN)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--continue-on-error", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_batch_report(
        collection_plan_path=args.collection_plan,
        report_path=args.report_path,
        timeout=args.timeout,
        continue_on_error=args.continue_on_error,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0 if report["summary"]["steps_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
