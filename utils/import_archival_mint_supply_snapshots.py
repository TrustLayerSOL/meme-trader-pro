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

from utils.collect_archival_mint_supply_snapshots import read_json  # noqa: E402
from wallets.archival_mint_snapshot_response_import import build_archival_mint_snapshot_response_import_report  # noqa: E402
from wallets.historical_market_context_backfill import relative_path  # noqa: E402


DEFAULT_COLLECTION_REPORT_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "archival_mint_supply_snapshot_collection_report.json"
)
DEFAULT_RAW_RESPONSE_PATH = (
    ROOT
    / "data"
    / "reports"
    / "historical_backfill"
    / "raw_provider_responses"
    / "archival_mint_supply_batch_raw.json"
)
DEFAULT_REPORT_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_mint_snapshot_response_import_report.json"
DEFAULT_SNAPSHOTS_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_mint_supply_snapshots.jsonl"


def write_archival_mint_snapshot_response_import_report(
    *,
    collection_report_path: Path | str = DEFAULT_COLLECTION_REPORT_PATH,
    raw_response_path: Path | str = DEFAULT_RAW_RESPONSE_PATH,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    snapshots_path: Path | str = DEFAULT_SNAPSHOTS_PATH,
    generated_at: float | None = None,
) -> dict[str, Any]:
    collection_report_path = Path(collection_report_path)
    raw_response_path = Path(raw_response_path)
    report_path = Path(report_path)
    snapshots_path = Path(snapshots_path)
    report = build_archival_mint_snapshot_response_import_report(
        snapshot_collection_report=read_json(collection_report_path, {"requests": []}),
        raw_provider_response=read_json(raw_response_path, []),
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "collection_report": relative_path(collection_report_path, ROOT),
        "raw_provider_response": relative_path(raw_response_path, ROOT),
    }
    report["output_paths"] = {
        "report": relative_path(report_path, ROOT),
        "snapshots": relative_path(snapshots_path, ROOT),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    snapshots_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with snapshots_path.open("w", encoding="utf-8") as handle:
        for snapshot in report.get("snapshots") or []:
            handle.write(json.dumps(snapshot, sort_keys=True) + "\n")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import saved archival mint supply snapshots for review.")
    parser.add_argument("--collection-report-path", type=Path, default=DEFAULT_COLLECTION_REPORT_PATH)
    parser.add_argument("--raw-response-path", type=Path, default=DEFAULT_RAW_RESPONSE_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--snapshots-path", type=Path, default=DEFAULT_SNAPSHOTS_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_archival_mint_snapshot_response_import_report(
        collection_report_path=args.collection_report_path,
        raw_response_path=args.raw_response_path,
        report_path=args.report_path,
        snapshots_path=args.snapshots_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
