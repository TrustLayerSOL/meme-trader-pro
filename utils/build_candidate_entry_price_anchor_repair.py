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

from wallets.candidate_entry_price_anchor_repair import build_candidate_entry_price_anchor_repair  # noqa: E402
from wallets.candidate_entry_price_anchor_repair import read_raw_glob  # noqa: E402


DEFAULT_CONTEXT_QUALITY_LIFT = (
    ROOT
    / "data"
    / "reports"
    / "forward_testing"
    / "candidate_walk_forward"
    / "candidate_context_quality_lift.json"
)
DEFAULT_RECORDS = ROOT / "data" / "reports" / "forward_testing" / "forward_outcome_records.jsonl"
DEFAULT_RAW_GLOB = str(ROOT / "data" / "wallet_backfills" / "raw_transactions" / "forward_wallet_activity_raw_*.jsonl")
DEFAULT_OUTPUT_DIR = ROOT / "data" / "reports" / "forward_testing" / "candidate_walk_forward"

AUDIT_FIELDS = [
    "event_id",
    "wallet_address",
    "token_address",
    "observed_action",
    "signal_time",
    "transaction_signature",
    "repair_status",
    "reason",
    "repaired_price",
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


def write_jsonl(path: Path | str, rows: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def write_csv(path: Path | str, rows: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=AUDIT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in AUDIT_FIELDS})


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    rejects = report.get("rejected_reason_counts") if isinstance(report.get("rejected_reason_counts"), dict) else {}
    lines = [
        "# Candidate Entry Price Anchor Repair",
        "",
        "Review-only repair packet for candidate missing-forward-entry-price rows. Anchor-enriched rows are separate artifacts, not applied trust changes.",
        "",
        "## Summary",
        "",
        f"- Target wallets: {summary.get('target_wallets', 0)}",
        f"- Missing entry price rows: {summary.get('missing_entry_price_rows', 0)}",
        f"- Anchor repaired rows: {summary.get('anchor_repaired_rows', 0)}",
        f"- Rejected rows: {summary.get('rejected_rows', 0)}",
        f"- Wallets with anchor repairs: {summary.get('wallets_with_anchor_repairs', 0)}",
        f"- Promotions allowed: {summary.get('promotions_allowed', 0)}",
        "",
        "## Wallets",
        "",
        "| Wallet | Missing Entry Price | Anchor Repaired | Rejected |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in report.get("wallet_summary") or []:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"| `{row.get('wallet_address')}` | {row.get('missing_entry_price_rows')} | "
            f"{row.get('anchor_repaired_rows')} | {row.get('rejected_rows')} |"
        )
    lines.extend(["", "## Rejected Reasons", ""])
    if rejects:
        for key, value in sorted(rejects.items()):
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "- Review-only output.",
            "- No live trading.",
            "- No paper simulation is enabled by this report.",
            "- No wallet promotion.",
            "- No wallet trust mutation.",
            "- No wallet-list mutation.",
        ]
    )
    return "\n".join(lines) + "\n"


def default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def write_candidate_entry_price_anchor_repair(
    *,
    context_quality_lift_path: Path | str = DEFAULT_CONTEXT_QUALITY_LIFT,
    records_path: Path | str = DEFAULT_RECORDS,
    raw_glob: str = DEFAULT_RAW_GLOB,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    run_id: str | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    run_id = run_id or default_run_id()
    report = build_candidate_entry_price_anchor_repair(
        context_quality_lift=read_json(context_quality_lift_path),
        records=read_jsonl(records_path),
        raw_rows=read_raw_glob(raw_glob),
        generated_at=generated_at,
    )
    output = Path(output_dir)
    json_path = output / f"candidate_entry_price_anchor_repair_{run_id}.json"
    csv_path = output / f"candidate_entry_price_anchor_repair_{run_id}.csv"
    repaired_path = output / f"candidate_entry_price_anchor_repaired_records_{run_id}.jsonl"
    rejected_path = output / f"candidate_entry_price_anchor_rejected_records_{run_id}.jsonl"
    md_path = output / f"candidate_entry_price_anchor_repair_{run_id}.md"
    report["run_id"] = run_id
    report["input_paths"] = {
        "context_quality_lift": str(context_quality_lift_path),
        "records": str(records_path),
        "raw_glob": raw_glob,
    }
    report["output_paths"] = {
        "json": str(json_path),
        "csv": str(csv_path),
        "anchor_repaired_records": str(repaired_path),
        "rejected_records": str(rejected_path),
        "markdown": str(md_path),
    }
    report_for_json = {key: value for key, value in report.items() if key not in {"anchor_repaired_records", "rejected_records"}}
    write_json(json_path, report_for_json)
    write_json(output / "candidate_entry_price_anchor_repair.json", report_for_json)
    write_csv(csv_path, [row for row in report.get("audit_rows", []) if isinstance(row, dict)])
    write_jsonl(repaired_path, [row for row in report.get("anchor_repaired_records", []) if isinstance(row, dict)])
    write_jsonl(rejected_path, [row for row in report.get("rejected_records", []) if isinstance(row, dict)])
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build candidate entry price anchor repair packet.")
    parser.add_argument("--context-quality-lift", type=Path, default=DEFAULT_CONTEXT_QUALITY_LIFT)
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    parser.add_argument("--raw-glob", default=DEFAULT_RAW_GLOB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-id", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_candidate_entry_price_anchor_repair(
        context_quality_lift_path=args.context_quality_lift,
        records_path=args.records,
        raw_glob=args.raw_glob,
        output_dir=args.output_dir,
        run_id=args.run_id,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(json.dumps(report["output_paths"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
