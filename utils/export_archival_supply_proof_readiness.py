#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wallets.archival_supply_proof_exports import (  # noqa: E402
    REJECTED_COLUMNS,
    VALID_EVIDENCE_COLUMNS,
    build_archival_supply_proof_export,
    json_cell,
)
from wallets.historical_market_context_backfill import relative_path  # noqa: E402


DEFAULT_REQUEST_BUNDLE_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "archival_mint_snapshot_request_bundle_report.json"
)
DEFAULT_RESPONSE_IMPORT_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "archival_mint_snapshot_response_import_report.json"
)
DEFAULT_ARCHIVAL_SUPPLY_EVIDENCE_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "archival_supply_evidence_report.json"
)
DEFAULT_SCORE_READY_MARKET_CONTEXT_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "score_ready_market_context_report.json"
)
DEFAULT_PROOF_READINESS_PATH = (
    ROOT / "data" / "reports" / "replay_validation" / "proof_readiness_blocker_reduction_report.json"
)
DEFAULT_MARKDOWN_PATH = (
    ROOT / "data" / "reports" / "replay_validation" / "archival_supply_proof_readiness_report.md"
)
DEFAULT_EVIDENCE_CSV_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "archival_supply_evidence_table.csv"
)
DEFAULT_REJECTED_CSV_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "archival_supply_rejected_rows.csv"
)
DEFAULT_SUMMARY_JSON_PATH = (
    ROOT / "data" / "reports" / "replay_validation" / "archival_supply_proof_readiness_summary.json"
)


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    return parsed if isinstance(parsed, dict) else default


def write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: json_cell(row.get(column)) for column in columns})


def write_archival_supply_proof_exports(
    *,
    request_bundle_path: Path | str = DEFAULT_REQUEST_BUNDLE_PATH,
    response_import_path: Path | str = DEFAULT_RESPONSE_IMPORT_PATH,
    archival_supply_evidence_path: Path | str = DEFAULT_ARCHIVAL_SUPPLY_EVIDENCE_PATH,
    score_ready_market_context_path: Path | str = DEFAULT_SCORE_READY_MARKET_CONTEXT_PATH,
    proof_readiness_path: Path | str = DEFAULT_PROOF_READINESS_PATH,
    markdown_path: Path | str = DEFAULT_MARKDOWN_PATH,
    evidence_csv_path: Path | str = DEFAULT_EVIDENCE_CSV_PATH,
    rejected_csv_path: Path | str = DEFAULT_REJECTED_CSV_PATH,
    summary_json_path: Path | str = DEFAULT_SUMMARY_JSON_PATH,
    generated_at: float | None = None,
) -> dict[str, Any]:
    request_bundle_path = Path(request_bundle_path)
    response_import_path = Path(response_import_path)
    archival_supply_evidence_path = Path(archival_supply_evidence_path)
    score_ready_market_context_path = Path(score_ready_market_context_path)
    proof_readiness_path = Path(proof_readiness_path)
    markdown_path = Path(markdown_path)
    evidence_csv_path = Path(evidence_csv_path)
    rejected_csv_path = Path(rejected_csv_path)
    summary_json_path = Path(summary_json_path)

    report = build_archival_supply_proof_export(
        request_bundle_report=read_json(request_bundle_path, {}),
        response_import_report=read_json(response_import_path, {}),
        archival_supply_evidence_report=read_json(archival_supply_evidence_path, {}),
        score_ready_market_context_report=read_json(score_ready_market_context_path, {}),
        proof_readiness_report=read_json(proof_readiness_path, {}),
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "request_bundle": relative_path(request_bundle_path, ROOT),
        "response_import": relative_path(response_import_path, ROOT),
        "archival_supply_evidence": relative_path(archival_supply_evidence_path, ROOT),
        "score_ready_market_context": relative_path(score_ready_market_context_path, ROOT),
        "proof_readiness": relative_path(proof_readiness_path, ROOT),
    }
    report["output_paths"] = {
        "markdown": relative_path(markdown_path, ROOT),
        "evidence_csv": relative_path(evidence_csv_path, ROOT),
        "rejected_csv": relative_path(rejected_csv_path, ROOT),
        "summary_json": relative_path(summary_json_path, ROOT),
    }

    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    summary_json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(report["markdown"] + "\n", encoding="utf-8")
    write_csv(evidence_csv_path, VALID_EVIDENCE_COLUMNS, report["valid_evidence_rows"])
    write_csv(rejected_csv_path, REJECTED_COLUMNS, report["rejected_rows"])
    summary_json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export archival supply proof-readiness audit artifacts.")
    parser.add_argument("--request-bundle-path", type=Path, default=DEFAULT_REQUEST_BUNDLE_PATH)
    parser.add_argument("--response-import-path", type=Path, default=DEFAULT_RESPONSE_IMPORT_PATH)
    parser.add_argument("--archival-supply-evidence-path", type=Path, default=DEFAULT_ARCHIVAL_SUPPLY_EVIDENCE_PATH)
    parser.add_argument("--score-ready-market-context-path", type=Path, default=DEFAULT_SCORE_READY_MARKET_CONTEXT_PATH)
    parser.add_argument("--proof-readiness-path", type=Path, default=DEFAULT_PROOF_READINESS_PATH)
    parser.add_argument("--markdown-path", type=Path, default=DEFAULT_MARKDOWN_PATH)
    parser.add_argument("--evidence-csv-path", type=Path, default=DEFAULT_EVIDENCE_CSV_PATH)
    parser.add_argument("--rejected-csv-path", type=Path, default=DEFAULT_REJECTED_CSV_PATH)
    parser.add_argument("--summary-json-path", type=Path, default=DEFAULT_SUMMARY_JSON_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_archival_supply_proof_exports(
        request_bundle_path=args.request_bundle_path,
        response_import_path=args.response_import_path,
        archival_supply_evidence_path=args.archival_supply_evidence_path,
        score_ready_market_context_path=args.score_ready_market_context_path,
        proof_readiness_path=args.proof_readiness_path,
        markdown_path=args.markdown_path,
        evidence_csv_path=args.evidence_csv_path,
        rejected_csv_path=args.rejected_csv_path,
        summary_json_path=args.summary_json_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
