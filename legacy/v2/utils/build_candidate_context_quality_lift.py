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

from wallets.candidate_context_quality_lift import build_candidate_context_quality_lift  # noqa: E402


DEFAULT_READINESS_GATE = (
    ROOT
    / "data"
    / "reports"
    / "forward_testing"
    / "candidate_walk_forward"
    / "candidate_walk_forward_paper_readiness_gate.json"
)
DEFAULT_RECORDS = ROOT / "data" / "reports" / "forward_testing" / "forward_outcome_records.jsonl"
DEFAULT_REPAIRED_RECORDS = ROOT / "data" / "reports" / "forward_testing" / "forward_entry_context_resolved_records.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "reports" / "forward_testing" / "candidate_walk_forward"

WALLET_FIELDS = [
    "wallet_address",
    "paper_readiness_status",
    "failed_readiness_gates",
    "candidate_records",
    "clean_proof_rows",
    "open_blocker_rows",
    "context_completion_rate",
    "excluded_rate",
    "unique_blocked_tokens",
    "missing_later_market_snapshot_rows",
    "missing_valid_execution_price_quote_rows",
    "missing_outcome_label_rows",
    "blocker_reason_counts",
    "recommended_context_action",
    "priority_rank",
    "next_operator_step",
    "promotion_allowed",
    "wallet_trust_mutation_allowed",
    "wallet_list_mutation_allowed",
]

EVENT_FIELDS = [
    "event_id",
    "wallet_address",
    "token_address",
    "token_symbol",
    "observed_at",
    "action",
    "blocker_reason",
    "has_quote_anchor",
    "has_valid_entry_context",
    "outcome_15m",
    "liquidity_at_entry",
    "market_cap_at_entry",
    "price_at_entry",
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


def csv_value(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True)
    return value


def write_csv(path: Path | str, rows: list[dict[str, Any]], fields: list[str]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field, "")) for field in fields})


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        "# Candidate Context Quality Lift",
        "",
        "Targeted blocker-reduction queue for walk-forward survivor wallets that failed readiness because of context or excluded-row quality.",
        "",
        "## Summary",
        "",
        f"- Wallets in queue: {summary.get('wallets_in_queue', 0)}",
        f"- Open blocker rows: {summary.get('open_blocker_rows', 0)}",
        f"- Clean proof rows: {summary.get('clean_proof_rows', 0)}",
        f"- Unique blocked tokens: {summary.get('unique_blocked_tokens', 0)}",
        f"- Repair market snapshot wallets: {summary.get('repair_market_snapshot_wallets', 0)}",
        f"- Repair entry timestamp wallets: {summary.get('repair_entry_timestamp_wallets', 0)}",
        f"- Promotions allowed: {summary.get('promotions_allowed', 0)}",
        "",
        "## Queue",
        "",
        "| Wallet | Action | Open Blockers | Clean Rows | Context Completion | Excluded Rate | Next Step |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in report.get("wallets") or []:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"| `{row.get('wallet_address')}` | {row.get('recommended_context_action')} | "
            f"{row.get('open_blocker_rows')} | {row.get('clean_proof_rows')} | "
            f"{row.get('context_completion_rate')} | {row.get('excluded_rate')} | {row.get('next_operator_step')} |"
        )
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "- Review-only output.",
            "- No live trading.",
            "- No wallet promotion.",
            "- No wallet trust mutation.",
            "- No wallet-list mutation.",
            "- No paper simulation is enabled by this report.",
        ]
    )
    return "\n".join(lines) + "\n"


def default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def write_candidate_context_quality_lift(
    *,
    readiness_gate_path: Path | str = DEFAULT_READINESS_GATE,
    records_path: Path | str = DEFAULT_RECORDS,
    repaired_records_path: Path | str = DEFAULT_REPAIRED_RECORDS,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    run_id: str | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    run_id = run_id or default_run_id()
    report = build_candidate_context_quality_lift(
        readiness_gate=read_json(readiness_gate_path),
        records=read_jsonl(records_path),
        repaired_records=read_jsonl(repaired_records_path),
        generated_at=generated_at,
    )
    output = Path(output_dir)
    json_path = output / f"candidate_context_quality_lift_{run_id}.json"
    csv_path = output / f"candidate_context_quality_lift_{run_id}.csv"
    events_csv_path = output / f"candidate_context_quality_lift_blocker_events_{run_id}.csv"
    md_path = output / f"candidate_context_quality_lift_{run_id}.md"
    report["run_id"] = run_id
    report["input_paths"] = {
        "readiness_gate": str(readiness_gate_path),
        "records": str(records_path),
        "repaired_records": str(repaired_records_path),
    }
    report["output_paths"] = {
        "json": str(json_path),
        "csv": str(csv_path),
        "blocker_events_csv": str(events_csv_path),
        "markdown": str(md_path),
    }
    write_json(json_path, report)
    write_json(output / "candidate_context_quality_lift.json", report)
    write_csv(csv_path, [row for row in report.get("wallets", []) if isinstance(row, dict)], WALLET_FIELDS)
    write_csv(events_csv_path, [row for row in report.get("blocker_events", []) if isinstance(row, dict)], EVENT_FIELDS)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build targeted candidate context quality lift queue.")
    parser.add_argument("--readiness-gate", type=Path, default=DEFAULT_READINESS_GATE)
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    parser.add_argument("--repaired-records", type=Path, default=DEFAULT_REPAIRED_RECORDS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-id", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_candidate_context_quality_lift(
        readiness_gate_path=args.readiness_gate,
        records_path=args.records,
        repaired_records_path=args.repaired_records,
        output_dir=args.output_dir,
        run_id=args.run_id,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(json.dumps(report["output_paths"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
