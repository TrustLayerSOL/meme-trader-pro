#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.env_loader import load_env  # noqa: E402
from core.json_store import atomic_write_json  # noqa: E402
from utils.discover_candidate_wallets import SyncRpcClient  # noqa: E402
from wallets.missing_raw_transaction_recovery import build_missing_raw_transaction_recovery_report  # noqa: E402


DEFAULT_HISTORICAL_BACKFILL_REPORT = (
    ROOT / "data" / "reports" / "historical_backfill" / "historical_market_context_backfill_report.json"
)
DEFAULT_REPORT_PATH = ROOT / "data" / "reports" / "historical_backfill" / "missing_raw_transaction_recovery_report.json"
DEFAULT_RAW_DIR = ROOT / "data" / "wallet_backfills" / "raw_transactions"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        parsed = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default
    return parsed


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def write_missing_raw_transaction_recovery_report(
    *,
    historical_backfill_report_path: Path | str = DEFAULT_HISTORICAL_BACKFILL_REPORT,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    raw_dir: Path | str = DEFAULT_RAW_DIR,
    rpc: Any | None = None,
    execute: bool = False,
    generated_at: float | None = None,
    request_pause_seconds: float = 0.0,
    limit: int | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    source_path = Path(historical_backfill_report_path)
    report_path = Path(report_path)
    raw_dir = Path(raw_dir)
    source_report = read_json(source_path, {"records": []})
    report = build_missing_raw_transaction_recovery_report(
        historical_backfill_report=source_report,
        rpc=rpc,
        execute=execute,
        generated_at=generated_at,
        request_pause_seconds=request_pause_seconds,
        limit=limit,
    )
    raw_rows = report.pop("raw_transactions", [])
    if raw_rows:
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(generated_at))
        raw_path = raw_dir / f"missing_raw_transactions_{stamp}.jsonl"
        append_jsonl(raw_path, raw_rows)
        report["raw_transactions_path"] = relative_path(raw_path)
        report["raw_transactions_preserved"] = len(raw_rows)
    else:
        report["raw_transactions_path"] = None
        report["raw_transactions_preserved"] = 0
    report["input_paths"] = {"historical_backfill_report": relative_path(source_path)}
    report["output_paths"] = {"report": relative_path(report_path), "raw_transactions_dir": relative_path(raw_dir)}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(report_path, report)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recover missing raw transactions for historical context backfill.")
    parser.add_argument("--execute", action="store_true", help="Fetch read-only getTransaction records. Default is dry-run.")
    parser.add_argument("--historical-backfill-report", type=Path, default=DEFAULT_HISTORICAL_BACKFILL_REPORT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--request-pause-seconds", type=float, default=0.2)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--rpc-timeout", type=int, default=15)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    load_env()
    rpc = SyncRpcClient(timeout=args.rpc_timeout) if args.execute else None
    report = write_missing_raw_transaction_recovery_report(
        historical_backfill_report_path=args.historical_backfill_report,
        report_path=args.report_path,
        raw_dir=args.raw_dir,
        rpc=rpc,
        execute=args.execute,
        request_pause_seconds=args.request_pause_seconds if args.execute else 0.0,
        limit=args.limit,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
