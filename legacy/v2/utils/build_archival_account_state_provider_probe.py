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

from utils.build_archival_account_state_provider_evaluation import DEFAULT_REPORT_PATH as DEFAULT_PROVIDER_EVALUATION_PATH  # noqa: E402
from utils.build_archival_mint_pagination_plan import DEFAULT_REPORT_PATH as DEFAULT_PAGINATION_PLAN_PATH  # noqa: E402
from utils.collect_archival_mint_history import read_json  # noqa: E402
from wallets.archival_account_state_provider_probe import build_archival_account_state_provider_probe_report  # noqa: E402
from wallets.historical_market_context_backfill import relative_path  # noqa: E402


DEFAULT_REPORT_PATH = ROOT / "data" / "reports" / "historical_backfill" / "archival_account_state_provider_probe_report.json"
DEFAULT_PRESERVED_RAW_RESPONSE_PATH = (
    ROOT
    / "data"
    / "reports"
    / "historical_backfill"
    / "raw_provider_responses"
    / "archival_account_state_provider_probe_raw.json"
)


def read_optional_json(path: Path | str | None) -> Any | None:
    if path is None:
        return None
    path = Path(path)
    if not path.exists():
        return None
    return read_json(path, None)


def preserve_raw_response(path: Path, raw_provider_response: Any | None) -> bool:
    if raw_provider_response is None:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw_provider_response, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return True


def write_archival_account_state_provider_probe_report(
    *,
    pagination_plan_path: Path | str = DEFAULT_PAGINATION_PLAN_PATH,
    provider_evaluation_path: Path | str = DEFAULT_PROVIDER_EVALUATION_PATH,
    raw_provider_response_path: Path | str | None = None,
    preserved_raw_response_path: Path | str = DEFAULT_PRESERVED_RAW_RESPONSE_PATH,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    generated_at: float | None = None,
) -> dict[str, Any]:
    pagination_plan_path = Path(pagination_plan_path)
    provider_evaluation_path = Path(provider_evaluation_path)
    preserved_raw_response_path = Path(preserved_raw_response_path)
    report_path = Path(report_path)
    raw_provider_response = read_optional_json(raw_provider_response_path)
    raw_preserved = preserve_raw_response(preserved_raw_response_path, raw_provider_response)
    report = build_archival_account_state_provider_probe_report(
        pagination_plan=read_json(pagination_plan_path, {"rows": []}),
        provider_evaluation=read_json(provider_evaluation_path, {"providers": []}),
        raw_provider_response=raw_provider_response if isinstance(raw_provider_response, dict) else None,
        raw_provider_response_preserved=raw_preserved,
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "pagination_plan": relative_path(pagination_plan_path, ROOT),
        "provider_evaluation": relative_path(provider_evaluation_path, ROOT),
        "raw_provider_response": None if raw_provider_response_path is None else relative_path(Path(raw_provider_response_path), ROOT),
    }
    report["output_paths"] = {
        "report": relative_path(report_path, ROOT),
        "preserved_raw_response": relative_path(preserved_raw_response_path, ROOT) if raw_preserved else None,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build read-only archival account-state provider probe report.")
    parser.add_argument("--pagination-plan-path", type=Path, default=DEFAULT_PAGINATION_PLAN_PATH)
    parser.add_argument("--provider-evaluation-path", type=Path, default=DEFAULT_PROVIDER_EVALUATION_PATH)
    parser.add_argument("--raw-provider-response-path", type=Path, default=None)
    parser.add_argument("--preserved-raw-response-path", type=Path, default=DEFAULT_PRESERVED_RAW_RESPONSE_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_archival_account_state_provider_probe_report(
        pagination_plan_path=args.pagination_plan_path,
        provider_evaluation_path=args.provider_evaluation_path,
        raw_provider_response_path=args.raw_provider_response_path,
        preserved_raw_response_path=args.preserved_raw_response_path,
        report_path=args.report_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
