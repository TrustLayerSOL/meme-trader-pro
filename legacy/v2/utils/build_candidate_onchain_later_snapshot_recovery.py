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

from utils.backfill_historical_market_context import load_raw_transactions  # noqa: E402
from wallets.candidate_onchain_later_snapshot_recovery import build_candidate_onchain_later_snapshot_recovery  # noqa: E402


DEFAULT_DEFERRED_QUEUE = (
    ROOT
    / "data"
    / "reports"
    / "forward_testing"
    / "candidate_walk_forward"
    / "candidate_bounded_snapshot_capture_deferred_20260525-candidate-bounded-snapshot-capture.csv"
)
DEFAULT_ANCHOR_RECORDS = (
    ROOT
    / "data"
    / "reports"
    / "forward_testing"
    / "candidate_walk_forward"
    / "candidate_entry_price_anchor_resolved_records_20260525-candidate-entry-price-anchor-repair.jsonl"
)
DEFAULT_RAW_TRANSACTIONS_DIR = ROOT / "data" / "wallet_backfills" / "raw_transactions"
DEFAULT_QUOTE_PRICE_SERIES = ROOT / "data" / "reports" / "historical_backfill" / "sol_usd_price_series.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "reports" / "forward_testing" / "candidate_walk_forward"

BLOCKED_FIELDS = [
    "event_id",
    "wallet_address",
    "token_address",
    "signal_time",
    "block_reason",
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


def read_csv(path: Path | str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


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
        writer = csv.DictWriter(handle, fieldnames=BLOCKED_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in BLOCKED_FIELDS})


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        "# Candidate Onchain Later-Snapshot Recovery",
        "",
        "Review-only candidate recovery using preserved raw transactions after the signal timestamp.",
        "",
        "## Summary",
        "",
        f"- Deferred rows scanned: {summary.get('deferred_rows_scanned', 0)}",
        f"- Candidate records built: {summary.get('candidate_records_built', 0)}",
        f"- Known 15m outcomes added: {summary.get('known_15m_outcomes_added', 0)}",
        f"- Recovered forward records written: {summary.get('recovered_forward_records', 0)}",
        f"- Combined repaired records written: {summary.get('combined_repaired_records', 0)}",
        f"- Records with onchain snapshots: {summary.get('records_with_onchain_snapshots', 0)}",
        f"- Blocked missing anchor rows: {summary.get('blocked_missing_anchor_rows', 0)}",
        f"- Raw transactions scanned: {summary.get('raw_transactions_scanned', 0)}",
        f"- Wallet-list mutations: {summary.get('wallet_list_mutations', 0)}",
        f"- Wallet-trust mutations: {summary.get('wallet_trust_mutations', 0)}",
        "",
        "## Guardrails",
        "",
        "- Review-only output.",
        "- No live trading.",
        "- No paper simulation is enabled.",
        "- No wallet promotion.",
        "- No wallet trust mutation.",
        "- No wallet-list mutation.",
        "- Recovered labels are written only to a separate candidate review artifact.",
        "- No recovered outcome is copied into canonical decision-time context.",
    ]
    return "\n".join(lines) + "\n"


def default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def write_candidate_onchain_later_snapshot_recovery(
    *,
    deferred_queue_path: Path | str = DEFAULT_DEFERRED_QUEUE,
    anchor_records_path: Path | str = DEFAULT_ANCHOR_RECORDS,
    raw_transactions_dir: Path | str = DEFAULT_RAW_TRANSACTIONS_DIR,
    quote_price_series_path: Path | str = DEFAULT_QUOTE_PRICE_SERIES,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    run_id: str | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    run_id = run_id or default_run_id()
    report = build_candidate_onchain_later_snapshot_recovery(
        deferred_rows=read_csv(deferred_queue_path),
        anchor_records=read_jsonl(anchor_records_path),
        raw_transactions=load_raw_transactions(Path(raw_transactions_dir)),
        quote_price_series=read_jsonl(quote_price_series_path),
        generated_at=generated_at,
    )
    output = Path(output_dir)
    json_path = output / f"candidate_onchain_later_snapshot_recovery_{run_id}.json"
    records_path = output / f"candidate_onchain_later_snapshot_recovery_records_{run_id}.jsonl"
    candidate_records_path = output / f"candidate_onchain_later_snapshot_recovery_candidate_records_{run_id}.jsonl"
    recovered_forward_records_path = output / f"candidate_onchain_later_snapshot_recovered_forward_records_{run_id}.jsonl"
    combined_repaired_records_path = output / f"candidate_onchain_later_snapshot_combined_repaired_records_{run_id}.jsonl"
    blocked_csv_path = output / f"candidate_onchain_later_snapshot_recovery_blocked_{run_id}.csv"
    md_path = output / f"candidate_onchain_later_snapshot_recovery_{run_id}.md"
    report["run_id"] = run_id
    report["input_paths"] = {
        "deferred_queue": str(deferred_queue_path),
        "anchor_records": str(anchor_records_path),
        "raw_transactions_dir": str(raw_transactions_dir),
        "quote_price_series": str(quote_price_series_path),
    }
    report["output_paths"] = {
        "json": str(json_path),
        "records": str(records_path),
        "candidate_records": str(candidate_records_path),
        "recovered_forward_records": str(recovered_forward_records_path),
        "combined_repaired_records": str(combined_repaired_records_path),
        "blocked": str(blocked_csv_path),
        "markdown": str(md_path),
    }
    report_for_json = {
        key: value
        for key, value in report.items()
        if key not in {"records", "candidate_records", "recovered_forward_records", "combined_repaired_records"}
    }
    write_json(json_path, report_for_json)
    write_json(output / "candidate_onchain_later_snapshot_recovery.json", report_for_json)
    write_jsonl(records_path, [row for row in report.get("records", []) if isinstance(row, dict)])
    write_jsonl(candidate_records_path, [row for row in report.get("candidate_records", []) if isinstance(row, dict)])
    write_jsonl(
        recovered_forward_records_path,
        [row for row in report.get("recovered_forward_records", []) if isinstance(row, dict)],
    )
    write_jsonl(
        combined_repaired_records_path,
        [row for row in report.get("combined_repaired_records", []) if isinstance(row, dict)],
    )
    write_csv(blocked_csv_path, [row for row in report.get("blocked_rows", []) if isinstance(row, dict)])
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build candidate onchain later-snapshot recovery report.")
    parser.add_argument("--deferred-queue", type=Path, default=DEFAULT_DEFERRED_QUEUE)
    parser.add_argument("--anchor-records", type=Path, default=DEFAULT_ANCHOR_RECORDS)
    parser.add_argument("--raw-transactions-dir", type=Path, default=DEFAULT_RAW_TRANSACTIONS_DIR)
    parser.add_argument("--quote-price-series", type=Path, default=DEFAULT_QUOTE_PRICE_SERIES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-id", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_candidate_onchain_later_snapshot_recovery(
        deferred_queue_path=args.deferred_queue,
        anchor_records_path=args.anchor_records,
        raw_transactions_dir=args.raw_transactions_dir,
        quote_price_series_path=args.quote_price_series,
        output_dir=args.output_dir,
        run_id=args.run_id,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(json.dumps(report["output_paths"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
