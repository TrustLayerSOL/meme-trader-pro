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

from wallets.forward_merged_calibration_scorecard import build_forward_merged_calibration_scorecard  # noqa: E402


DEFAULT_ORIGINAL_RECORDS = ROOT / "data" / "reports" / "forward_testing" / "forward_outcome_records.jsonl"
DEFAULT_REPAIRED_RECORDS = ROOT / "data" / "reports" / "forward_testing" / "forward_entry_context_resolved_records.jsonl"
DEFAULT_REPORT = ROOT / "data" / "reports" / "forward_testing" / "forward_merged_calibration_scorecard.json"
DEFAULT_MARKDOWN = ROOT / "data" / "reports" / "forward_testing" / "forward_merged_calibration_scorecard.md"


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


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        "# MemeTraderPro Merged Forward Calibration Scorecard",
        "",
        "Review-only scorecard combining original forward outcomes with repaired entry-context rows.",
        "",
        "## Summary",
        "",
        f"- Original records: {summary.get('original_records', 0)}",
        f"- Repaired records: {summary.get('repaired_records', 0)}",
        f"- Replaced original blocked records: {summary.get('replaced_original_blocked_records', 0)}",
        f"- Merged records: {summary.get('merged_records', 0)}",
        f"- Known 15m outcomes: {summary.get('known_15m_outcomes', 0)}",
        f"- Runner 15m outcomes: {summary.get('runner_15m_outcomes', 0)}",
        f"- Flat 15m outcomes: {summary.get('flat_15m_outcomes', 0)}",
        f"- Blocked records: {summary.get('blocked_records', 0)}",
        "",
        "## Wallets",
        "",
        "| Wallet | Status | Records | Known 15m | Runner | Rug | Flat | Blocked |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    scorecard = report.get("scorecard") if isinstance(report.get("scorecard"), dict) else {}
    for row in scorecard.get("wallets") or []:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"| {row.get('wallet')} | {row.get('calibration_status')} | {row.get('records')} | "
            f"{row.get('known_15m')} | {row.get('runner_15m')} | {row.get('rug_15m')} | "
            f"{row.get('flat_15m')} | {row.get('blocked_records')} |"
        )
    lines.extend(
        [
            "",
            "Safety:",
            "- Review-only output.",
            "- Repaired rows are analysis-only.",
            "- Live execution remains locked.",
            "- Wallet trust and wallet lists are not mutated.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_forward_merged_calibration_scorecard(
    *,
    original_records_path: Path | str = DEFAULT_ORIGINAL_RECORDS,
    repaired_records_path: Path | str = DEFAULT_REPAIRED_RECORDS,
    report_path: Path | str = DEFAULT_REPORT,
    markdown_path: Path | str = DEFAULT_MARKDOWN,
    generated_at: float | None = None,
) -> dict[str, Any]:
    original_records_path = Path(original_records_path)
    repaired_records_path = Path(repaired_records_path)
    report_path = Path(report_path)
    markdown_path = Path(markdown_path)
    report = build_forward_merged_calibration_scorecard(
        original_records=read_jsonl(original_records_path),
        repaired_records=read_jsonl(repaired_records_path),
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "forward_outcome_records": relative_path(original_records_path),
        "forward_entry_context_resolved_records": relative_path(repaired_records_path),
    }
    report["output_paths"] = {"report": relative_path(report_path), "markdown": relative_path(markdown_path)}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the review-only merged forward calibration scorecard.")
    parser.add_argument("--original-records", type=Path, default=DEFAULT_ORIGINAL_RECORDS)
    parser.add_argument("--repaired-records", type=Path, default=DEFAULT_REPAIRED_RECORDS)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--markdown-path", type=Path, default=DEFAULT_MARKDOWN)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_forward_merged_calibration_scorecard(
        original_records_path=args.original_records,
        repaired_records_path=args.repaired_records,
        report_path=args.report_path,
        markdown_path=args.markdown_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
