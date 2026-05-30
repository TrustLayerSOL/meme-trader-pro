#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.wallet_promotion_demotion_system import build_wallet_promotion_demotion_system_report


DEFAULT_STAGE4_REVIEW = ROOT / "data" / "reports" / "wallet_backfills" / "wallet_stage4_review_report.json"
DEFAULT_CANDIDATE_AUDIT = ROOT / "data" / "wallet_candidate_audit.json"
DEFAULT_DECISION_PREP = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_candidate_decision_prep.json"
DEFAULT_REVIEW_SUMMARY = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_candidate_review_summary.json"
DEFAULT_COLLECTION_PLAN = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_candidate_collection_plan.json"
DEFAULT_COLLECTION_BATCH = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_candidate_collection_batch_report.json"
DEFAULT_BLOCKER_REDUCER = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_candidate_blocker_reducer.json"
DEFAULT_CONTEXT_RECOVERY_QUEUE = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_candidate_context_recovery_queue.json"
DEFAULT_CONTEXT_RECOVERY_RUNNER = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_candidate_context_recovery_runner.json"
DEFAULT_CONTEXT_RECOVERY_CLOSEOUT = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_candidate_context_recovery_closeout.json"
DEFAULT_OUTPUT = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_promotion_demotion_system_report.json"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default
    return value if isinstance(value, dict) else default


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def write_wallet_promotion_demotion_system_report(
    *,
    stage4_review_path: Path = DEFAULT_STAGE4_REVIEW,
    candidate_audit_path: Path = DEFAULT_CANDIDATE_AUDIT,
    decision_prep_path: Path = DEFAULT_DECISION_PREP,
    review_summary_path: Path = DEFAULT_REVIEW_SUMMARY,
    collection_plan_path: Path = DEFAULT_COLLECTION_PLAN,
    collection_batch_path: Path = DEFAULT_COLLECTION_BATCH,
    blocker_reducer_path: Path = DEFAULT_BLOCKER_REDUCER,
    context_recovery_queue_path: Path = DEFAULT_CONTEXT_RECOVERY_QUEUE,
    context_recovery_runner_path: Path = DEFAULT_CONTEXT_RECOVERY_RUNNER,
    context_recovery_closeout_path: Path = DEFAULT_CONTEXT_RECOVERY_CLOSEOUT,
    output_path: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    report = build_wallet_promotion_demotion_system_report(
        stage4_review=read_json(stage4_review_path, {}),
        candidate_audit=read_json(candidate_audit_path, {}),
        decision_prep=read_json(decision_prep_path, {}),
        review_summary=read_json(review_summary_path, {}),
        collection_plan=read_json(collection_plan_path, {}),
        collection_batch=read_json(collection_batch_path, {}),
        blocker_reducer=read_json(blocker_reducer_path, {}),
        context_recovery_queue=read_json(context_recovery_queue_path, {}),
        context_recovery_runner=read_json(context_recovery_runner_path, {}),
        context_recovery_closeout=read_json(context_recovery_closeout_path, {}),
    )
    report["input_paths"] = {
        "stage4_review": rel(stage4_review_path),
        "candidate_audit": rel(candidate_audit_path),
        "decision_prep": rel(decision_prep_path),
        "review_summary": rel(review_summary_path),
        "collection_plan": rel(collection_plan_path),
        "collection_batch": rel(collection_batch_path),
        "blocker_reducer": rel(blocker_reducer_path),
        "context_recovery_queue": rel(context_recovery_queue_path),
        "context_recovery_runner": rel(context_recovery_runner_path),
        "context_recovery_closeout": rel(context_recovery_closeout_path),
    }
    report["output_paths"] = {"report": rel(output_path)}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = write_wallet_promotion_demotion_system_report()
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
