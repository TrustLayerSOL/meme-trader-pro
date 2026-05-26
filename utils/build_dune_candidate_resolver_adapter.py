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

from wallets.dune_candidate_resolver_adapter import build_dune_candidate_resolver_adapter  # noqa: E402


DEFAULT_RECORDS = ROOT / "data" / "reports" / "forward_testing" / "forward_outcome_records.jsonl"
DEFAULT_DUNE_JOIN = (
    ROOT
    / "data"
    / "reports"
    / "forward_testing"
    / "candidate_walk_forward"
    / "dune_candidate_join.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "data" / "reports" / "forward_testing" / "candidate_walk_forward"
AUDIT_FIELDS = [
    "event_id",
    "wallet_address",
    "token_mint",
    "transaction_signature",
    "dune_transaction_signature",
    "quality",
    "price_usd",
    "amount_usd",
    "proof_ready",
    "block_reasons",
    "promotion_allowed",
    "wallet_trust_mutation_allowed",
    "wallet_list_mutation_allowed",
]


def default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


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
    lines = [
        "# Dune Candidate Resolver Adapter",
        "",
        "Review-only adapter that attaches Dune quote/price candidates to local candidate rows while keeping them blocked until liquidity and market cap are complete.",
        "",
        "## Summary",
        "",
        f"- Joined events scanned: {summary.get('joined_events_scanned', 0)}",
        f"- Context candidate records: {summary.get('context_candidate_records', 0)}",
        f"- Price candidate records: {summary.get('price_candidate_records', 0)}",
        f"- Quote-only candidate records: {summary.get('quote_only_candidate_records', 0)}",
        f"- Liquidity candidate records: {summary.get('liquidity_candidate_records', 0)}",
        f"- Market-cap candidate records: {summary.get('market_cap_candidate_records', 0)}",
        f"- Proof-ready records: {summary.get('proof_ready_records', 0)}",
        f"- Promotions allowed: {summary.get('promotions_allowed', 0)}",
        "",
        "## Guardrails",
        "",
        "- No live trading.",
        "- No wallet promotion.",
        "- No wallet trust mutation.",
        "- No wallet-list mutation.",
        "- Dune context candidates remain excluded from proof metrics until liquidity and market cap are complete.",
    ]
    return "\n".join(lines) + "\n"


def write_dune_candidate_resolver_adapter(
    *,
    records_path: Path | str = DEFAULT_RECORDS,
    dune_join_path: Path | str = DEFAULT_DUNE_JOIN,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    run_id: str | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    run_id = run_id or default_run_id()
    report = build_dune_candidate_resolver_adapter(
        records=read_jsonl(records_path),
        dune_join=read_json(dune_join_path),
        generated_at=generated_at,
    )
    output = Path(output_dir)
    json_path = output / f"dune_candidate_resolver_adapter_{run_id}.json"
    csv_path = output / f"dune_candidate_resolver_adapter_events_{run_id}.csv"
    records_path_out = output / f"dune_candidate_context_candidate_records_{run_id}.jsonl"
    md_path = output / f"dune_candidate_resolver_adapter_{run_id}.md"
    report["run_id"] = run_id
    report["input_paths"] = {"records": str(records_path), "dune_join": str(dune_join_path)}
    report["output_paths"] = {
        "json": str(json_path),
        "csv": str(csv_path),
        "context_candidate_records": str(records_path_out),
        "markdown": str(md_path),
    }
    report_for_json = {key: value for key, value in report.items() if key != "context_candidate_records"}
    write_json(json_path, report_for_json)
    write_json(output / "dune_candidate_resolver_adapter.json", report_for_json)
    write_jsonl(records_path_out, [row for row in report.get("context_candidate_records", []) if isinstance(row, dict)])
    write_csv(csv_path, [row for row in report.get("audit_rows", []) if isinstance(row, dict)])
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Dune candidate resolver adapter outputs.")
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    parser.add_argument("--dune-join", type=Path, default=DEFAULT_DUNE_JOIN)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-id", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_dune_candidate_resolver_adapter(
        records_path=args.records,
        dune_join_path=args.dune_join,
        output_dir=args.output_dir,
        run_id=args.run_id,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(json.dumps(report["output_paths"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
