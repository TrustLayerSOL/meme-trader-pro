#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wallets.wallet_candidate_blocker_reducer import build_wallet_candidate_blocker_reducer

DEFAULT_AUDIT = ROOT / "data" / "wallet_candidate_audit.json"
DEFAULT_PLAN = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_candidate_collection_plan.json"
DEFAULT_BATCH = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_candidate_collection_batch_report.json"
DEFAULT_OUTPUT = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_candidate_blocker_reducer.json"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_report(
    *,
    audit_path: Path = DEFAULT_AUDIT,
    plan_path: Path = DEFAULT_PLAN,
    batch_path: Path = DEFAULT_BATCH,
    output_path: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    report = build_wallet_candidate_blocker_reducer(
        candidate_audit=read_json(audit_path, {}),
        collection_plan=read_json(plan_path, {}),
        collection_batch=read_json(batch_path, {}),
    )
    report["input_paths"] = {
        "candidate_audit": str(audit_path.relative_to(ROOT)),
        "collection_plan": str(plan_path.relative_to(ROOT)),
        "collection_batch": str(batch_path.relative_to(ROOT)),
    }
    report["output_paths"] = {"report": str(output_path.relative_to(ROOT))}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = write_report()
    print(json.dumps({
        "blocked_total": report["summary"].get("blocked_total"),
        "primary_blocker_counts": report.get("primary_blocker_counts"),
        "batch_steps_failed": report["batch_health"].get("steps_failed"),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
