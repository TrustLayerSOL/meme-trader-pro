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

from utils.build_archival_mint_history_progress import DEFAULT_REPORT_PATH as DEFAULT_PROGRESS_PATH  # noqa: E402
from utils.collect_archival_mint_history import read_json  # noqa: E402
from wallets.archival_mint_pagination_planner import build_archival_mint_pagination_plan_report  # noqa: E402
from wallets.historical_market_context_backfill import relative_path  # noqa: E402


DEFAULT_REPORT_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_mint_pagination_plan_report.json"


def write_archival_mint_pagination_plan_report(
    *,
    progress_path: Path | str = DEFAULT_PROGRESS_PATH,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    page_size: int = 100,
    pages_per_batch: int = 10,
    provider_threshold_signatures: int = 2000,
    generated_at: float | None = None,
) -> dict[str, Any]:
    progress_path = Path(progress_path)
    report_path = Path(report_path)
    report = build_archival_mint_pagination_plan_report(
        progress_report=read_json(progress_path, {"rows": []}),
        page_size=page_size,
        pages_per_batch=pages_per_batch,
        provider_threshold_signatures=provider_threshold_signatures,
        generated_at=generated_at,
    )
    report["input_paths"] = {"progress": relative_path(progress_path, ROOT)}
    report["output_paths"] = {"report": relative_path(report_path, ROOT)}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build read-only mint-history pagination plan from checkpoint progress.")
    parser.add_argument("--progress-path", type=Path, default=DEFAULT_PROGRESS_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--pages-per-batch", type=int, default=10)
    parser.add_argument("--provider-threshold-signatures", type=int, default=2000)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_archival_mint_pagination_plan_report(
        progress_path=args.progress_path,
        report_path=args.report_path,
        page_size=args.page_size,
        pages_per_batch=args.pages_per_batch,
        provider_threshold_signatures=args.provider_threshold_signatures,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
