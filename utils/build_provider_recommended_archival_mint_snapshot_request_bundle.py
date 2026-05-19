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

from utils.build_archival_mint_snapshot_request_bundle import (  # noqa: E402
    DEFAULT_COLLECTION_REPORT_PATH,
    write_archival_mint_snapshot_request_bundle_report,
)
from utils.collect_archival_mint_supply_snapshots import read_json  # noqa: E402
from wallets.historical_market_context_backfill import relative_path  # noqa: E402


SOURCE_FILTER = "provider_recommended_archival_account_state"
DEFAULT_PAGINATION_PLAN_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_mint_pagination_plan_report.json"
DEFAULT_REPORT_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "provider_recommended_archival_mint_snapshot_request_bundle_report.json"
)
DEFAULT_RAW_RESPONSE_PATH = (
    "data/reports/historical_backfill/raw_provider_responses/provider_recommended_archival_mint_supply_batch_raw.json"
)
DEFAULT_BATCH_REQUEST_PATH = (
    ROOT
    / "data"
    / "reports"
    / "historical_backfill"
    / "raw_provider_responses"
    / "provider_recommended_archival_mint_supply_batch_request.json"
)
DEFAULT_RESPONSE_TEMPLATE_PATH = (
    ROOT
    / "data"
    / "reports"
    / "historical_backfill"
    / "raw_provider_responses"
    / "provider_recommended_archival_mint_supply_batch_response_template.json"
)


def provider_recommended_token_mints(pagination_plan_report: dict[str, Any]) -> set[str]:
    rows = pagination_plan_report.get("rows") if isinstance(pagination_plan_report, dict) else []
    mints: set[str] = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if row.get("recommended_action") != "CONSIDER_ARCHIVAL_ACCOUNT_STATE_PROVIDER":
            continue
        mint = str(row.get("token_mint") or "").strip()
        if mint:
            mints.add(mint)
    return mints


def write_provider_recommended_archival_mint_snapshot_request_bundle_report(
    *,
    collection_report_path: Path | str = DEFAULT_COLLECTION_REPORT_PATH,
    pagination_plan_path: Path | str = DEFAULT_PAGINATION_PLAN_PATH,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    raw_response_path: str = DEFAULT_RAW_RESPONSE_PATH,
    batch_request_path: Path | str = DEFAULT_BATCH_REQUEST_PATH,
    response_template_path: Path | str = DEFAULT_RESPONSE_TEMPLATE_PATH,
    batch_chunk_size: int = 100,
    generated_at: float | None = None,
) -> dict[str, Any]:
    pagination_plan_path = Path(pagination_plan_path)
    provider_mints = provider_recommended_token_mints(read_json(pagination_plan_path, {"rows": []}))
    report = write_archival_mint_snapshot_request_bundle_report(
        collection_report_path=collection_report_path,
        report_path=report_path,
        raw_response_path=raw_response_path,
        batch_request_path=batch_request_path,
        response_template_path=response_template_path,
        batch_chunk_size=batch_chunk_size,
        generated_at=generated_at,
        allowed_token_mints=provider_mints,
        source_filter=SOURCE_FILTER,
    )
    report["provider_recommended_token_count"] = len(provider_mints)
    report.setdefault("input_paths", {})
    report["input_paths"]["pagination_plan"] = relative_path(pagination_plan_path, ROOT)

    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a read-only archival mint request bundle for provider-recommended tokens.")
    parser.add_argument("--collection-report-path", type=Path, default=DEFAULT_COLLECTION_REPORT_PATH)
    parser.add_argument("--pagination-plan-path", type=Path, default=DEFAULT_PAGINATION_PLAN_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--raw-response-path", default=DEFAULT_RAW_RESPONSE_PATH)
    parser.add_argument("--batch-request-path", type=Path, default=DEFAULT_BATCH_REQUEST_PATH)
    parser.add_argument("--response-template-path", type=Path, default=DEFAULT_RESPONSE_TEMPLATE_PATH)
    parser.add_argument("--batch-chunk-size", type=int, default=100)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_provider_recommended_archival_mint_snapshot_request_bundle_report(
        collection_report_path=args.collection_report_path,
        pagination_plan_path=args.pagination_plan_path,
        report_path=args.report_path,
        raw_response_path=args.raw_response_path,
        batch_request_path=args.batch_request_path,
        response_template_path=args.response_template_path,
        batch_chunk_size=args.batch_chunk_size,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
