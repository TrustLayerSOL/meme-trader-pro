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

from wallets.candidate_walk_forward_paper_readiness_gate import build_candidate_walk_forward_paper_readiness_gate  # noqa: E402


DEFAULT_SURVIVOR_REVIEW = (
    ROOT
    / "data"
    / "reports"
    / "forward_testing"
    / "candidate_walk_forward"
    / "candidate_walk_forward_survivor_review.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "data" / "reports" / "forward_testing" / "candidate_walk_forward"

WALLET_FIELDS = [
    "wallet_address",
    "walk_forward_conclusion",
    "paper_readiness_status",
    "candidate_records",
    "proof_metric_records",
    "excluded_records",
    "excluded_rate",
    "context_completion_rate",
    "validation_clean_records",
    "validation_runner_count",
    "validation_runner_rate",
    "validation_token_count",
    "failed_gates",
    "required_next_steps",
    "paper_simulation_enabled",
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


def csv_value(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True)
    return value


def write_csv(path: Path | str, rows: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=WALLET_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field, "")) for field in WALLET_FIELDS})


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    config = report.get("gate_config") if isinstance(report.get("gate_config"), dict) else {}
    lines = [
        "# Candidate Walk-Forward Paper Readiness Gate",
        "",
        "Advisory gate for deciding whether a candidate wallet deserves manual paper-simulation review. This report does not enable paper simulation or execution.",
        "",
        "## Summary",
        "",
        f"- Wallets evaluated: {summary.get('wallets_evaluated', 0)}",
        f"- Eligible for manual paper-simulation review: {summary.get('eligible_for_manual_paper_simulation_review', 0)}",
        f"- Not ready wallets: {summary.get('not_ready_wallets', 0)}",
        f"- Paper simulation enabled: {summary.get('paper_simulation_enabled', False)}",
        f"- Promotions allowed: {summary.get('promotions_allowed', 0)}",
        "",
        "## Gate Config",
        "",
        f"- Required walk-forward conclusion: `{config.get('required_walk_forward_conclusion')}`",
        f"- Minimum total clean rows: `{config.get('min_total_clean_rows')}`",
        f"- Minimum validation clean rows: `{config.get('min_validation_clean_rows')}`",
        f"- Minimum validation runners: `{config.get('min_validation_runner_count')}`",
        f"- Minimum validation token count: `{config.get('min_validation_token_count')}`",
        f"- Minimum context completion rate: `{config.get('min_context_completion_rate')}`",
        f"- Maximum excluded rate: `{config.get('max_excluded_rate')}`",
        "",
        "## Wallets",
        "",
        "| Wallet | Status | Proof Rows | Validation Rows | Validation Runners | Excluded Rate | Failed Gates |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in report.get("wallets") or []:
        if not isinstance(row, dict):
            continue
        failed = ", ".join(row.get("failed_gates") or [])
        lines.append(
            f"| `{row.get('wallet_address')}` | {row.get('paper_readiness_status')} | "
            f"{row.get('proof_metric_records')} | {row.get('validation_clean_records')} | "
            f"{row.get('validation_runner_count')} | {row.get('excluded_rate')} | {failed} |"
        )
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "- No live trading.",
            "- No paper simulation is enabled by this report.",
            "- No wallet trust mutation.",
            "- No wallet-list mutation.",
            "- No automatic promotion.",
            "- No profitability claim.",
        ]
    )
    return "\n".join(lines) + "\n"


def default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def write_candidate_walk_forward_paper_readiness_gate(
    *,
    survivor_review_path: Path | str = DEFAULT_SURVIVOR_REVIEW,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    run_id: str | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    run_id = run_id or default_run_id()
    report = build_candidate_walk_forward_paper_readiness_gate(
        survivor_review=read_json(survivor_review_path),
        generated_at=generated_at,
    )
    output = Path(output_dir)
    json_path = output / f"candidate_walk_forward_paper_readiness_gate_{run_id}.json"
    csv_path = output / f"candidate_walk_forward_paper_readiness_gate_{run_id}.csv"
    md_path = output / f"candidate_walk_forward_paper_readiness_gate_{run_id}.md"
    report["run_id"] = run_id
    report["input_paths"] = {"survivor_review": str(survivor_review_path)}
    report["output_paths"] = {
        "json": str(json_path),
        "csv": str(csv_path),
        "markdown": str(md_path),
    }
    write_json(json_path, report)
    write_json(output / "candidate_walk_forward_paper_readiness_gate.json", report)
    write_csv(csv_path, [row for row in report.get("wallets", []) if isinstance(row, dict)])
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build candidate walk-forward paper readiness gate report.")
    parser.add_argument("--survivor-review", type=Path, default=DEFAULT_SURVIVOR_REVIEW)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-id", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_candidate_walk_forward_paper_readiness_gate(
        survivor_review_path=args.survivor_review,
        output_dir=args.output_dir,
        run_id=args.run_id,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(json.dumps(report["output_paths"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
