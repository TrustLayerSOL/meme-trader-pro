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
from wallets.dune_candidate_join import build_dune_candidate_join_report  # noqa: E402


DEFAULT_RECORDS = ROOT / "data" / "reports" / "forward_testing" / "forward_outcome_records.jsonl"
DEFAULT_DUNE_ROWS = (
    ROOT / "data" / "reports" / "forward_testing" / "candidate_walk_forward" / "dune_candidate_feasibility_rows.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "data" / "reports" / "forward_testing" / "candidate_walk_forward"
EVENT_FIELDS = [
    "event_id",
    "wallet_address",
    "token_mint",
    "local_transaction_signature",
    "dune_transaction_signature",
    "local_signal_time",
    "dune_block_time",
    "time_delta_seconds",
    "match_type",
    "amount_usd",
    "price_usd",
    "has_quote_anchor_candidate",
    "has_price_context_candidate",
    "has_liquidity_context",
    "has_market_cap_context",
    "proof_ready",
    "evidence_quality",
    "missing_for_proof",
    "notes",
]


def default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def parse_wallets(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def read_json(path: Path | str) -> Any:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


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


def load_dune_dex_rows(path: Path | str) -> list[dict[str, Any]]:
    payload = read_json(path)
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        if isinstance(payload.get("candidate_dex_trades"), list):
            return [row for row in payload["candidate_dex_trades"] if isinstance(row, dict)]
        query_results = payload.get("query_results")
        if isinstance(query_results, dict) and isinstance(query_results.get("candidate_dex_trades"), list):
            return [row for row in query_results["candidate_dex_trades"] if isinstance(row, dict)]
    return []


def write_json(path: Path | str, payload: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def csv_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    normalized["missing_for_proof"] = ",".join(row.get("missing_for_proof") or [])
    return normalized


def write_csv(path: Path | str, rows: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EVENT_FIELDS)
        writer.writeheader()
        for row in rows:
            output = csv_row(row)
            writer.writerow({field: output.get(field, "") for field in EVENT_FIELDS})


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        "# Dune Candidate Join",
        "",
        "Candidate-only join of Dune DEX rows to local forward events. Joined rows are context candidates, not trust proof.",
        "",
        "## Summary",
        "",
        f"- Candidate events scanned: {summary.get('candidate_events_scanned', 0)}",
        f"- Dune DEX rows: {summary.get('dune_dex_rows', 0)}",
        f"- Matched events: {summary.get('matched_events', 0)}",
        f"- Exact signature matches: {summary.get('exact_signature_matches', 0)}",
        f"- Time-window matches: {summary.get('time_window_matches', 0)}",
        f"- Quote-anchor candidate events: {summary.get('quote_anchor_candidate_events', 0)}",
        f"- Price-context candidate events: {summary.get('price_context_candidate_events', 0)}",
        f"- Liquidity-context candidate events: {summary.get('liquidity_context_candidate_events', 0)}",
        f"- Market-cap context candidate events: {summary.get('market_cap_context_candidate_events', 0)}",
        f"- Proof-ready events: {summary.get('proof_ready_events', 0)}",
        f"- Promotions allowed: {summary.get('promotions_allowed', 0)}",
        "",
        "## Guardrails",
        "",
        "- No live trading.",
        "- No wallet promotion.",
        "- No wallet trust mutation.",
        "- No wallet-list mutation.",
        "- Dune rows stay out of proof metrics until liquidity and market cap are decision-time safe.",
    ]
    return "\n".join(lines) + "\n"


def write_dune_candidate_join(
    *,
    records_path: Path | str = DEFAULT_RECORDS,
    dune_rows_path: Path | str = DEFAULT_DUNE_ROWS,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    run_id: str | None = None,
    candidate_wallets: list[str] | None = None,
    max_time_delta_seconds: float = 300.0,
    generated_at: float | None = None,
) -> dict[str, Any]:
    run_id = run_id or default_run_id()
    report = build_dune_candidate_join_report(
        records=read_jsonl(records_path),
        dune_dex_rows=load_dune_dex_rows(dune_rows_path),
        candidate_wallets=candidate_wallets or DEFAULT_CANDIDATE_WALLETS,
        max_time_delta_seconds=max_time_delta_seconds,
        generated_at=generated_at,
    )
    output = Path(output_dir)
    json_path = output / f"dune_candidate_join_{run_id}.json"
    csv_path = output / f"dune_candidate_join_events_{run_id}.csv"
    md_path = output / f"dune_candidate_join_{run_id}.md"
    report["run_id"] = run_id
    report["input_paths"] = {"records": str(records_path), "dune_rows": str(dune_rows_path)}
    report["output_paths"] = {"json": str(json_path), "csv": str(csv_path), "markdown": str(md_path)}
    write_json(json_path, report)
    write_json(output / "dune_candidate_join.json", report)
    write_csv(csv_path, [row for row in report.get("joined_events", []) if isinstance(row, dict)])
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Join Dune candidate DEX rows to local candidate events.")
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    parser.add_argument("--dune-rows", type=Path, default=DEFAULT_DUNE_ROWS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--candidate-wallets", default=None)
    parser.add_argument("--max-time-delta-seconds", type=float, default=300.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_dune_candidate_join(
        records_path=args.records,
        dune_rows_path=args.dune_rows,
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
