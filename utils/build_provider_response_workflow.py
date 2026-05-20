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

from wallets.historical_market_context_backfill import relative_path  # noqa: E402
from wallets.provider_response_workflow import build_provider_response_workflow_report  # noqa: E402


DEFAULT_REQUEST_BUNDLE_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "provider_recommended_archival_mint_snapshot_request_bundle_report.json"
)
DEFAULT_RESPONSE_IMPORT_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "provider_recommended_archival_mint_snapshot_response_import_report.json"
)
DEFAULT_PROOF_READINESS_PATH = (
    ROOT / "data" / "reports" / "replay_validation" / "proof_readiness_blocker_reduction_report.json"
)
DEFAULT_COMBINED_RAW_RESPONSE_PATH = (
    ROOT
    / "data"
    / "reports"
    / "historical_backfill"
    / "raw_provider_responses"
    / "provider_recommended_archival_mint_supply_batch_raw.json"
)
DEFAULT_REPORT_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "provider_response_workflow_report.json"
)


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    return parsed if isinstance(parsed, dict) else default


def write_provider_response_workflow_report(
    *,
    request_bundle_path: Path | str = DEFAULT_REQUEST_BUNDLE_PATH,
    response_import_path: Path | str = DEFAULT_RESPONSE_IMPORT_PATH,
    proof_readiness_path: Path | str = DEFAULT_PROOF_READINESS_PATH,
    combined_raw_response_path: Path | str = DEFAULT_COMBINED_RAW_RESPONSE_PATH,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    root: Path | str = ROOT,
    generated_at: float | None = None,
) -> dict[str, Any]:
    root = Path(root)
    request_bundle_path = Path(request_bundle_path)
    response_import_path = Path(response_import_path)
    proof_readiness_path = Path(proof_readiness_path)
    combined_raw_response_path = Path(combined_raw_response_path)
    report_path = Path(report_path)
    report = build_provider_response_workflow_report(
        request_bundle_report=read_json(request_bundle_path, {"summary": {}, "response_template_chunks": []}),
        combined_raw_response_path=combined_raw_response_path,
        response_import_report=read_json(response_import_path, {"summary": {}}),
        proof_readiness_report=read_json(proof_readiness_path, {"summary": {}}),
        root=root,
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "request_bundle": relative_path(request_bundle_path, ROOT),
        "response_import": relative_path(response_import_path, ROOT),
        "proof_readiness": relative_path(proof_readiness_path, ROOT),
        "combined_raw_response": relative_path(combined_raw_response_path, ROOT),
    }
    report["output_paths"] = {"report": relative_path(report_path, ROOT)}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect the focused provider-response workflow without importing evidence.")
    parser.add_argument("--request-bundle-path", type=Path, default=DEFAULT_REQUEST_BUNDLE_PATH)
    parser.add_argument("--response-import-path", type=Path, default=DEFAULT_RESPONSE_IMPORT_PATH)
    parser.add_argument("--proof-readiness-path", type=Path, default=DEFAULT_PROOF_READINESS_PATH)
    parser.add_argument("--combined-raw-response-path", type=Path, default=DEFAULT_COMBINED_RAW_RESPONSE_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_provider_response_workflow_report(
        request_bundle_path=args.request_bundle_path,
        response_import_path=args.response_import_path,
        proof_readiness_path=args.proof_readiness_path,
        combined_raw_response_path=args.combined_raw_response_path,
        report_path=args.report_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(f"Next action: {report['next_action']['code']} - {report['next_action']['detail']}")
    print(f"Report: {report['output_paths']['report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
