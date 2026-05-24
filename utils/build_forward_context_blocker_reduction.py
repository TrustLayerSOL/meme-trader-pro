#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wallets.forward_context_blocker_reduction import build_forward_context_blocker_reduction  # noqa: E402


DEFAULT_RECOMMENDATIONS = ROOT / "data" / "reports" / "forward_testing" / "forward_merged_calibration_recommendations.json"
DEFAULT_REPAIR_PLAN = ROOT / "data" / "reports" / "forward_testing" / "forward_entry_context_repair_plan.json"
DEFAULT_RESOLVER = ROOT / "data" / "reports" / "forward_testing" / "forward_entry_context_resolver_report.json"
DEFAULT_REJECTED = ROOT / "data" / "reports" / "forward_testing" / "forward_entry_context_resolver_rejected.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "reports" / "forward_testing" / "context_blocker_reduction"


FIELDS = [
    "wallet_address",
    "recommendation_bucket",
    "total_records",
    "known_15m_outcomes",
    "runner_15m_count",
    "flat_15m_count",
    "loser_15m_count",
    "blocked_record_count",
    "context_completion_rate",
    "repair_plan_blocked_rows",
    "unique_blocked_tokens",
    "quote_anchor_repair_rows",
    "quote_anchor_and_snapshot_rows",
    "quote_anchor_without_snapshot_rows",
    "needs_market_snapshot_rows",
    "partial_context_rows",
    "missing_later_market_snapshot_rows",
    "missing_valid_execution_price_quote_rows",
    "repair_action",
    "recommended_context_action",
    "priority_rank",
    "priority_reason",
    "next_operator_step",
    "promotion_allowed",
    "can_mutate_wallet_trust",
    "wallet_list_mutation_allowed",
]


def read_json(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    parsed = json.loads(p.read_text(encoding="utf-8"))
    return parsed if isinstance(parsed, dict) else {}


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


def write_json(path: Path | str, payload: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path | str, rows: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDS})


def relative_path(path: Path | str) -> str:
    p = Path(path)
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        "# Forward Context Blocker Reduction",
        "",
        "Review-only priority queue for reducing missing forward entry-context blockers. This is not a promotion surface.",
        "",
        "## Summary",
        "",
        f"- Fix-context wallets: {summary.get('fix_context_wallets', 0)}",
        f"- Blocked records: {summary.get('blocked_records', 0)}",
        f"- Missing later market snapshot rows: {summary.get('missing_later_market_snapshot_rows', 0)}",
        f"- Missing valid execution price quote rows: {summary.get('missing_valid_execution_price_quote_rows', 0)}",
        f"- Priority market snapshot wallets: {summary.get('priority_market_snapshot_wallets', 0)}",
        f"- Priority entry timestamp wallets: {summary.get('priority_entry_timestamp_wallets', 0)}",
        f"- Promotions allowed: {summary.get('promotions_allowed', 0)}",
        "",
        "## Priority Queue",
        "",
        "| Wallet | Action | Blocked | Missing Snapshots | Missing Quote | Tokens | Context | Next Step |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in report.get("wallets") or []:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"| `{row.get('wallet_address')}` | {row.get('recommended_context_action')} | "
            f"{row.get('blocked_record_count')} | {row.get('missing_later_market_snapshot_rows')} | "
            f"{row.get('missing_valid_execution_price_quote_rows')} | {row.get('unique_blocked_tokens')} | "
            f"{row.get('context_completion_rate')} | {row.get('next_operator_step')} |"
        )
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- Review-only output.",
            "- Live execution remains locked.",
            "- Wallet trust is not mutated.",
            "- Wallet lists are not mutated.",
            "- No wallet is promoted.",
        ]
    )
    return "\n".join(lines) + "\n"


def default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def write_forward_context_blocker_reduction(
    *,
    recommendations_path: Path | str = DEFAULT_RECOMMENDATIONS,
    repair_plan_path: Path | str = DEFAULT_REPAIR_PLAN,
    resolver_report_path: Path | str = DEFAULT_RESOLVER,
    rejected_records_path: Path | str = DEFAULT_REJECTED,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    run_id: str | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    run_id = run_id or default_run_id()
    output_dir = Path(output_dir)
    report = build_forward_context_blocker_reduction(
        recommendations=read_json(recommendations_path),
        repair_plan=read_json(repair_plan_path),
        resolver_report=read_json(resolver_report_path),
        rejected_records=read_jsonl(rejected_records_path),
        run_id=run_id,
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "forward_merged_calibration_recommendations": relative_path(recommendations_path),
        "forward_entry_context_repair_plan": relative_path(repair_plan_path),
        "forward_entry_context_resolver_report": relative_path(resolver_report_path),
        "forward_entry_context_resolver_rejected": relative_path(rejected_records_path),
    }
    json_path = output_dir / f"forward_context_blocker_reduction_{run_id}.json"
    csv_path = output_dir / f"forward_context_blocker_reduction_{run_id}.csv"
    md_path = output_dir / f"forward_context_blocker_reduction_{run_id}.md"
    output_paths = {
        "json": relative_path(json_path),
        "csv": relative_path(csv_path),
        "markdown": relative_path(md_path),
    }
    report["output_paths"] = output_paths
    write_json(json_path, report)
    write_csv(csv_path, report.get("wallets") or [])
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(report), encoding="utf-8")
    write_json(output_dir / "forward_context_blocker_reduction.json", report)
    (output_dir / "forward_context_blocker_reduction.md").write_text(render_markdown(report), encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the review-only forward context blocker reduction packet.")
    parser.add_argument("--recommendations", type=Path, default=DEFAULT_RECOMMENDATIONS)
    parser.add_argument("--repair-plan", type=Path, default=DEFAULT_REPAIR_PLAN)
    parser.add_argument("--resolver-report", type=Path, default=DEFAULT_RESOLVER)
    parser.add_argument("--rejected-records", type=Path, default=DEFAULT_REJECTED)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-id", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_forward_context_blocker_reduction(
        recommendations_path=args.recommendations,
        repair_plan_path=args.repair_plan,
        resolver_report_path=args.resolver_report,
        rejected_records_path=args.rejected_records,
        output_dir=args.output_dir,
        run_id=args.run_id,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(json.dumps(report["output_paths"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
