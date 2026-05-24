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

from wallets.forward_market_snapshot_repair_queue import build_forward_market_snapshot_repair_queue  # noqa: E402


DEFAULT_REJECTED = ROOT / "data" / "reports" / "forward_testing" / "forward_entry_context_resolver_rejected.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "reports" / "forward_testing" / "market_snapshot_repair_queue"

FIELDS = [
    "token_mint",
    "blocked_row_count",
    "wallet_count",
    "required_snapshot_start_time",
    "required_snapshot_end_time",
    "earliest_signal_time",
    "latest_signal_time",
    "recommended_action",
    "repair_priority",
    "reason",
    "promotion_allowed",
    "can_mutate_wallet_trust",
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


def write_csv(path: Path | str, rows: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDS})


def relative_path(path: Path | str) -> str:
    p = Path(path)
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        "# Forward Market Snapshot Repair Queue",
        "",
        "Review-only queue of token/time windows that already have quote anchors but need later market snapshots.",
        "",
        "## Summary",
        "",
        f"- Input rejected records: {summary.get('input_rejected_records', 0)}",
        f"- Missing later market snapshot rows: {summary.get('missing_later_market_snapshot_rows', 0)}",
        f"- Queued token mints: {summary.get('queued_token_mints', 0)}",
        f"- Queued wallets: {summary.get('queued_wallets', 0)}",
        f"- Top token blocked rows: {summary.get('top_token_blocked_rows', 0)}",
        "",
        "## Top Queue",
        "",
        "| Token | Rows | Wallets | Start | End | Action |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in (report.get("queue") or [])[:25]:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"| `{row.get('token_mint')}` | {row.get('blocked_row_count')} | {row.get('wallet_count')} | "
            f"{row.get('required_snapshot_start_time')} | {row.get('required_snapshot_end_time')} | "
            f"{row.get('recommended_action')} |"
        )
    lines.extend(
        [
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
    )
    return "\n".join(lines) + "\n"


def write_forward_market_snapshot_repair_queue(
    *,
    rejected_records_path: Path | str = DEFAULT_REJECTED,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    run_id: str | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    run_id = run_id or default_run_id()
    output_dir = Path(output_dir)
    report = build_forward_market_snapshot_repair_queue(
        rejected_records=read_jsonl(rejected_records_path),
        run_id=run_id,
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "rejected_records": relative_path(rejected_records_path),
    }
    json_path = output_dir / f"forward_market_snapshot_repair_queue_{run_id}.json"
    csv_path = output_dir / f"forward_market_snapshot_repair_queue_{run_id}.csv"
    md_path = output_dir / f"forward_market_snapshot_repair_queue_{run_id}.md"
    report["output_paths"] = {
        "json": relative_path(json_path),
        "csv": relative_path(csv_path),
        "markdown": relative_path(md_path),
    }
    write_json(json_path, report)
    write_json(output_dir / "forward_market_snapshot_repair_queue.json", report)
    write_csv(csv_path, report.get("queue") if isinstance(report.get("queue"), list) else [])
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(report), encoding="utf-8")
    (output_dir / "forward_market_snapshot_repair_queue.md").write_text(render_markdown(report), encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the review-only forward market snapshot repair queue.")
    parser.add_argument("--rejected-records", type=Path, default=DEFAULT_REJECTED)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-id", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_forward_market_snapshot_repair_queue(
        rejected_records_path=args.rejected_records,
        output_dir=args.output_dir,
        run_id=args.run_id,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(json.dumps(report["output_paths"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
