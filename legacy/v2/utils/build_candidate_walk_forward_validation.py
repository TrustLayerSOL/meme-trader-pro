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

from wallets.candidate_walk_forward_validation import DEFAULT_CANDIDATE_WALLETS  # noqa: E402
from wallets.candidate_walk_forward_validation import build_candidate_walk_forward_validation_report  # noqa: E402


DEFAULT_RECORDS = ROOT / "data" / "reports" / "forward_testing" / "forward_outcome_records.jsonl"
DEFAULT_REPAIRED_RECORDS = ROOT / "data" / "reports" / "forward_testing" / "forward_entry_context_resolved_records.jsonl"
DEFAULT_DUNE_COMPLETED_RECORDS = (
    ROOT
    / "data"
    / "reports"
    / "forward_testing"
    / "candidate_walk_forward"
    / "dune_candidate_context_completed_records_20260526-dune-context-completion-live-v1.jsonl"
)
DEFAULT_OUTPUT_DIR = ROOT / "data" / "reports" / "forward_testing" / "candidate_walk_forward"

WALLET_FIELDS = [
    "wallet_address",
    "conclusion",
    "candidate_records",
    "proof_metric_records",
    "train_clean_records",
    "train_runner_rate",
    "validation_clean_records",
    "validation_runner_rate",
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


def wallet_csv_row(row: dict[str, Any]) -> dict[str, Any]:
    train = row.get("train") if isinstance(row.get("train"), dict) else {}
    validation = row.get("validation") if isinstance(row.get("validation"), dict) else {}
    return {
        "wallet_address": row.get("wallet_address"),
        "conclusion": row.get("conclusion"),
        "candidate_records": row.get("candidate_records"),
        "proof_metric_records": row.get("proof_metric_records"),
        "train_clean_records": train.get("clean_records"),
        "train_runner_rate": train.get("runner_rate"),
        "validation_clean_records": validation.get("clean_records"),
        "validation_runner_rate": validation.get("runner_rate"),
        "promotion_allowed": row.get("promotion_allowed"),
        "wallet_trust_mutation_allowed": row.get("wallet_trust_mutation_allowed"),
        "wallet_list_mutation_allowed": row.get("wallet_list_mutation_allowed"),
    }


def write_csv(path: Path | str, rows: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=WALLET_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in WALLET_FIELDS})


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        "# Candidate Walk-Forward Validation",
        "",
        "Candidate-wallet-only out-of-sample validation. This report is an evidence packet, not a trade signal.",
        "",
        "## Summary",
        "",
        f"- Candidate wallets: {summary.get('candidate_wallets', 0)}",
        f"- Candidate records: {summary.get('candidate_records', 0)}",
        f"- Clean proof records: {summary.get('clean_records', 0)}",
        f"- Excluded records: {summary.get('excluded_records', 0)}",
        f"- Dune completed input records: {summary.get('dune_completed_records', 0)}",
        f"- Dune clean proof records: {summary.get('dune_clean_records', 0)}",
        f"- Dune existing event matches: {summary.get('dune_existing_event_matches', 0)}",
        f"- Dune new event appends: {summary.get('dune_new_event_appends', 0)}",
        f"- Continued validation wallets: {summary.get('continued_validation_wallets', 0)}",
        f"- Degraded wallets: {summary.get('degraded_wallets', 0)}",
        f"- Inconclusive wallets: {summary.get('inconclusive_wallets', 0)}",
        f"- Rejected wallets: {summary.get('rejected_wallets', 0)}",
        f"- Promotions allowed: {summary.get('promotions_allowed', 0)}",
        "",
        "## Wallets",
        "",
        "| Wallet | Conclusion | Train Clean | Train Runner Rate | Validation Clean | Validation Runner Rate |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in report.get("wallets") or []:
        if not isinstance(row, dict):
            continue
        train = row.get("train") if isinstance(row.get("train"), dict) else {}
        validation = row.get("validation") if isinstance(row.get("validation"), dict) else {}
        lines.append(
            f"| `{row.get('wallet_address')}` | {row.get('conclusion')} | {train.get('clean_records')} | "
            f"{train.get('runner_rate')} | {validation.get('clean_records')} | {validation.get('runner_rate')} |"
        )
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "- No live trading.",
            "- No wallet trust mutation.",
            "- No wallet-list mutation.",
            "- No automatic promotion.",
            "- No broad wallet scanning.",
            "- No edge claim.",
        ]
    )
    return "\n".join(lines) + "\n"


