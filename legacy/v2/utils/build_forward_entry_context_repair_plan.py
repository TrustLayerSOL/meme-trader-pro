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

from wallets.forward_entry_context_repair_plan import build_forward_entry_context_repair_plan  # noqa: E402


DEFAULT_RECORDS = ROOT / "data" / "reports" / "forward_testing" / "forward_outcome_records.jsonl"
DEFAULT_MARKET_CONTEXT = ROOT / "data" / "wallet_backfills" / "forward_market_context_snapshots.jsonl"
DEFAULT_REPORT = ROOT / "data" / "reports" / "forward_testing" / "forward_entry_context_repair_plan.json"
DEFAULT_MARKDOWN = ROOT / "data" / "reports" / "forward_testing" / "forward_entry_context_repair_plan.md"


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
        "# MemeTraderPro Forward Entry Context Repair Plan",
        "",
        "Review-only queue for forward rows blocked by missing entry price context.",
        "",
        "## Summary",
        "",
        f"- Wallets: {summary.get('wallets', 0)}",
        f"- Blocked rows: {summary.get('blocked_rows', 0)}",
        f"- Quote-anchor repair rows: {summary.get('quote_anchor_repair_rows', 0)}",
        f"- Quote-anchor rows with later snapshots: {summary.get('quote_anchor_and_snapshot_rows', 0)}",
        f"- Quote-anchor rows without later snapshots: {summary.get('quote_anchor_without_snapshot_rows', 0)}",
        f"- Needs market snapshot rows: {summary.get('needs_market_snapshot_rows', 0)}",
        f"- Partial context rows: {summary.get('partial_context_rows', 0)}",
        "",
        "## Wallet Repair Queue",
        "",
        "| Wallet | Action | Blocked | Quote Repair | Quote+Snapshot | Quote No Snapshot | Needs Snapshot | Partial | Tokens |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in report.get("wallets") or []:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"| {row.get('wallet')} | {row.get('repair_action')} | {row.get('blocked_rows')} | "
            f"{row.get('quote_anchor_repair_rows')} | {row.get('quote_anchor_and_snapshot_rows')} | "
            f"{row.get('quote_anchor_without_snapshot_rows')} | {row.get('needs_market_snapshot_rows')} | "
            f"{row.get('partial_context_rows')} | {row.get('tokens')} |"
        )
    lines.extend(
        [
            "",
            "Safety:",
            "- Review-only output.",
            "- Live execution remains locked.",
            "- Wallet trust and wallet lists are not mutated.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_forward_entry_context_repair_plan(
    *,
    records_path: Path | str = DEFAULT_RECORDS,
    market_context_path: Path | str = DEFAULT_MARKET_CONTEXT,
    report_path: Path | str = DEFAULT_REPORT,
    markdown_path: Path | str = DEFAULT_MARKDOWN,
    generated_at: float | None = None,
) -> dict[str, Any]:
    records_path = Path(records_path)
    market_context_path = Path(market_context_path)
    report_path = Path(report_path)
    markdown_path = Path(markdown_path)
    report = build_forward_entry_context_repair_plan(
        read_jsonl(records_path),
        market_snapshots=read_jsonl(market_context_path),
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "forward_outcome_records": relative_path(records_path),
        "forward_market_context_snapshots": relative_path(market_context_path),
    }
    report["output_paths"] = {"report": relative_path(report_path), "markdown": relative_path(markdown_path)}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the review-only forward entry-context repair plan.")
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    parser.add_argument("--market-context", type=Path, default=DEFAULT_MARKET_CONTEXT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--markdown-path", type=Path, default=DEFAULT_MARKDOWN)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_forward_entry_context_repair_plan(
        records_path=args.records,
        market_context_path=args.market_context,
        report_path=args.report_path,
        markdown_path=args.markdown_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
