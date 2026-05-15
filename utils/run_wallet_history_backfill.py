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

from core.env_loader import load_env
from core.json_store import atomic_write_json, read_json
from utils.build_wallet_candidate_backfill_targets import read_jsonl
from utils.discover_candidate_wallets import SyncRpcClient
from wallets.wallet_history_backfill import build_wallet_history_backfill_report


DEFAULT_TARGETS = ROOT / "data" / "wallet_candidate_backfill_targets.json"
DEFAULT_REPLAY_EVENTS = ROOT / "data" / "historical_replay" / "replay_events.jsonl"
DEFAULT_REPORT = ROOT / "data" / "wallet_backfills" / "wallet_history_backfill_report.json"
DEFAULT_EVIDENCE = ROOT / "data" / "wallet_evidence" / "wallet_history_evidence.jsonl"
DEFAULT_REPORT_DIR = ROOT / "data" / "reports" / "wallet_backfills"
DEFAULT_RAW_DIR = ROOT / "data" / "wallet_backfills" / "raw_transactions"


def append_jsonl(path: Path | str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def write_wallet_history_backfill_report(
    *,
    out_path: Path | str = DEFAULT_REPORT,
    evidence_path: Path | str = DEFAULT_EVIDENCE,
    report_dir: Path | str = DEFAULT_REPORT_DIR,
    raw_dir: Path | str = DEFAULT_RAW_DIR,
    backfill_targets: Any | None = None,
    replay_events: list[dict[str, Any]] | None = None,
    rpc: Any | None = None,
    execute: bool = False,
    max_wallets: int = 45,
    signature_limit: int = 40,
    max_transactions_per_wallet: int = 20,
    request_pause_seconds: float = 0.0,
) -> dict[str, Any]:
    generated_at = time.time()
    report = build_wallet_history_backfill_report(
        backfill_targets=backfill_targets if backfill_targets is not None else read_json(DEFAULT_TARGETS, {"targets": []}),
        replay_events=replay_events if replay_events is not None else read_jsonl(DEFAULT_REPLAY_EVENTS),
        rpc=rpc,
        execute=execute,
        generated_at=generated_at,
        max_wallets=max_wallets,
        signature_limit=signature_limit,
        max_transactions_per_wallet=max_transactions_per_wallet,
        request_pause_seconds=request_pause_seconds,
    )
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(generated_at))
    raw_rows = report.pop("raw_transactions", [])
    if raw_rows:
        raw_path = Path(raw_dir) / f"wallet_history_raw_{stamp}.jsonl"
        append_jsonl(raw_path, raw_rows)
        report["raw_transactions_path"] = str(raw_path.relative_to(ROOT))
        report["raw_transactions_preserved"] = len(raw_rows)
    else:
        report["raw_transactions_path"] = None
        report["raw_transactions_preserved"] = 0
    out = Path(out_path)
    atomic_write_json(out, report)

    report_snapshot = Path(report_dir) / f"wallet_history_backfill_{stamp}.json"
    atomic_write_json(report_snapshot, report)

    append_jsonl(evidence_path, report.get("evidence_records") if isinstance(report.get("evidence_records"), list) else [])
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a read-only wallet-history backfill report.")
    parser.add_argument("--execute", action="store_true", help="Fetch read-only wallet history. Default is dry-run only.")
    parser.add_argument("--max-wallets", type=int, default=45)
    parser.add_argument("--signature-limit", type=int, default=40)
    parser.add_argument("--max-transactions-per-wallet", type=int, default=20)
    parser.add_argument("--request-pause-seconds", type=float, default=0.2)
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    load_env()
    rpc = SyncRpcClient() if args.execute else None
    report = write_wallet_history_backfill_report(
        out_path=args.out,
        rpc=rpc,
        execute=args.execute,
        max_wallets=args.max_wallets,
        signature_limit=args.signature_limit,
        max_transactions_per_wallet=args.max_transactions_per_wallet,
        request_pause_seconds=args.request_pause_seconds if args.execute else 0.0,
    )
    summary = report["summary"]
    print(
        "wrote {} execute={} wallets={} collected={} partial={} blocked={} evidence_rows={} ready={}".format(
            Path(args.out).relative_to(ROOT),
            bool(args.execute),
            summary["wallets_processed"],
            summary["wallets_successfully_backfilled"],
            summary["wallets_partially_backfilled"],
            summary["wallets_blocked"],
            summary["total_evidence_rows_created"],
            summary["ready_for_candidate_review"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
