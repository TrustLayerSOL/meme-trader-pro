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

from utils.backfill_historical_market_context import read_jsonl  # noqa: E402
from wallets.archival_supply_evidence import build_archival_supply_evidence_report  # noqa: E402
from wallets.historical_market_context_backfill import relative_path  # noqa: E402


DEFAULT_PLAN_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_supply_recovery_plan.json"
DEFAULT_SNAPSHOTS_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_mint_supply_snapshots.jsonl"
DEFAULT_REPORT_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_supply_evidence_report.json"
DEFAULT_RECORDS_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_supply_evidence_records.jsonl"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    return parsed


def write_archival_supply_evidence_report(
    *,
    plan_path: Path | str = DEFAULT_PLAN_PATH,
    snapshots_path: Path | str = DEFAULT_SNAPSHOTS_PATH,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    output_records_path: Path | str = DEFAULT_RECORDS_PATH,
    generated_at: float | None = None,
) -> dict[str, Any]:
    plan_path = Path(plan_path)
    snapshots_path = Path(snapshots_path)
    report_path = Path(report_path)
    output_records_path = Path(output_records_path)
    report = build_archival_supply_evidence_report(
        archival_supply_plan=read_json(plan_path, {"candidate_rows": [], "token_requirements": []}),
        supply_snapshots=read_jsonl(snapshots_path),
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "plan": relative_path(plan_path, ROOT),
        "snapshots": relative_path(snapshots_path, ROOT),
    }
    report["output_paths"] = {
        "report": relative_path(report_path, ROOT),
        "records": relative_path(output_records_path, ROOT),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output_records_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with output_records_path.open("w", encoding="utf-8") as handle:
        for record in report.get("records") or []:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a read-only archival supply evidence report.")
    parser.add_argument("--plan-path", type=Path, default=DEFAULT_PLAN_PATH)
    parser.add_argument("--snapshots-path", type=Path, default=DEFAULT_SNAPSHOTS_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--records-path", type=Path, default=DEFAULT_RECORDS_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_archival_supply_evidence_report(
        plan_path=args.plan_path,
        snapshots_path=args.snapshots_path,
        report_path=args.report_path,
        output_records_path=args.records_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
