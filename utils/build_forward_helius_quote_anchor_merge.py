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

from wallets.forward_helius_quote_anchor_merge import build_forward_helius_quote_anchor_merge  # noqa: E402


DEFAULT_RECORDS = ROOT / "data" / "reports" / "forward_testing" / "forward_outcome_records.jsonl"
DEFAULT_MARKET_CONTEXT = ROOT / "data" / "wallet_backfills" / "forward_market_context_snapshots.jsonl"
DEFAULT_QUOTE_PROBE = ROOT / "data" / "reports" / "forward_testing" / "helius_quote_probe" / "forward_helius_quote_probe.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "reports" / "forward_testing" / "helius_quote_anchor_merge"

CSV_FIELDS = [
    "event_id",
    "wallet",
    "token_mint",
    "transaction_signature",
    "signal_time",
    "execution_price_quote",
    "execution_price_source",
    "quote_mint",
    "quote_amount_delta",
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


def read_probe_rows(path: Path | str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    try:
        parsed = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, list):
        return [row for row in parsed if isinstance(row, dict)]
    if isinstance(parsed, dict) and isinstance(parsed.get("rows"), list):
        return [row for row in parsed["rows"] if isinstance(row, dict)]
    return []


def relative_path(path: Path | str) -> str:
    p = Path(path)
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


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


def matched_record_csv_row(row: dict[str, Any]) -> dict[str, Any]:
    entry = row.get("decision_context", {}).get("estimated_entry_context", {})
    entry = entry if isinstance(entry, dict) else {}
    return {
        "event_id": row.get("event_id"),
        "wallet": row.get("wallet"),
        "token_mint": row.get("token_mint"),
        "transaction_signature": row.get("transaction_signature"),
        "signal_time": row.get("signal_time"),
        "execution_price_quote": entry.get("execution_price_quote"),
        "execution_price_source": entry.get("execution_price_source"),
        "quote_mint": entry.get("quote_mint"),
        "quote_amount_delta": entry.get("quote_amount_delta"),
    }


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
        "# MemeTraderPro Helius Quote Anchor Merge",
        "",
        "Review-only merge of recovered Helius quote anchors into a temporary forward record set.",
        "",
        "## Summary",
        "",
        f"- Input records: {summary.get('input_records', 0)}",
        f"- Input quote probe rows: {summary.get('input_quote_probe_rows', 0)}",
        f"- Recoverable quote anchors: {summary.get('recoverable_quote_anchors', 0)}",
        f"- Records augmented with quote anchor: {summary.get('records_augmented_with_quote_anchor', 0)}",
        f"- Resolver resolved rows: {summary.get('resolver_resolved_rows', 0)}",
        f"- Resolver known 15m outcomes: {summary.get('resolver_known_15m_outcomes', 0)}",
        f"- Resolver blocked without later snapshot: {summary.get('resolver_blocked_no_later_snapshot_rows', 0)}",
        f"- Resolver blocked without quote anchor: {summary.get('resolver_blocked_no_quote_anchor_rows', 0)}",
        "",
        "## Safety",
        "",
        "- Review-only output.",
        "- Live execution remains locked.",
        "- Canonical resolver files are not overwritten.",
        "- Wallet trust and wallet lists are not mutated.",
        "- No wallet is promoted.",
        "- No trades are executed.",
    ]
    return "\n".join(lines) + "\n"


def write_forward_helius_quote_anchor_merge(
    *,
    records_path: Path | str = DEFAULT_RECORDS,
    quote_probe_path: Path | str = DEFAULT_QUOTE_PROBE,
    market_context_path: Path | str = DEFAULT_MARKET_CONTEXT,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    run_id: str | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    run_id = run_id or default_run_id()
    output_dir = Path(output_dir)
    report = build_forward_helius_quote_anchor_merge(
        records=read_jsonl(records_path),
        quote_probe_rows=read_probe_rows(quote_probe_path),
        market_snapshots=read_jsonl(market_context_path),
        run_id=run_id,
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "forward_outcome_records": relative_path(records_path),
        "helius_quote_probe": relative_path(quote_probe_path),
        "forward_market_context_snapshots": relative_path(market_context_path),
    }

    json_path = output_dir / f"forward_helius_quote_anchor_merge_{run_id}.json"
    csv_path = output_dir / f"forward_helius_quote_anchor_merge_{run_id}.csv"
    md_path = output_dir / f"forward_helius_quote_anchor_merge_{run_id}.md"
    resolved_path = output_dir / f"forward_helius_quote_anchor_merge_resolved_{run_id}.jsonl"
    rejected_path = output_dir / f"forward_helius_quote_anchor_merge_rejected_{run_id}.jsonl"
    report["output_paths"] = {
        "json": relative_path(json_path),
        "csv": relative_path(csv_path),
        "markdown": relative_path(md_path),
        "resolved_records": relative_path(resolved_path),
        "rejected_records": relative_path(rejected_path),
    }

    resolver_report = report.get("resolver_report") if isinstance(report.get("resolver_report"), dict) else {}
    resolved = resolver_report.get("resolved_records") if isinstance(resolver_report.get("resolved_records"), list) else []
    rejected = resolver_report.get("rejected_records") if isinstance(resolver_report.get("rejected_records"), list) else []
    matched = report.get("augmented_records") if isinstance(report.get("augmented_records"), list) else []
    report_for_json = {
        key: value
        for key, value in report.items()
        if key not in {"augmented_records", "resolver_report"}
    }
    report_for_json["resolver_summary"] = resolver_report.get("summary")

    write_json(json_path, report_for_json)
    write_json(output_dir / "forward_helius_quote_anchor_merge.json", report_for_json)
    write_csv(csv_path, [matched_record_csv_row(row) for row in matched])
    write_jsonl(resolved_path, resolved)
    write_jsonl(rejected_path, rejected)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review-only merge of Helius quote anchors into forward resolver.")
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    parser.add_argument("--quote-probe", type=Path, default=DEFAULT_QUOTE_PROBE)
    parser.add_argument("--market-context", type=Path, default=DEFAULT_MARKET_CONTEXT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-id", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_forward_helius_quote_anchor_merge(
        records_path=args.records,
        quote_probe_path=args.quote_probe,
        market_context_path=args.market_context,
        output_dir=args.output_dir,
        run_id=args.run_id,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(json.dumps(report["output_paths"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
