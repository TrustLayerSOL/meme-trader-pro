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

from utils.backfill_historical_market_context import load_raw_transactions, read_jsonl  # noqa: E402
from wallets.historical_market_context_backfill import relative_path  # noqa: E402
from wallets.archival_supply_recovery_plan import build_archival_supply_recovery_plan  # noqa: E402


DEFAULT_SCORE_READY_RECORDS_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "score_ready_market_context_records.jsonl"
)
DEFAULT_RAW_TRANSACTIONS_DIR = ROOT / "data" / "wallet_backfills" / "raw_transactions"
DEFAULT_REPORT_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_supply_recovery_plan.json"


def write_archival_supply_recovery_plan(
    *,
    score_ready_records_path: Path | str = DEFAULT_SCORE_READY_RECORDS_PATH,
    raw_transactions_dir: Path | str = DEFAULT_RAW_TRANSACTIONS_DIR,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    generated_at: float | None = None,
) -> dict[str, Any]:
    score_ready_records_path = Path(score_ready_records_path)
    raw_transactions_dir = Path(raw_transactions_dir)
    report_path = Path(report_path)
    report = build_archival_supply_recovery_plan(
        score_ready_market_context_records=read_jsonl(score_ready_records_path),
        raw_transactions=load_raw_transactions(raw_transactions_dir),
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "score_ready_records": relative_path(score_ready_records_path, ROOT),
        "raw_transactions_dir": relative_path(raw_transactions_dir, ROOT),
    }
    report["output_paths"] = {
        "report": relative_path(report_path, ROOT),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a read-only archival supply recovery plan.")
    parser.add_argument("--score-ready-records", type=Path, default=DEFAULT_SCORE_READY_RECORDS_PATH)
    parser.add_argument("--raw-transactions-dir", type=Path, default=DEFAULT_RAW_TRANSACTIONS_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_archival_supply_recovery_plan(
        score_ready_records_path=args.score_ready_records,
        raw_transactions_dir=args.raw_transactions_dir,
        report_path=args.report_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
