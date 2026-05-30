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

from wallets.forward_outcome_resolution import build_forward_outcome_resolution_report
from wallets.forward_outcome_resolution import render_daily_forward_calibration_markdown


DEFAULT_EVIDENCE = ROOT / "data" / "wallet_evidence" / "wallet_history_evidence.jsonl"
DEFAULT_MARKET_CONTEXT = ROOT / "data" / "wallet_backfills" / "forward_market_context_snapshots.jsonl"
DEFAULT_REPORT = ROOT / "data" / "reports" / "forward_testing" / "forward_outcome_resolution_report.json"
DEFAULT_RECORDS = ROOT / "data" / "reports" / "forward_testing" / "forward_outcome_records.jsonl"
DEFAULT_DAILY_JSON = ROOT / "data" / "reports" / "forward_testing" / "daily_forward_calibration_report.json"
DEFAULT_DAILY_MD = ROOT / "data" / "reports" / "forward_testing" / "daily_forward_calibration_report.md"


def read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                rows.append(parsed)
    return rows


def relative_path(path: Path | str) -> str:
    p = Path(path)
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def write_jsonl(path: Path | str, rows: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def write_forward_outcome_resolution_report(
    *,
    evidence_path: Path | str = DEFAULT_EVIDENCE,
    market_context_path: Path | str = DEFAULT_MARKET_CONTEXT,
    report_path: Path | str = DEFAULT_REPORT,
    records_path: Path | str = DEFAULT_RECORDS,
    daily_json_path: Path | str = DEFAULT_DAILY_JSON,
    daily_markdown_path: Path | str = DEFAULT_DAILY_MD,
    generated_at: float | None = None,
) -> dict[str, Any]:
    evidence_path = Path(evidence_path)
    market_context_path = Path(market_context_path)
    report_path = Path(report_path)
    records_path = Path(records_path)
    daily_json_path = Path(daily_json_path)
    daily_markdown_path = Path(daily_markdown_path)

    report = build_forward_outcome_resolution_report(
        evidence_records=read_jsonl(evidence_path),
        market_snapshots=read_jsonl(market_context_path),
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "wallet_history_evidence": relative_path(evidence_path),
        "forward_market_context_snapshots": relative_path(market_context_path),
    }
    report["output_paths"] = {
        "report": relative_path(report_path),
        "records": relative_path(records_path),
        "daily_json": relative_path(daily_json_path),
        "daily_markdown": relative_path(daily_markdown_path),
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_jsonl(records_path, report.get("records") or [])

    daily = report.get("daily_calibration") if isinstance(report.get("daily_calibration"), dict) else {}
    daily_json_path.parent.mkdir(parents=True, exist_ok=True)
    daily_json_path.write_text(json.dumps(daily, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    daily_markdown_path.parent.mkdir(parents=True, exist_ok=True)
    daily_markdown_path.write_text(render_daily_forward_calibration_markdown(daily), encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve review-only forward outcome windows from captured market snapshots.")
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--market-context", type=Path, default=DEFAULT_MARKET_CONTEXT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--records-path", type=Path, default=DEFAULT_RECORDS)
    parser.add_argument("--daily-json-path", type=Path, default=DEFAULT_DAILY_JSON)
    parser.add_argument("--daily-markdown-path", type=Path, default=DEFAULT_DAILY_MD)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_forward_outcome_resolution_report(
        evidence_path=args.evidence,
        market_context_path=args.market_context,
        report_path=args.report_path,
        records_path=args.records_path,
        daily_json_path=args.daily_json_path,
        daily_markdown_path=args.daily_markdown_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
