#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wallets.candidate_bounded_snapshot_capture import build_candidate_bounded_snapshot_capture  # noqa: E402


DEFAULT_OUTCOME_COMPLETION = (
    ROOT
    / "data"
    / "reports"
    / "forward_testing"
    / "candidate_walk_forward"
    / "candidate_outcome_window_completion.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "data" / "reports" / "forward_testing" / "candidate_walk_forward"

SNAPSHOT_FIELDS = [
    "mint",
    "time",
    "source",
    "price",
    "liquidity",
    "market_cap",
    "risk_label",
    "candidate_snapshot_capture",
]

DEFERRED_FIELDS = [
    "event_id",
    "wallet_address",
    "token_address",
    "signal_time",
    "needed_snapshot_start",
    "needed_snapshot_end",
    "defer_reason",
    "recommended_next_action",
    "promotion_allowed",
    "wallet_trust_mutation_allowed",
    "wallet_list_mutation_allowed",
]


def read_json(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        parsed = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def write_json(path: Path | str, payload: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path | str, rows: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


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
    budget = report.get("budget") if isinstance(report.get("budget"), dict) else {}
    lines = [
        "# Candidate Bounded Snapshot Capture",
        "",
        "Review-only bounded current snapshot capture for candidate outcome windows. Expired 15m windows are deferred to archival/onchain recovery.",
        "",
        "## Summary",
        "",
        f"- Input capture queue rows: {summary.get('input_capture_queue_rows', 0)}",
        f"- Deduped capture queue rows: {summary.get('deduped_capture_queue_rows', 0)}",
        f"- Capture eligible rows: {summary.get('capture_eligible_rows', 0)}",
        f"- Deferred expired window rows: {summary.get('deferred_expired_window_rows', 0)}",
        f"- Current snapshots captured: {summary.get('current_snapshots_captured', 0)}",
        f"- Provider misses: {summary.get('provider_misses', 0)}",
        f"- Deferred rows: {summary.get('deferred_rows', 0)}",
        f"- Budget status: `{budget.get('budget_status')}`",
        "",
        "## Guardrails",
        "",
        "- Review-only output.",
        "- Current snapshots are not captured for expired 15m windows.",
        "- No live trading.",
        "- No wallet promotion.",
        "- No wallet trust mutation.",
        "- No wallet-list mutation.",
    ]
    return "\n".join(lines) + "\n"


def default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def write_candidate_bounded_snapshot_capture(
    *,
    outcome_completion_path: Path | str = DEFAULT_OUTCOME_COMPLETION,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    market_provider: Callable[[str], dict[str, Any] | None] | None = None,
    execute: bool = False,
    max_market_context_calls: int = 10,
    run_id: str | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    run_id = run_id or default_run_id()
    report = build_candidate_bounded_snapshot_capture(
        outcome_completion=read_json(outcome_completion_path),
        market_provider=market_provider,
        execute=execute,
        max_market_context_calls=max_market_context_calls,
        run_id=run_id,
        generated_at=generated_at,
    )
    output = Path(output_dir)
    json_path = output / f"candidate_bounded_snapshot_capture_{run_id}.json"
    snapshots_path = output / f"candidate_bounded_snapshot_capture_snapshots_{run_id}.jsonl"
    snapshots_csv_path = output / f"candidate_bounded_snapshot_capture_snapshots_{run_id}.csv"
    deferred_csv_path = output / f"candidate_bounded_snapshot_capture_deferred_{run_id}.csv"
    md_path = output / f"candidate_bounded_snapshot_capture_{run_id}.md"
    report["input_paths"] = {"outcome_completion": str(outcome_completion_path)}
    report["output_paths"] = {
        "json": str(json_path),
        "captured_snapshots": str(snapshots_path),
        "captured_snapshots_csv": str(snapshots_csv_path),
        "deferred_csv": str(deferred_csv_path),
        "markdown": str(md_path),
    }
    write_json(json_path, report)
    write_json(output / "candidate_bounded_snapshot_capture.json", report)
    write_jsonl(snapshots_path, [row for row in report.get("captured_snapshots", []) if isinstance(row, dict)])
    write_csv(snapshots_csv_path, [row for row in report.get("captured_snapshots", []) if isinstance(row, dict)], SNAPSHOT_FIELDS)
    write_csv(deferred_csv_path, [row for row in report.get("deferred_queue", []) if isinstance(row, dict)], DEFERRED_FIELDS)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture bounded candidate current snapshots only for still-open outcome windows.")
    parser.add_argument("--outcome-completion", type=Path, default=DEFAULT_OUTCOME_COMPLETION)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-market-context-calls", type=int, default=10)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_candidate_bounded_snapshot_capture(
        outcome_completion_path=args.outcome_completion,
        output_dir=args.output_dir,
        execute=args.execute,
        max_market_context_calls=args.max_market_context_calls,
        run_id=args.run_id,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(json.dumps(report["output_paths"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
