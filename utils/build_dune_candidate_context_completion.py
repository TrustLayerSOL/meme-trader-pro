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

from wallets.dune_candidate_context_completion import build_dune_candidate_context_completion  # noqa: E402


DEFAULT_CANDIDATES = (
    ROOT
    / "data"
    / "reports"
    / "forward_testing"
    / "candidate_walk_forward"
    / "dune_candidate_context_candidate_records_20260526-dune-resolver-adapter-live-v4.jsonl"
)
DEFAULT_MARKET_SNAPSHOTS = ROOT / "data" / "wallet_backfills" / "forward_market_context_snapshots.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "reports" / "forward_testing" / "candidate_walk_forward"
AUDIT_FIELDS = [
    "event_id",
    "wallet_address",
    "token_mint",
    "transaction_signature",
    "status",
    "price_usd",
    "liquidity",
    "market_cap",
    "market_snapshot_lag_seconds",
    "proof_ready_candidate",
    "block_reasons",
    "wallet_trust_mutation_allowed",
    "wallet_list_mutation_allowed",
]


def default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


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
    lines = [
        "# Dune Candidate Context Completion",
        "",
        "Review-only completion report for Dune-matched candidate rows with near-event forward market snapshots.",
        "",
        "## Summary",
        "",
        f"- Candidate records scanned: {summary.get('candidate_records_scanned', 0)}",
        f"- Context-complete records: {summary.get('context_complete_records', 0)}",
        f"- Proof-ready candidate records: {summary.get('proof_ready_candidate_records', 0)}",
        f"- Blocked records: {summary.get('blocked_records', 0)}",
        f"- Blocked missing price: {summary.get('blocked_missing_price_records', 0)}",
        f"- Blocked missing liquidity: {summary.get('blocked_missing_liquidity_records', 0)}",
        f"- Blocked missing market cap: {summary.get('blocked_missing_market_cap_records', 0)}",
        f"- Wallet trust mutations: {summary.get('wallet_trust_mutations', 0)}",
        f"- Wallet-list mutations: {summary.get('wallet_list_mutations', 0)}",
        "",
        "## Guardrails",
        "",
        "- Candidate-wallet validation only.",
        "- No live trading.",
        "- No wallet promotion.",
        "- No wallet trust mutation.",
        "- No wallet-list mutation.",
    ]
    return "\n".join(lines) + "\n"


def write_dune_candidate_context_completion(
    *,
    candidate_records_path: Path | str = DEFAULT_CANDIDATES,
    market_snapshots_path: Path | str = DEFAULT_MARKET_SNAPSHOTS,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    run_id: str | None = None,
    generated_at: float | None = None,
    max_snapshot_lag_seconds: float = 120.0,
) -> dict[str, Any]:
    run_id = run_id or default_run_id()
    report = build_dune_candidate_context_completion(
        candidate_records=read_jsonl(candidate_records_path),
        market_snapshots=read_jsonl(market_snapshots_path),
        generated_at=generated_at,
        max_snapshot_lag_seconds=max_snapshot_lag_seconds,
    )
    output = Path(output_dir)
    json_path = output / f"dune_candidate_context_completion_{run_id}.json"
    csv_path = output / f"dune_candidate_context_completion_events_{run_id}.csv"
    completed_path = output / f"dune_candidate_context_completed_records_{run_id}.jsonl"
    blocked_path = output / f"dune_candidate_context_blocked_records_{run_id}.jsonl"
    md_path = output / f"dune_candidate_context_completion_{run_id}.md"
    report["run_id"] = run_id
    report["input_paths"] = {
        "candidate_records": str(candidate_records_path),
        "market_snapshots": str(market_snapshots_path),
    }
    report["output_paths"] = {
        "json": str(json_path),
        "csv": str(csv_path),
        "completed_records": str(completed_path),
        "blocked_records": str(blocked_path),
        "markdown": str(md_path),
    }
    report_for_json = {key: value for key, value in report.items() if key not in {"completed_records", "blocked_records"}}
    write_json(json_path, report_for_json)
    write_json(output / "dune_candidate_context_completion.json", report_for_json)
    write_jsonl(completed_path, [row for row in report.get("completed_records", []) if isinstance(row, dict)])
    write_jsonl(blocked_path, [row for row in report.get("blocked_records", []) if isinstance(row, dict)])
    write_csv(csv_path, [row for row in report.get("audit_rows", []) if isinstance(row, dict)])
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Dune candidate context-completion outputs.")
    parser.add_argument("--candidate-records", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--market-snapshots", type=Path, default=DEFAULT_MARKET_SNAPSHOTS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--max-snapshot-lag-seconds", type=float, default=120.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_dune_candidate_context_completion(
        candidate_records_path=args.candidate_records,
        market_snapshots_path=args.market_snapshots,
        output_dir=args.output_dir,
        run_id=args.run_id,
        max_snapshot_lag_seconds=args.max_snapshot_lag_seconds,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(json.dumps(report["output_paths"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
