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
from wallets.onchain_market_context_recovery import relative_path  # noqa: E402
from wallets.score_ready_market_context import build_score_ready_market_context_report  # noqa: E402


DEFAULT_ONCHAIN_RECORDS_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "onchain_market_context_recovery_records.jsonl"
)
DEFAULT_SUPPLY_RECORDS_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "onchain_supply_evidence_records.jsonl"
)
DEFAULT_ARCHIVAL_SUPPLY_RECORDS_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "archival_supply_evidence_records.jsonl"
)
DEFAULT_MANUAL_SUPPLY_RECORDS_PATH = ROOT / "data" / "manual_research" / "manual_supply_evidence_records.jsonl"
DEFAULT_REPORT_PATH = ROOT / "data" / "reports" / "historical_backfill" / "score_ready_market_context_report.json"
DEFAULT_OUTPUT_RECORDS_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "score_ready_market_context_records.jsonl"
)


def write_score_ready_market_context_report(
    *,
    onchain_records_path: Path | str = DEFAULT_ONCHAIN_RECORDS_PATH,
    supply_records_path: Path | str = DEFAULT_SUPPLY_RECORDS_PATH,
    archival_supply_records_path: Path | str = DEFAULT_ARCHIVAL_SUPPLY_RECORDS_PATH,
    manual_supply_records_path: Path | str = DEFAULT_MANUAL_SUPPLY_RECORDS_PATH,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    output_records_path: Path | str = DEFAULT_OUTPUT_RECORDS_PATH,
    generated_at: float | None = None,
) -> dict[str, Any]:
    onchain_records_path = Path(onchain_records_path)
    supply_records_path = Path(supply_records_path)
    archival_supply_records_path = Path(archival_supply_records_path)
    manual_supply_records_path = Path(manual_supply_records_path)
    report_path = Path(report_path)
    output_records_path = Path(output_records_path)
    report = build_score_ready_market_context_report(
        onchain_market_context_records=read_jsonl(onchain_records_path),
        supply_evidence_records=read_jsonl(supply_records_path),
        archival_supply_records=read_jsonl(archival_supply_records_path),
        manual_supply_records=read_jsonl(manual_supply_records_path),
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "onchain_market_context_records": relative_path(onchain_records_path, ROOT),
        "supply_evidence_records": relative_path(supply_records_path, ROOT),
        "archival_supply_records": relative_path(archival_supply_records_path, ROOT),
        "manual_supply_records": relative_path(manual_supply_records_path, ROOT),
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
    parser = argparse.ArgumentParser(description="Classify score-ready historical market context candidates.")
    parser.add_argument("--onchain-records", type=Path, default=DEFAULT_ONCHAIN_RECORDS_PATH)
    parser.add_argument("--supply-records", type=Path, default=DEFAULT_SUPPLY_RECORDS_PATH)
    parser.add_argument("--archival-supply-records", type=Path, default=DEFAULT_ARCHIVAL_SUPPLY_RECORDS_PATH)
    parser.add_argument("--manual-supply-records", type=Path, default=DEFAULT_MANUAL_SUPPLY_RECORDS_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--records-path", type=Path, default=DEFAULT_OUTPUT_RECORDS_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_score_ready_market_context_report(
        onchain_records_path=args.onchain_records,
        supply_records_path=args.supply_records,
        archival_supply_records_path=args.archival_supply_records,
        manual_supply_records_path=args.manual_supply_records,
        report_path=args.report_path,
        output_records_path=args.records_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
