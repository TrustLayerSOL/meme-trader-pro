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
from wallets.dune_candidate_nonoverlap_slice import build_dune_candidate_nonoverlap_slice  # noqa: E402


DEFAULT_DUNE_ROWS = (
    ROOT
    / "data"
    / "reports"
    / "forward_testing"
    / "candidate_walk_forward"
    / "dune_candidate_feasibility_rows_20260526-dune-candidate-feasibility-live-v4.json"
)
DEFAULT_LOCAL_RECORDS = ROOT / "data" / "reports" / "forward_testing" / "forward_outcome_records.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "reports" / "forward_testing" / "candidate_walk_forward"
CSV_FIELDS = [
    "wallet_address",
    "token_mint",
    "dune_transaction_signature",
    "dune_block_time",
    "dune_block_timestamp",
    "amount_usd",
    "price_usd",
    "status",
    "block_reasons",
    "has_quote_anchor_candidate",
    "has_price_context_candidate",
    "has_liquidity_context",
    "has_market_cap_context",
    "has_forward_outcome",
    "proof_ready",
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
    parsed = json.loads(p.read_text(encoding="utf-8"))
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


def write_csv(path: Path | str, rows: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            next_row = {field: row.get(field, "") for field in CSV_FIELDS}
            if isinstance(next_row.get("block_reasons"), list):
                next_row["block_reasons"] = ",".join(next_row["block_reasons"])
            writer.writerow(next_row)


def write_jsonl(path: Path | str, rows: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def parse_wallets(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        "# Dune Candidate Non-Overlap Slice",
        "",
        "Review-only report for Dune DEX rows that do not overlap local forward evidence.",
        "",
        "## Summary",
        "",
        f"- Dune DEX rows: {summary.get('dune_dex_rows', 0)}",
        f"- Local overlap rows: {summary.get('local_overlap_rows', 0)}",
        f"- Non-overlap rows: {summary.get('nonoverlap_rows', 0)}",
        f"- Price-context candidate rows: {summary.get('price_context_candidate_rows', 0)}",
        f"- Liquidity-context rows: {summary.get('liquidity_context_rows', 0)}",
        f"- Market-cap context rows: {summary.get('market_cap_context_rows', 0)}",
        f"- Forward outcome rows: {summary.get('forward_outcome_rows', 0)}",
        f"- Proof-ready rows: {summary.get('proof_ready_rows', 0)}",
        f"- Promotions allowed: {summary.get('promotions_allowed', 0)}",
        "",
        "## Guardrails",
        "",
        "- Candidate wallets only.",
        "- No live trading.",
        "- No wallet promotion.",
        "- No wallet trust mutation.",
        "- No wallet-list mutation.",
        "- Non-overlap rows stay excluded from proof metrics until context and outcomes are complete.",
    ]
    return "\n".join(lines) + "\n"


def write_dune_candidate_nonoverlap_slice(
    *,
    dune_rows_path: Path | str = DEFAULT_DUNE_ROWS,
    local_records_path: Path | str = DEFAULT_LOCAL_RECORDS,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    run_id: str | None = None,
    candidate_wallets: list[str] | None = None,
    generated_at: float | None = None,
    max_time_delta_seconds: float = 300.0,
) -> dict[str, Any]:
    run_id = run_id or default_run_id()
    report = build_dune_candidate_nonoverlap_slice(
        dune_rows=read_json(dune_rows_path),
        local_records=read_jsonl(local_records_path),
        candidate_wallets=candidate_wallets or DEFAULT_CANDIDATE_WALLETS,
        generated_at=generated_at,
        max_time_delta_seconds=max_time_delta_seconds,
    )
    output = Path(output_dir)
    json_path = output / f"dune_candidate_nonoverlap_slice_{run_id}.json"
    csv_path = output / f"dune_candidate_nonoverlap_slice_{run_id}.csv"
    records_path = output / f"dune_candidate_nonoverlap_records_{run_id}.jsonl"
    md_path = output / f"dune_candidate_nonoverlap_slice_{run_id}.md"
    report["run_id"] = run_id
    report["input_paths"] = {
        "dune_rows": str(dune_rows_path),
        "local_records": str(local_records_path),
    }
    report["output_paths"] = {
        "json": str(json_path),
        "csv": str(csv_path),
        "records": str(records_path),
        "markdown": str(md_path),
    }
    write_json(json_path, report)
    write_json(output / "dune_candidate_nonoverlap_slice.json", report)
    write_csv(csv_path, [row for row in report.get("nonoverlap_records", []) if isinstance(row, dict)])
    write_jsonl(records_path, [row for row in report.get("nonoverlap_records", []) if isinstance(row, dict)])
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Dune candidate non-overlap slice report.")
    parser.add_argument("--dune-rows", type=Path, default=DEFAULT_DUNE_ROWS)
    parser.add_argument("--local-records", type=Path, default=DEFAULT_LOCAL_RECORDS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--candidate-wallets", default=None)
    parser.add_argument("--max-time-delta-seconds", type=float, default=300.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_dune_candidate_nonoverlap_slice(
        dune_rows_path=args.dune_rows,
        local_records_path=args.local_records,
        output_dir=args.output_dir,
        run_id=args.run_id,
        candidate_wallets=parse_wallets(args.candidate_wallets),
        max_time_delta_seconds=args.max_time_delta_seconds,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(json.dumps(report["output_paths"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
