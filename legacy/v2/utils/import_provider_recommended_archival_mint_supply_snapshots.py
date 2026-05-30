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

from utils.build_provider_recommended_archival_mint_snapshot_request_bundle import (  # noqa: E402
    DEFAULT_PAGINATION_PLAN_PATH,
    DEFAULT_RAW_RESPONSE_PATH,
    SOURCE_FILTER,
    provider_recommended_token_mints,
)
from utils.collect_archival_mint_supply_snapshots import read_json  # noqa: E402
from utils.import_archival_mint_supply_snapshots import (  # noqa: E402
    DEFAULT_COLLECTION_REPORT_PATH,
    DEFAULT_SNAPSHOTS_PATH,
    write_archival_mint_snapshot_response_import_report,
)
from wallets.historical_market_context_backfill import relative_path  # noqa: E402


DEFAULT_REPORT_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "provider_recommended_archival_mint_snapshot_response_import_report.json"
)


def write_provider_recommended_archival_mint_snapshot_response_import_report(
    *,
    collection_report_path: Path | str = DEFAULT_COLLECTION_REPORT_PATH,
    pagination_plan_path: Path | str = DEFAULT_PAGINATION_PLAN_PATH,
    raw_response_path: Path | str = ROOT / DEFAULT_RAW_RESPONSE_PATH,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    snapshots_path: Path | str = DEFAULT_SNAPSHOTS_PATH,
    generated_at: float | None = None,
) -> dict[str, Any]:
    pagination_plan_path = Path(pagination_plan_path)
    provider_mints = provider_recommended_token_mints(read_json(pagination_plan_path, {"rows": []}))
    report = write_archival_mint_snapshot_response_import_report(
        collection_report_path=collection_report_path,
        raw_response_path=raw_response_path,
        report_path=report_path,
        snapshots_path=snapshots_path,
        allowed_token_mints=provider_mints,
        source_filter=SOURCE_FILTER,
        generated_at=generated_at,
    )
    report["provider_recommended_token_count"] = len(provider_mints)
    report.setdefault("input_paths", {})
    report["input_paths"]["pagination_plan"] = relative_path(pagination_plan_path, ROOT)

    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import saved archival mint snapshots for provider-recommended tokens only.")
    parser.add_argument("--collection-report-path", type=Path, default=DEFAULT_COLLECTION_REPORT_PATH)
    parser.add_argument("--pagination-plan-path", type=Path, default=DEFAULT_PAGINATION_PLAN_PATH)
    parser.add_argument("--raw-response-path", type=Path, default=ROOT / DEFAULT_RAW_RESPONSE_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--snapshots-path", type=Path, default=DEFAULT_SNAPSHOTS_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_provider_recommended_archival_mint_snapshot_response_import_report(
        collection_report_path=args.collection_report_path,
        pagination_plan_path=args.pagination_plan_path,
        raw_response_path=args.raw_response_path,
        report_path=args.report_path,
        snapshots_path=args.snapshots_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
