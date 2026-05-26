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

from wallets.dune_candidate_context_drift import build_dune_candidate_context_drift  # noqa: E402


DEFAULT_DUNE_COMPLETED = (
    ROOT
    / "data"
    / "reports"
    / "forward_testing"
    / "candidate_walk_forward"
    / "dune_candidate_context_completed_records_20260526-dune-context-completion-live-v1.jsonl"
)
DEFAULT_LOCAL_RECORDS = ROOT / "data" / "reports" / "forward_testing" / "forward_outcome_records.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "reports" / "forward_testing" / "candidate_walk_forward"
CSV_FIELDS = [
    "event_id",
    "wallet_address",
    "token_mint",
    "transaction_signature",
    "drift_status",
    "local_match",
    "dune_price",
    "local_price",
    "price_delta_pct",
    "dune_liquidity",
    "local_liquidity",
    "liquidity_delta_pct",
    "dune_market_cap",
    "local_market_cap",
    "market_cap_delta_pct",
    "dune_outcome_15m",
    "local_outcome_15m",
    "liquidity_match",
    "market_cap_match",
    "outcome_15m_match",
    "promotion_allowed",
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


def write_csv(path: Path | str, rows: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        "# Dune Candidate Context Drift",
        "",
        "Review-only comparison of Dune context-confirmed rows against local forward records.",
        "",
        "## Summary",
        "",
        f"- Dune records scanned: {summary.get('dune_records_scanned', 0)}",
        f"- Local matches: {summary.get('local_matches', 0)}",
        f"- Missing local matches: {summary.get('missing_local_match_records', 0)}",
        f"- No material drift: {summary.get('no_material_drift_records', 0)}",
        f"- Material price drift: {summary.get('material_price_drift_records', 0)}",
        f"- Liquidity drift: {summary.get('liquidity_drift_records', 0)}",
        f"- Market-cap drift: {summary.get('market_cap_drift_records', 0)}",
        f"- Outcome drift: {summary.get('outcome_drift_records', 0)}",
        f"- Max absolute price delta pct: {summary.get('max_abs_price_delta_pct')}",
        f"- Promotions allowed: {summary.get('promotions_allowed', 0)}",
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


def write_dune_candidate_context_drift(
    *,
    dune_completed_records_path: Path | str = DEFAULT_DUNE_COMPLETED,
    local_records_path: Path | str = DEFAULT_LOCAL_RECORDS,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    run_id: str | None = None,
    generated_at: float | None = None,
    max_price_delta_pct: float = 25.0,
) -> dict[str, Any]:
    run_id = run_id or default_run_id()
    report = build_dune_candidate_context_drift(
        dune_completed_records=read_jsonl(dune_completed_records_path),
        local_records=read_jsonl(local_records_path),
        generated_at=generated_at,
        max_price_delta_pct=max_price_delta_pct,
    )
    output = Path(output_dir)
    json_path = output / f"dune_candidate_context_drift_{run_id}.json"
    csv_path = output / f"dune_candidate_context_drift_{run_id}.csv"
    md_path = output / f"dune_candidate_context_drift_{run_id}.md"
    report["run_id"] = run_id
    report["input_paths"] = {
        "dune_completed_records": str(dune_completed_records_path),
        "local_records": str(local_records_path),
    }
    report["output_paths"] = {
        "json": str(json_path),
        "csv": str(csv_path),
        "markdown": str(md_path),
    }
    write_json(json_path, report)
    write_json(output / "dune_candidate_context_drift.json", report)
    write_csv(csv_path, [row for row in report.get("drift_records", []) if isinstance(row, dict)])
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Dune candidate context drift report.")
    parser.add_argument("--dune-completed-records", type=Path, default=DEFAULT_DUNE_COMPLETED)
    parser.add_argument("--local-records", type=Path, default=DEFAULT_LOCAL_RECORDS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--max-price-delta-pct", type=float, default=25.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_dune_candidate_context_drift(
        dune_completed_records_path=args.dune_completed_records,
        local_records_path=args.local_records,
        output_dir=args.output_dir,
        run_id=args.run_id,
        max_price_delta_pct=args.max_price_delta_pct,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(json.dumps(report["output_paths"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
