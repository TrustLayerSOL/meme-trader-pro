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

from wallets.candidate_walk_forward_survivor_review import build_candidate_walk_forward_survivor_review  # noqa: E402


DEFAULT_RECORDS = ROOT / "data" / "reports" / "forward_testing" / "forward_outcome_records.jsonl"
DEFAULT_REPAIRED_RECORDS = ROOT / "data" / "reports" / "forward_testing" / "forward_entry_context_resolved_records.jsonl"
DEFAULT_WALK_FORWARD_REPORT = (
    ROOT
    / "data"
    / "reports"
    / "forward_testing"
    / "candidate_walk_forward"
    / "candidate_walk_forward_validation.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "data" / "reports" / "forward_testing" / "candidate_walk_forward"

WALLET_FIELDS = [
    "wallet_address",
    "walk_forward_conclusion",
    "paper_simulation_readiness",
    "candidate_records",
    "proof_metric_records",
    "excluded_records",
    "train_clean_records",
    "train_runner_count",
    "train_runner_rate",
    "validation_clean_records",
    "validation_runner_count",
    "validation_runner_rate",
    "operator_action",
    "promotion_allowed",
    "wallet_trust_mutation_allowed",
    "wallet_list_mutation_allowed",
]

EVENT_FIELDS = [
    "wallet_address",
    "token_address",
    "token_symbol",
    "action",
    "observed_at",
    "decision_time_snapshot_at",
    "market_context_available",
    "liquidity_at_entry",
    "market_cap_at_entry",
    "price_at_entry",
    "outcome_15m",
    "return_15m_pct",
    "runner_label",
    "flat_label",
    "loser_label",
    "blocked_reason",
    "repaired_context",
    "evidence_quality",
    "window",
    "event_id",
    "transaction_signature",
    "notes",
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


def write_csv(path: Path | str, rows: list[dict[str, Any]], fields: list[str]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def wallet_csv_row(row: dict[str, Any]) -> dict[str, Any]:
    train = row.get("train") if isinstance(row.get("train"), dict) else {}
    validation = row.get("validation") if isinstance(row.get("validation"), dict) else {}
    return {
        "wallet_address": row.get("wallet_address"),
        "walk_forward_conclusion": row.get("walk_forward_conclusion"),
        "paper_simulation_readiness": row.get("paper_simulation_readiness"),
        "candidate_records": row.get("candidate_records"),
        "proof_metric_records": row.get("proof_metric_records"),
        "excluded_records": row.get("excluded_records"),
        "train_clean_records": train.get("clean_records"),
        "train_runner_count": train.get("runner_count"),
        "train_runner_rate": train.get("runner_rate"),
        "validation_clean_records": validation.get("clean_records"),
        "validation_runner_count": validation.get("runner_count"),
        "validation_runner_rate": validation.get("runner_rate"),
        "operator_action": row.get("operator_action"),
        "promotion_allowed": row.get("promotion_allowed"),
        "wallet_trust_mutation_allowed": row.get("wallet_trust_mutation_allowed"),
        "wallet_list_mutation_allowed": row.get("wallet_list_mutation_allowed"),
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        "# Candidate Walk-Forward Survivor Review",
        "",
        "Row-level interpretation for wallets that survived candidate-only walk-forward validation. This is an evidence packet, not a trade signal.",
        "",
        "## Summary",
        "",
        f"- Survivor wallets: {summary.get('survivor_wallets', 0)}",
        f"- Proof metric records: {summary.get('proof_metric_records', 0)}",
        f"- Excluded records: {summary.get('excluded_records', 0)}",
        f"- Train event rows: {summary.get('train_event_rows', 0)}",
        f"- Validation event rows: {summary.get('validation_event_rows', 0)}",
        f"- Promotions allowed: {summary.get('promotions_allowed', 0)}",
        "",
        "## Wallets",
        "",
        "| Wallet | Conclusion | Readiness | Proof Rows | Validation Runners | Validation Runner Rate |",
        "| --- | --- | --- | ---: | ---: | ---: |",
    ]
    for row in report.get("wallets") or []:
        if not isinstance(row, dict):
            continue
        validation = row.get("validation") if isinstance(row.get("validation"), dict) else {}
        lines.append(
            f"| `{row.get('wallet_address')}` | {row.get('walk_forward_conclusion')} | "
            f"{row.get('paper_simulation_readiness')} | {row.get('proof_metric_records')} | "
            f"{validation.get('runner_count')} | {validation.get('runner_rate')} |"
        )
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "- No live trading.",
            "- No paper trading is enabled by this report.",
            "- No wallet trust mutation.",
            "- No wallet-list mutation.",
            "- No automatic promotion.",
            "- No profitability claim.",
        ]
    )
    return "\n".join(lines) + "\n"


def default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def write_candidate_walk_forward_survivor_review(
    *,
    walk_forward_report_path: Path | str = DEFAULT_WALK_FORWARD_REPORT,
    records_path: Path | str = DEFAULT_RECORDS,
    repaired_records_path: Path | str = DEFAULT_REPAIRED_RECORDS,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    run_id: str | None = None,
    generated_at: float | None = None,
    include_conclusions: list[str] | None = None,
) -> dict[str, Any]:
    run_id = run_id or default_run_id()
    report = build_candidate_walk_forward_survivor_review(
        walk_forward_report=read_json(walk_forward_report_path),
        records=read_jsonl(records_path),
        repaired_records=read_jsonl(repaired_records_path),
        generated_at=generated_at,
        include_conclusions=include_conclusions,
    )
    output = Path(output_dir)
    json_path = output / f"candidate_walk_forward_survivor_review_{run_id}.json"
    csv_path = output / f"candidate_walk_forward_survivor_review_{run_id}.csv"
    events_csv_path = output / f"candidate_walk_forward_survivor_events_{run_id}.csv"
    md_path = output / f"candidate_walk_forward_survivor_review_{run_id}.md"
    report["run_id"] = run_id
    report["input_paths"] = {
        "walk_forward_report": str(walk_forward_report_path),
        "records": str(records_path),
        "repaired_records": str(repaired_records_path),
    }
    report["output_paths"] = {
        "json": str(json_path),
        "csv": str(csv_path),
        "events_csv": str(events_csv_path),
        "markdown": str(md_path),
    }
    write_json(json_path, report)
    write_json(output / "candidate_walk_forward_survivor_review.json", report)
    write_csv(csv_path, [wallet_csv_row(row) for row in report.get("wallets", []) if isinstance(row, dict)], WALLET_FIELDS)
    write_csv(events_csv_path, [row for row in report.get("event_evidence", []) if isinstance(row, dict)], EVENT_FIELDS)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return report


def parse_conclusions(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build candidate walk-forward survivor row-level review.")
    parser.add_argument("--walk-forward-report", type=Path, default=DEFAULT_WALK_FORWARD_REPORT)
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    parser.add_argument("--repaired-records", type=Path, default=DEFAULT_REPAIRED_RECORDS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--include-conclusions", default=None, help="Comma-separated allowed conclusions. Defaults to continued_validation only.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_candidate_walk_forward_survivor_review(
        walk_forward_report_path=args.walk_forward_report,
        records_path=args.records,
        repaired_records_path=args.repaired_records,
        output_dir=args.output_dir,
        run_id=args.run_id,
        include_conclusions=parse_conclusions(args.include_conclusions),
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(json.dumps(report["output_paths"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
