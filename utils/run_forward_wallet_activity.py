#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.env_loader import load_env
from core.json_store import atomic_write_json, read_json
from core.runtime_status import update_component
from utils.discover_candidate_wallets import SyncRpcClient
from utils.run_wallet_history_backfill import merge_wallet_evidence_rows
from wallets.forward_wallet_activity import build_forward_wallet_activity_report


DEFAULT_TRACKED = ROOT / "data" / "tracked_wallets.json"
DEFAULT_PAPER_WATCH = ROOT / "data" / "paper_watch_wallets.json"
DEFAULT_REPORT = ROOT / "data" / "wallet_backfills" / "forward_wallet_activity_report.json"
DEFAULT_EVIDENCE = ROOT / "data" / "wallet_evidence" / "wallet_history_evidence.jsonl"
DEFAULT_REPORT_DIR = ROOT / "data" / "reports" / "wallet_backfills"
DEFAULT_RAW_DIR = ROOT / "data" / "wallet_backfills" / "raw_transactions"
COMPONENT = "forward_wallet_activity"


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def write_jsonl(path: Path | str, rows: list[dict[str, Any]]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def write_forward_wallet_activity_report(
    *,
    out_path: Path | str = DEFAULT_REPORT,
    evidence_path: Path | str = DEFAULT_EVIDENCE,
    report_dir: Path | str = DEFAULT_REPORT_DIR,
    raw_dir: Path | str = DEFAULT_RAW_DIR,
    tracked_wallets: Any | None = None,
    paper_watch_wallets: Any | None = None,
    rpc: Any | None = None,
    generated_at: float | None = None,
    lookback_seconds: int = 86400,
    execute: bool = False,
    max_wallets: int = 100,
    signature_limit: int = 40,
    max_transactions_per_wallet: int = 20,
    request_pause_seconds: float = 0.0,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    report = build_forward_wallet_activity_report(
        tracked_wallets=tracked_wallets if tracked_wallets is not None else read_json(DEFAULT_TRACKED, []),
        paper_watch_wallets=paper_watch_wallets if paper_watch_wallets is not None else read_json(DEFAULT_PAPER_WATCH, {"wallets": []}),
        rpc=rpc,
        generated_at=generated_at,
        lookback_seconds=lookback_seconds,
        execute=execute,
        max_wallets=max_wallets,
        signature_limit=signature_limit,
        max_transactions_per_wallet=max_transactions_per_wallet,
        request_pause_seconds=request_pause_seconds,
    )
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(generated_at))
    raw_rows = report.pop("raw_transactions", [])
    if raw_rows:
        raw_path = Path(raw_dir) / f"forward_wallet_activity_raw_{stamp}.jsonl"
        write_jsonl(raw_path, raw_rows)
        report["raw_transactions_path"] = display_path(raw_path)
        report["raw_transactions_preserved"] = len(raw_rows)
    else:
        report["raw_transactions_path"] = None
        report["raw_transactions_preserved"] = 0

    report_snapshot = Path(report_dir) / f"forward_wallet_activity_{stamp}.json"
    evidence_rows = report.get("evidence_records") if isinstance(report.get("evidence_records"), list) else []
    report.update(
        merge_wallet_evidence_rows(
            evidence_path=evidence_path,
            new_rows=evidence_rows,
            report_dir=report_dir,
            stamp=stamp,
        )
    )
    atomic_write_json(out_path, report)
    atomic_write_json(report_snapshot, report)
    return report


def run_forward_wallet_activity_cycle(
    *,
    write_report=write_forward_wallet_activity_report,
    update_status=update_component,
    rpc: Any | None = None,
    execute: bool = False,
    max_wallets: int = 100,
    lookback_seconds: int = 86400,
    signature_limit: int = 40,
    max_transactions_per_wallet: int = 20,
    request_pause_seconds: float = 0.0,
    interval_seconds: int | None = None,
) -> dict[str, Any]:
    update_status(
        COMPONENT,
        status="cycle_running",
        live_execution_locked=True,
        wallet_list_mutated=False,
        execute=bool(execute),
        heartbeat_interval=interval_seconds,
    )
    report = write_report(
        rpc=rpc,
        execute=execute,
        max_wallets=max_wallets,
        lookback_seconds=lookback_seconds,
        signature_limit=signature_limit,
        max_transactions_per_wallet=max_transactions_per_wallet,
        request_pause_seconds=request_pause_seconds,
    )
    summary = report.get("summary") if isinstance(report, dict) else {}
    update_status(
        COMPONENT,
        status="cycle_ok",
        last_error=None,
        live_execution_locked=True,
        wallet_list_mutated=False,
        execute=bool(execute),
        wallets_processed=int(summary.get("wallets_processed", 0) or 0),
        wallets_collected=int(summary.get("wallets_collected", 0) or 0),
        evidence_rows_created=int(summary.get("evidence_rows_created", 0) or 0),
        wallets_blocked_rpc_error=int(summary.get("wallets_blocked_rpc_error", 0) or 0),
        heartbeat_interval=interval_seconds,
    )
    return report


async def forward_wallet_activity_loop(interval_seconds: int = 900, config: dict[str, Any] | None = None) -> None:
    config = dict(config or {})
    config.setdefault("interval_seconds", interval_seconds)
    while True:
        try:
            load_env()
            rpc = SyncRpcClient() if config.get("execute") else None
            await asyncio.to_thread(
                run_forward_wallet_activity_cycle,
                rpc=rpc,
                execute=bool(config.get("execute")),
                max_wallets=int(config.get("max_wallets", 100)),
                lookback_seconds=int(config.get("lookback_seconds", 86400)),
                signature_limit=int(config.get("signature_limit", 40)),
                max_transactions_per_wallet=int(config.get("max_transactions_per_wallet", 20)),
                request_pause_seconds=float(config.get("request_pause_seconds", 0.2)),
                interval_seconds=interval_seconds,
            )
        except Exception as exc:
            update_component(
                COMPONENT,
                status="cycle_error",
                live_execution_locked=True,
                wallet_list_mutated=False,
                last_error=str(exc)[:240],
                heartbeat_interval=interval_seconds,
            )
        await asyncio.sleep(interval_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect recent tracked/paper-watch wallet activity into review-only evidence.")
    parser.add_argument("--execute", action="store_true", help="Fetch recent read-only wallet activity. Default is dry-run.")
    parser.add_argument("--loop", action="store_true", help="Run continuously at --interval seconds.")
    parser.add_argument("--interval", type=int, default=900)
    parser.add_argument("--max-wallets", type=int, default=100)
    parser.add_argument("--lookback-seconds", type=int, default=86400)
    parser.add_argument("--signature-limit", type=int, default=40)
    parser.add_argument("--max-transactions-per-wallet", type=int, default=20)
    parser.add_argument("--request-pause-seconds", type=float, default=0.2)
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    load_env()
    rpc = SyncRpcClient() if args.execute else None
    if args.loop:
        print(f"Forward wallet activity scheduler running every {args.interval}s. Live execution remains locked.")
        asyncio.run(
            forward_wallet_activity_loop(
                interval_seconds=args.interval,
                config={
                    "execute": args.execute,
                    "max_wallets": args.max_wallets,
                    "lookback_seconds": args.lookback_seconds,
                    "signature_limit": args.signature_limit,
                    "max_transactions_per_wallet": args.max_transactions_per_wallet,
                    "request_pause_seconds": args.request_pause_seconds if args.execute else 0.0,
                },
            )
        )
        return 0

    report = run_forward_wallet_activity_cycle(
        rpc=rpc,
        execute=args.execute,
        max_wallets=args.max_wallets,
        lookback_seconds=args.lookback_seconds,
        signature_limit=args.signature_limit,
        max_transactions_per_wallet=args.max_transactions_per_wallet,
        request_pause_seconds=args.request_pause_seconds if args.execute else 0.0,
        interval_seconds=None,
    )
    summary = report["summary"]
    print(
        "wrote {} execute={} wallets={} collected={} evidence_rows={} old_skipped={}".format(
            Path(args.out).relative_to(ROOT),
            bool(args.execute),
            summary["wallets_processed"],
            summary["wallets_collected"],
            summary["evidence_rows_created"],
            summary["old_signatures_skipped"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
