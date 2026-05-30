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

from wallets.candidate_outcome_window_completion import build_candidate_outcome_window_completion  # noqa: E402


DEFAULT_RESOLVED = (
    ROOT
    / "data"
    / "reports"
    / "forward_testing"
    / "candidate_walk_forward"
    / "candidate_entry_price_anchor_resolved_records_20260525-candidate-entry-price-anchor-repair.jsonl"
)
DEFAULT_REJECTED = (
    ROOT
    / "data"
    / "reports"
    / "forward_testing"
    / "candidate_walk_forward"
    / "candidate_entry_price_anchor_resolver_rejected_20260525-candidate-entry-price-anchor-repair.jsonl"
)
DEFAULT_OUTPUT_DIR = ROOT / "data" / "reports" / "forward_testing" / "candidate_walk_forward"

AUDIT_FIELDS = [
    "event_id",
    "wallet_address",
    "token_address",
    "signal_time",
    "transaction_signature",
    "outcome_15m",
    "completion_status",
    "reason",
    "promotion_allowed",
    "wallet_trust_mutation_allowed",
    "wallet_list_mutation_allowed",
]

QUEUE_FIELDS = [
    "event_id",
    "wallet_address",
    "token_address",
    "observed_action",
    "signal_time",
    "transaction_signature",
    "target_window",
    "evaluation_horizon_seconds",
    "needed_snapshot_start",
    "needed_snapshot_end",
    "blocker_type",
    "recommended_action",
    "source_record_status",
    "priority_rank",
    "promotion_allowed",
    "wallet_trust_mutation_allowed",
    "wallet_list_mutation_allowed",
]


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


def write_csv(path: Path | str, rows: list[dict[str, Any]], fields: list[str]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        "# Candidate Outcome Window Completion",
        "",
        "Review-only queue for completing unresolved 15m outcome windows after candidate entry-price anchor repair.",
        "",
        "## Summary",
        "",
        f"- Records scanned: {summary.get('records_scanned', 0)}",
        f"- Known 15m rows: {summary.get('known_15m_rows', 0)}",
        f"- Unresolved 15m rows: {summary.get('unresolved_15m_rows', 0)}",
        f"- Rejected missing later snapshot rows: {summary.get('rejected_missing_later_snapshot_rows', 0)}",
        f"- Capture queue rows: {summary.get('capture_queue_rows', 0)}",
        f"- Unique tokens to capture: {summary.get('unique_tokens_to_capture', 0)}",
        f"- Promotions allowed: {summary.get('promotions_allowed', 0)}",
        "",
        "## Queue Preview",
        "",
        "| Wallet | Token | Blocker | Window | Needed End | Action |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]
    for row in (report.get("capture_queue") or [])[:25]:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"| `{row.get('wallet_address')}` | `{row.get('token_address')}` | {row.get('blocker_type')} | "
            f"{row.get('target_window')} | {row.get('needed_snapshot_end')} | {row.get('recommended_action')} |"
        )
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "- Review-only output.",
            "- No outcome labels are invented.",
            "- No live trading.",
            "- No wallet promotion.",
            "- No wallet trust mutation.",
            "- No wallet-list mutation.",
        ]
    )
    return "\n".join(lines) + "\n"


def default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def write_candidate_outcome_window_completion(
    *,
    resolved_records_path: Path | str = DEFAULT_RESOLVED,
    rejected_records_path: Path | str = DEFAULT_REJECTED,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    run_id: str | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    run_id = run_id or default_run_id()
    report = build_candidate_outcome_window_completion(
        resolved_records=read_jsonl(resolved_records_path),
        rejected_records=read_jsonl(rejected_records_path),
        generated_at=generated_at,
    )
    output = Path(output_dir)
    json_path = output / f"candidate_outcome_window_completion_{run_id}.json"
    audit_csv_path = output / f"candidate_outcome_window_completion_{run_id}.csv"
    queue_csv_path = output / f"candidate_outcome_window_capture_queue_{run_id}.csv"
    md_path = output / f"candidate_outcome_window_completion_{run_id}.md"
    report["run_id"] = run_id
    report["input_paths"] = {
        "resolved_records": str(resolved_records_path),
        "rejected_records": str(rejected_records_path),
    }
    report["output_paths"] = {
        "json": str(json_path),
        "csv": str(audit_csv_path),
        "capture_queue_csv": str(queue_csv_path),
        "markdown": str(md_path),
    }
    write_json(json_path, report)
    write_json(output / "candidate_outcome_window_completion.json", report)
    write_csv(audit_csv_path, [row for row in report.get("audit_rows", []) if isinstance(row, dict)], AUDIT_FIELDS)
    write_csv(queue_csv_path, [row for row in report.get("capture_queue", []) if isinstance(row, dict)], QUEUE_FIELDS)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build candidate outcome window completion queue.")
    parser.add_argument("--resolved-records", type=Path, default=DEFAULT_RESOLVED)
    parser.add_argument("--rejected-records", type=Path, default=DEFAULT_REJECTED)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-id", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_candidate_outcome_window_completion(
        resolved_records_path=args.resolved_records,
        rejected_records_path=args.rejected_records,
        output_dir=args.output_dir,
        run_id=args.run_id,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(json.dumps(report["output_paths"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
