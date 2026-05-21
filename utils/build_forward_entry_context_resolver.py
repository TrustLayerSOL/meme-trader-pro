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

from wallets.forward_entry_context_resolver import build_forward_entry_context_resolver_report  # noqa: E402


DEFAULT_RECORDS = ROOT / "data" / "reports" / "forward_testing" / "forward_outcome_records.jsonl"
DEFAULT_MARKET_CONTEXT = ROOT / "data" / "wallet_backfills" / "forward_market_context_snapshots.jsonl"
DEFAULT_REPORT = ROOT / "data" / "reports" / "forward_testing" / "forward_entry_context_resolver_report.json"
DEFAULT_RESOLVED = ROOT / "data" / "reports" / "forward_testing" / "forward_entry_context_resolved_records.jsonl"
DEFAULT_REJECTED = ROOT / "data" / "reports" / "forward_testing" / "forward_entry_context_resolver_rejected.jsonl"
DEFAULT_MARKDOWN = ROOT / "data" / "reports" / "forward_testing" / "forward_entry_context_resolver_report.md"


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


def write_jsonl(path: Path | str, rows: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def relative_path(path: Path | str) -> str:
    p = Path(path)
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    rejected = summary.get("rejected_reason_counts") if isinstance(summary.get("rejected_reason_counts"), dict) else {}
    lines = [
        "# MemeTraderPro Forward Entry Context Resolver",
        "",
        "Review-only resolver for blocked forward rows that have same-transaction quote anchors and later market snapshots.",
        "",
        "## Summary",
        "",
        f"- Blocked rows scanned: {summary.get('blocked_rows_scanned', 0)}",
        f"- Quote-anchor candidates: {summary.get('quote_anchor_candidates', 0)}",
        f"- Resolved rows: {summary.get('resolved_rows', 0)}",
        f"- Known 15m outcomes after repair: {summary.get('known_15m_outcomes', 0)}",
        f"- Blocked without later snapshot: {summary.get('blocked_no_later_snapshot_rows', 0)}",
        f"- Blocked without valid quote anchor: {summary.get('blocked_no_quote_anchor_rows', 0)}",
        "",
        "## Rejected Reasons",
        "",
    ]
    if rejected:
        for key, value in sorted(rejected.items()):
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "Safety:",
            "- Review-only output.",
            "- Live execution remains locked.",
            "- Wallet trust and wallet lists are not mutated.",
            "- Rows without later snapshot support stay blocked.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_forward_entry_context_resolver_report(
    *,
    records_path: Path | str = DEFAULT_RECORDS,
    market_context_path: Path | str = DEFAULT_MARKET_CONTEXT,
    report_path: Path | str = DEFAULT_REPORT,
    resolved_records_path: Path | str = DEFAULT_RESOLVED,
    rejected_records_path: Path | str = DEFAULT_REJECTED,
    markdown_path: Path | str = DEFAULT_MARKDOWN,
    generated_at: float | None = None,
) -> dict[str, Any]:
    records_path = Path(records_path)
    market_context_path = Path(market_context_path)
    report_path = Path(report_path)
    resolved_records_path = Path(resolved_records_path)
    rejected_records_path = Path(rejected_records_path)
    markdown_path = Path(markdown_path)
    report = build_forward_entry_context_resolver_report(
        records=read_jsonl(records_path),
        market_snapshots=read_jsonl(market_context_path),
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "forward_outcome_records": relative_path(records_path),
        "forward_market_context_snapshots": relative_path(market_context_path),
    }
    report["output_paths"] = {
        "report": relative_path(report_path),
        "resolved_records": relative_path(resolved_records_path),
        "rejected_records": relative_path(rejected_records_path),
        "markdown": relative_path(markdown_path),
    }

    resolved = report.get("resolved_records") if isinstance(report.get("resolved_records"), list) else []
    rejected = report.get("rejected_records") if isinstance(report.get("rejected_records"), list) else []
    report_for_json = {key: value for key, value in report.items() if key not in {"resolved_records", "rejected_records"}}

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report_for_json, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_jsonl(resolved_records_path, resolved)
    write_jsonl(rejected_records_path, rejected)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve review-only forward entry-context rows from quote anchors.")
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    parser.add_argument("--market-context", type=Path, default=DEFAULT_MARKET_CONTEXT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--resolved-records-path", type=Path, default=DEFAULT_RESOLVED)
    parser.add_argument("--rejected-records-path", type=Path, default=DEFAULT_REJECTED)
    parser.add_argument("--markdown-path", type=Path, default=DEFAULT_MARKDOWN)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_forward_entry_context_resolver_report(
        records_path=args.records,
        market_context_path=args.market_context,
        report_path=args.report_path,
        resolved_records_path=args.resolved_records_path,
        rejected_records_path=args.rejected_records_path,
        markdown_path=args.markdown_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