def default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def write_candidate_walk_forward_validation_report(
    *,
    records_path: Path | str = DEFAULT_RECORDS,
    repaired_records_path: Path | str = DEFAULT_REPAIRED_RECORDS,
    dune_completed_records_path: Path | str | None = None,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    run_id: str | None = None,
    generated_at: float | None = None,
    candidate_wallets: list[str] | None = None,
    train_fraction: float = 0.7,
    min_train_clean_rows: int = 10,
    min_validation_clean_rows: int = 5,
    degradation_tolerance: float = 0.5,
) -> dict[str, Any]:
    run_id = run_id or default_run_id()
    report = build_candidate_walk_forward_validation_report(
        records=read_jsonl(records_path),
        repaired_records=read_jsonl(repaired_records_path),
        dune_completed_records=read_jsonl(dune_completed_records_path) if dune_completed_records_path else [],
        candidate_wallets=candidate_wallets or DEFAULT_CANDIDATE_WALLETS,
        generated_at=generated_at,
        train_fraction=train_fraction,
        min_train_clean_rows=min_train_clean_rows,
        min_validation_clean_rows=min_validation_clean_rows,
        degradation_tolerance=degradation_tolerance,
    )
    report["run_id"] = run_id
    report["input_paths"] = {
        "records": str(records_path),
        "repaired_records": str(repaired_records_path),
        "dune_completed_records": str(dune_completed_records_path) if dune_completed_records_path else None,
    }
    output = Path(output_dir)
    json_path = output / f"candidate_walk_forward_validation_{run_id}.json"
    csv_path = output / f"candidate_walk_forward_validation_{run_id}.csv"
    md_path = output / f"candidate_walk_forward_validation_{run_id}.md"
    report["output_paths"] = {
        "json": str(json_path),
        "csv": str(csv_path),
        "markdown": str(md_path),
    }
    write_json(json_path, report)
    write_json(output / "candidate_walk_forward_validation.json", report)
    write_csv(csv_path, [wallet_csv_row(row) for row in report.get("wallets", []) if isinstance(row, dict)])
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return report


def parse_wallets(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build candidate-only walk-forward validation evidence packet.")
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    parser.add_argument("--repaired-records", type=Path, default=DEFAULT_REPAIRED_RECORDS)
    parser.add_argument("--dune-completed-records", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--candidate-wallets", default=None, help="Comma-separated wallet addresses. Defaults to current candidate validation wallets.")
    parser.add_argument("--train-fraction", type=float, default=0.7)
    parser.add_argument("--min-train-clean-rows", type=int, default=10)
    parser.add_argument("--min-validation-clean-rows", type=int, default=5)
    parser.add_argument("--degradation-tolerance", type=float, default=0.5)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_candidate_walk_forward_validation_report(
        records_path=args.records,
        repaired_records_path=args.repaired_records,
        dune_completed_records_path=args.dune_completed_records,
        output_dir=args.output_dir,
        run_id=args.run_id,
        candidate_wallets=parse_wallets(args.candidate_wallets),
        train_fraction=args.train_fraction,
        min_train_clean_rows=args.min_train_clean_rows,
        min_validation_clean_rows=args.min_validation_clean_rows,
        degradation_tolerance=args.degradation_tolerance,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(json.dumps(report["output_paths"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
