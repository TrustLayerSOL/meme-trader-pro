#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wallets.forward_market_snapshot_capture import build_forward_market_snapshot_capture  # noqa: E402


DEFAULT_QUEUE = ROOT / "data" / "reports" / "forward_testing" / "market_snapshot_repair_queue" / "forward_market_snapshot_repair_queue.json"
DEFAULT_EXISTING_MARKET_CONTEXT = ROOT / "data" / "wallet_backfills" / "forward_market_context_snapshots.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "reports" / "forward_testing" / "market_snapshot_capture"

FIELDS = [
    "mint",
    "time",
    "source",
    "price",
    "liquidity",
    "market_cap",
    "risk_label",
    "repair_queue_capture",
]


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
        "# Forward Market Snapshot Capture",
        "",
        "Review-only bounded capture of current market snapshots for queued token mints.",
        "",
        "## Summary",
        "",
        f"- Input queue rows: {summary.get('input_queue_rows', 0)}",
        f"- Selected mints: {summary.get('selected_mints', 0)}",
        f"- Dry-run mints: {summary.get('dry_run_mints', 0)}",
        f"- Snapshots captured: {summary.get('snapshots_captured', 0)}",
        f"- Provider misses: {summary.get('provider_misses', 0)}",
        f"- Combined market snapshots: {summary.get('combined_market_snapshots', 0)}",
        "",
        "## Safety",
        "",
        "- Review-only output.",
        "- Live execution remains locked.",
        "- Canonical market context files are not overwritten.",
        "- Wallet trust and wallet lists are not mutated.",
        "- No wallet is promoted.",
        "- No trades are executed.",
    ]
    return "\n".join(lines) + "\n"


def write_forward_market_snapshot_capture(
    *,
    repair_queue_path: Path | str = DEFAULT_QUEUE,
    existing_market_context_path: Path | str = DEFAULT_EXISTING_MARKET_CONTEXT,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    market_provider: Callable[[str], dict[str, Any] | None] | None = None,
    execute: bool = False,
    max_mints: int = 10,
    max_market_context_calls: int = 10,
    run_id: str | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    run_id = run_id or default_run_id()
    output_dir = Path(output_dir)
    report = build_forward_market_snapshot_capture(
        repair_queue=read_json(repair_queue_path),
        existing_market_snapshots=read_jsonl(existing_market_context_path),
        market_provider=market_provider,
        execute=execute,
        max_mints=max_mints,
        max_market_context_calls=max_market_context_calls,
        run_id=run_id,
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "market_snapshot_repair_queue": relative_path(repair_queue_path),
        "existing_market_context": relative_path(existing_market_context_path),
    }
    json_path = output_dir / f"forward_market_snapshot_capture_{run_id}.json"
    csv_path = output_dir / f"forward_market_snapshot_capture_{run_id}.csv"
    md_path = output_dir / f"forward_market_snapshot_capture_{run_id}.md"
    snapshots_path = output_dir / f"forward_market_snapshot_capture_snapshots_{run_id}.jsonl"
    combined_path = output_dir / f"forward_market_snapshot_capture_combined_market_context_{run_id}.jsonl"
    report["output_paths"] = {
        "json": relative_path(json_path),
        "csv": relative_path(csv_path),
        "markdown": relative_path(md_path),
        "captured_snapshots": relative_path(snapshots_path),
        "combined_market_context": relative_path(combined_path),
    }
    captured = report.get("captured_snapshots") if isinstance(report.get("captured_snapshots"), list) else []
    combined = report.get("combined_market_snapshots") if isinstance(report.get("combined_market_snapshots"), list) else []
    report_for_json = {key: value for key, value in report.items() if key not in {"combined_market_snapshots"}}
    write_json(json_path, report_for_json)
    write_json(output_dir / "forward_market_snapshot_capture.json", report_for_json)
    write_csv(csv_path, captured)
    write_jsonl(snapshots_path, captured)
    write_jsonl(combined_path, combined)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(report), encoding="utf-8")
    (output_dir / "forward_market_snapshot_capture.md").write_text(render_markdown(report), encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture bounded review-only snapshots for market snapshot repair queue.")
    parser.add_argument("--repair-queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--existing-market-context", type=Path, default=DEFAULT_EXISTING_MARKET_CONTEXT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-mints", type=int, default=10)
    parser.add_argument("--max-market-context-calls", type=int, default=10)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_forward_market_snapshot_capture(
        repair_queue_path=args.repair_queue,
        existing_market_context_path=args.existing_market_context,
        output_dir=args.output_dir,
        execute=args.execute,
        max_mints=args.max_mints,
        max_market_context_calls=args.max_market_context_calls,
        run_id=args.run_id,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(json.dumps(report["output_paths"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
