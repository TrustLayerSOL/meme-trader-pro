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
from wallets.archival_mint_snapshot_request_bundle import build_archival_mint_snapshot_request_bundle_report  # noqa: E402
from wallets.historical_market_context_backfill import relative_path  # noqa: E402


DEFAULT_COLLECTION_REPORT_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "archival_mint_supply_snapshot_collection_report.json"
)
DEFAULT_REPORT_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_mint_snapshot_request_bundle_report.json"
DEFAULT_RAW_RESPONSE_PATH = (
    "data/reports/historical_backfill/raw_provider_responses/archival_mint_supply_batch_raw.json"
)
DEFAULT_BATCH_REQUEST_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "raw_provider_responses" / "archival_mint_supply_batch_request.json"
)
DEFAULT_RESPONSE_TEMPLATE_PATH = (
    ROOT
    / "data"
    / "reports"
    / "historical_backfill"
    / "raw_provider_responses"
    / "archival_mint_supply_batch_response_template.json"
)


def write_archival_mint_snapshot_request_bundle_report(
    *,
    collection_report_path: Path | str = DEFAULT_COLLECTION_REPORT_PATH,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    raw_response_path: str = DEFAULT_RAW_RESPONSE_PATH,
    batch_request_path: Path | str = DEFAULT_BATCH_REQUEST_PATH,
    response_template_path: Path | str = DEFAULT_RESPONSE_TEMPLATE_PATH,
    generated_at: float | None = None,
) -> dict[str, Any]:
    collection_report_path = Path(collection_report_path)
    report_path = Path(report_path)
    batch_request_path = Path(batch_request_path)
    response_template_path = Path(response_template_path)
    batch_request_relative = relative_path(batch_request_path, ROOT)
    response_template_relative = relative_path(response_template_path, ROOT)
    report = build_archival_mint_snapshot_request_bundle_report(
        snapshot_collection_report=read_json(collection_report_path, {"requests": []}),
        raw_response_path=raw_response_path,
        batch_request_path=batch_request_relative,
        response_template_path=response_template_relative,
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "collection_report": relative_path(collection_report_path, ROOT),
    }
    report["output_paths"] = {
        "report": relative_path(report_path, ROOT),
        "batch_request": batch_request_relative,
        "response_template": response_template_relative,
        "raw_provider_response": raw_response_path,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    batch_request_path.parent.mkdir(parents=True, exist_ok=True)
    response_template_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    batch_request_path.write_text(json.dumps(report["batch_jsonrpc_payload"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    response_template_path.write_text(json.dumps(report["response_template"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a read-only archival mint snapshot batch request bundle.")
    parser.add_argument("--collection-report-path", type=Path, default=DEFAULT_COLLECTION_REPORT_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--raw-response-path", default=DEFAULT_RAW_RESPONSE_PATH)
    parser.add_argument("--batch-request-path", type=Path, default=DEFAULT_BATCH_REQUEST_PATH)
    parser.add_argument("--response-template-path", type=Path, default=DEFAULT_RESPONSE_TEMPLATE_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_archival_mint_snapshot_request_bundle_report(
        collection_report_path=args.collection_report_path,
        report_path=args.report_path,
        raw_response_path=args.raw_response_path,
        batch_request_path=args.batch_request_path,
        response_template_path=args.response_template_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
