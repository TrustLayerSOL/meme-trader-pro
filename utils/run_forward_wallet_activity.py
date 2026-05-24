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
from core.storage import EventStore
from core.json_store import atomic_write_json, read_json
from core.runtime_status import update_component
from core.rpc_provider import build_public_rpc_providers
from utils.discover_candidate_wallets import SyncRpcClient
from utils.run_wallet_history_backfill import merge_wallet_evidence_rows
from wallets.forward_market_context import build_forward_market_context_report
from wallets.forward_market_context import DEFAULT_MAX_EVENT_SNAPSHOT_LAG_SECONDS
from wallets.forward_market_context import DEFAULT_MAX_MARKET_CONTEXT_CALLS_PER_CYCLE
from wallets.forward_market_context import DEFAULT_MAX_MARKET_CONTEXT_MINTS
from wallets.forward_wallet_activity import build_forward_wallet_activity_report
from wallets.forward_wallet_activity import DEFAULT_FORWARD_MAX_WALLETS
from wallets.forward_wallet_activity import DEFAULT_ADAPTIVE_DEGRADED_MAX_WALLETS
from wallets.forward_wallet_activity import DEFAULT_MAX_RPC_CALLS_PER_CYCLE
from wallets.forward_wallet_activity import DEFAULT_MAX_RPC_CALLS_PER_DAY


DEFAULT_TRACKED = ROOT / "data" / "tracked_wallets.json"
DEFAULT_PAPER_WATCH = ROOT / "data" / "paper_watch_wallets.json"
DEFAULT_REPORT = ROOT / "data" / "wallet_backfills" / "forward_wallet_activity_report.json"
DEFAULT_EVIDENCE = ROOT / "data" / "wallet_evidence" / "wallet_history_evidence.jsonl"
DEFAULT_REPORT_DIR = ROOT / "data" / "reports" / "wallet_backfills"
DEFAULT_RAW_DIR = ROOT / "data" / "wallet_backfills" / "raw_transactions"
DEFAULT_MARKET_CONTEXT = ROOT / "data" / "wallet_backfills" / "forward_market_context_snapshots.jsonl"
DEFAULT_DB = ROOT / "data" / "memetrader.db"
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


def persist_market_context_snapshots(snapshots: list[dict[str, Any]], *, db_path: Path | str = DEFAULT_DB) -> int:
    if not snapshots:
        return 0
    store = EventStore(db_path)
    inserted = 0
    for snapshot in snapshots:
        store.insert_token_snapshot(snapshot)
        inserted += 1
    return inserted


def write_forward_wallet_activity_report(
    *,
    out_path: Path | str = DEFAULT_REPORT,
    evidence_path: Path | str = DEFAULT_EVIDENCE,
    report_dir: Path | str = DEFAULT_REPORT_DIR,
    raw_dir: Path | str = DEFAULT_RAW_DIR,
    market_context_path: Path | str = DEFAULT_MARKET_CONTEXT,
    db_path: Path | str = DEFAULT_DB,
    tracked_wallets: Any | None = None,
    paper_watch_wallets: Any | None = None,
    rpc: Any | None = None,
    market_context_provider=None,
    generated_at: float | None = None,
    lookback_seconds: int = 86400,
    execute: bool = False,
    max_wallets: int = DEFAULT_FORWARD_MAX_WALLETS,
    signature_limit: int = 40,
    max_transactions_per_wallet: int = 20,
    request_pause_seconds: float = 0.0,
    interval_seconds: int | None = None,
    max_rpc_calls_per_cycle: int = DEFAULT_MAX_RPC_CALLS_PER_CYCLE,
    max_rpc_calls_per_day: int = DEFAULT_MAX_RPC_CALLS_PER_DAY,
    rpc_preflight: bool = False,
    adaptive_free_rpc_throttle: bool = False,
    adaptive_degraded_max_wallets: int = DEFAULT_ADAPTIVE_DEGRADED_MAX_WALLETS,
    capture_market_context: bool = False,
    persist_market_context: bool = True,
    max_market_mints: int = DEFAULT_MAX_MARKET_CONTEXT_MINTS,
    max_market_context_calls_per_cycle: int = DEFAULT_MAX_MARKET_CONTEXT_CALLS_PER_CYCLE,
    max_event_snapshot_lag_seconds: float = DEFAULT_MAX_EVENT_SNAPSHOT_LAG_SECONDS,
    rpc_mode: str = "free_public_rpc",
    paid_rpc_allowed: bool = False,
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
        interval_seconds=interval_seconds,
        max_rpc_calls_per_cycle=max_rpc_calls_per_cycle,
        max_rpc_calls_per_day=max_rpc_calls_per_day,
        rpc_preflight=rpc_preflight,
        adaptive_free_rpc_throttle=adaptive_free_rpc_throttle,
        adaptive_degraded_max_wallets=adaptive_degraded_max_wallets,
    )
    report["rpc_mode"] = str(rpc_mode)
    report["paid_rpc_allowed"] = bool(paid_rpc_allowed)
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

    market_snapshots: list[dict[str, Any]] = []
    if capture_market_context:
        market_report = build_forward_market_context_report(
            evidence_records=report.get("evidence_records") if isinstance(report.get("evidence_records"), list) else [],
            market_provider=market_context_provider,
            generated_at=generated_at,
            execute=execute,
            max_market_mints=max_market_mints,
            max_market_context_calls_per_cycle=max_market_context_calls_per_cycle,
            max_event_snapshot_lag_seconds=max_event_snapshot_lag_seconds,
        )
        report["evidence_records"] = market_report.get("evidence_records", [])
        market_snapshots = (
            market_report.get("market_context_snapshots")
            if isinstance(market_report.get("market_context_snapshots"), list)
            else []
        )
        report["market_context"] = {
            "mode": market_report.get("mode"),
            "summary": market_report.get("summary"),
            "api_budget": market_report.get("api_budget"),
            "limits": market_report.get("limits"),
            "live_execution_locked": market_report.get("live_execution_locked"),
            "review_only": market_report.get("review_only"),
        }
    else:
        report["market_context"] = {
            "mode": "FORWARD_MARKET_CONTEXT_DISABLED",
            "summary": {
                "snapshots_collected": 0,
                "evidence_rows_with_forward_context": 0,
            },
        }

    if market_snapshots:
        write_jsonl(market_context_path, market_snapshots)
        report["market_context_snapshots_path"] = display_path(Path(market_context_path))
        report["market_context_snapshots_written"] = len(market_snapshots)
        if persist_market_context:
            report["market_context_snapshots_persisted"] = persist_market_context_snapshots(
                market_snapshots,
                db_path=db_path,
            )
        else:
            report["market_context_snapshots_persisted"] = 0
    else:
        report["market_context_snapshots_path"] = None
        report["market_context_snapshots_written"] = 0
        report["market_context_snapshots_persisted"] = 0

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
    max_wallets: int = DEFAULT_FORWARD_MAX_WALLETS,
    lookback_seconds: int = 86400,
    signature_limit: int = 40,
    max_transactions_per_wallet: int = 20,
    request_pause_seconds: float = 0.0,
    max_rpc_calls_per_cycle: int = DEFAULT_MAX_RPC_CALLS_PER_CYCLE,
    max_rpc_calls_per_day: int = DEFAULT_MAX_RPC_CALLS_PER_DAY,
    rpc_preflight: bool = False,
    adaptive_free_rpc_throttle: bool = False,
    adaptive_degraded_max_wallets: int = DEFAULT_ADAPTIVE_DEGRADED_MAX_WALLETS,
    capture_market_context: bool = False,
    persist_market_context: bool = True,
    max_market_mints: int = DEFAULT_MAX_MARKET_CONTEXT_MINTS,
    max_market_context_calls_per_cycle: int = DEFAULT_MAX_MARKET_CONTEXT_CALLS_PER_CYCLE,
    max_event_snapshot_lag_seconds: float = DEFAULT_MAX_EVENT_SNAPSHOT_LAG_SECONDS,
    interval_seconds: int | None = None,
    rpc_mode: str = "free_public_rpc",
    paid_rpc_allowed: bool = False,
) -> dict[str, Any]:
    update_status(
        COMPONENT,
        status="cycle_running",
        live_execution_locked=True,
        wallet_list_mutated=False,
        execute=bool(execute),
        heartbeat_interval=interval_seconds,
        max_rpc_calls_per_cycle=max_rpc_calls_per_cycle,
        max_rpc_calls_per_day=max_rpc_calls_per_day,
        rpc_preflight=bool(rpc_preflight),
        adaptive_free_rpc_throttle=bool(adaptive_free_rpc_throttle),
        adaptive_degraded_max_wallets=int(adaptive_degraded_max_wallets),
        capture_market_context=bool(capture_market_context),
        max_market_context_calls_per_cycle=max_market_context_calls_per_cycle,
        rpc_mode=rpc_mode,
        paid_rpc_allowed=paid_rpc_allowed,
    )
    report = write_report(
        rpc=rpc,
        execute=execute,
        max_wallets=max_wallets,
        lookback_seconds=lookback_seconds,
        signature_limit=signature_limit,
        max_transactions_per_wallet=max_transactions_per_wallet,
        request_pause_seconds=request_pause_seconds,
        interval_seconds=interval_seconds,
        max_rpc_calls_per_cycle=max_rpc_calls_per_cycle,
        max_rpc_calls_per_day=max_rpc_calls_per_day,
        rpc_preflight=rpc_preflight,
        adaptive_free_rpc_throttle=adaptive_free_rpc_throttle,
        adaptive_degraded_max_wallets=adaptive_degraded_max_wallets,
        capture_market_context=capture_market_context,
        persist_market_context=persist_market_context,
        max_market_mints=max_market_mints,
        max_market_context_calls_per_cycle=max_market_context_calls_per_cycle,
        max_event_snapshot_lag_seconds=max_event_snapshot_lag_seconds,
        rpc_mode=rpc_mode,
        paid_rpc_allowed=paid_rpc_allowed,
    )
    summary = report.get("summary") if isinstance(report, dict) else {}
    api_budget = report.get("api_budget") if isinstance(report.get("api_budget"), dict) else {}
    market_context = report.get("market_context") if isinstance(report.get("market_context"), dict) else {}
    market_summary = market_context.get("summary") if isinstance(market_context.get("summary"), dict) else {}
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
        wallets_blocked_api_budget=int(summary.get("wallets_blocked_api_budget", 0) or 0),
        api_budget_status=api_budget.get("budget_status"),
        rpc_preflight_status=report.get("rpc_preflight", {}).get("status") if isinstance(report.get("rpc_preflight"), dict) else None,
        wallets_blocked_rpc_preflight=int(summary.get("wallets_blocked_rpc_preflight", 0) or 0),
        wallets_throttled_by_rpc_preflight=int(summary.get("wallets_throttled_by_rpc_preflight", 0) or 0),
        estimated_rpc_calls_per_cycle=int(api_budget.get("estimated_rpc_calls_per_cycle", 0) or 0),
        projected_rpc_calls_per_day=api_budget.get("projected_rpc_calls_per_day"),
        capture_market_context=bool(capture_market_context),
        market_context_snapshots_collected=int(market_summary.get("snapshots_collected", 0) or 0),
        evidence_rows_with_forward_context=int(market_summary.get("evidence_rows_with_forward_context", 0) or 0),
        market_context_budget_status=(
            market_context.get("api_budget", {}).get("budget_status")
            if isinstance(market_context.get("api_budget"), dict)
            else None
        ),
        heartbeat_interval=interval_seconds,
        rpc_mode=rpc_mode,
        paid_rpc_allowed=bool(paid_rpc_allowed),
    )
    return report


def build_forward_rpc_client(
    *,
    allow_paid_rpc: bool = False,
    free_rpc_urls: str | None = None,
    timeout: int = 15,
) -> SyncRpcClient:
    if allow_paid_rpc:
        return SyncRpcClient(timeout=timeout)
    return SyncRpcClient(providers=build_public_rpc_providers(urls=free_rpc_urls), timeout=timeout)


async def forward_wallet_activity_loop(interval_seconds: int = 900, config: dict[str, Any] | None = None) -> None:
    config = dict(config or {})
    config.setdefault("interval_seconds", interval_seconds)
    while True:
        try:
            load_env()
            allow_paid_rpc = bool(config.get("allow_paid_rpc"))
            rpc = (
                build_forward_rpc_client(
                    allow_paid_rpc=allow_paid_rpc,
                    free_rpc_urls=config.get("free_rpc_urls"),
                )
                if config.get("execute")
                else None
            )
            await asyncio.to_thread(
                run_forward_wallet_activity_cycle,
                rpc=rpc,
                execute=bool(config.get("execute")),
                max_wallets=int(config.get("max_wallets", DEFAULT_FORWARD_MAX_WALLETS)),
                lookback_seconds=int(config.get("lookback_seconds", 86400)),
                signature_limit=int(config.get("signature_limit", 40)),
                max_transactions_per_wallet=int(config.get("max_transactions_per_wallet", 20)),
                request_pause_seconds=float(config.get("request_pause_seconds", 0.2)),
                max_rpc_calls_per_cycle=int(config.get("max_rpc_calls_per_cycle", DEFAULT_MAX_RPC_CALLS_PER_CYCLE)),
                max_rpc_calls_per_day=int(config.get("max_rpc_calls_per_day", DEFAULT_MAX_RPC_CALLS_PER_DAY)),
                rpc_preflight=bool(config.get("rpc_preflight")),
                adaptive_free_rpc_throttle=bool(config.get("adaptive_free_rpc_throttle")),
                adaptive_degraded_max_wallets=int(
                    config.get("adaptive_degraded_max_wallets", DEFAULT_ADAPTIVE_DEGRADED_MAX_WALLETS)
                ),
                capture_market_context=bool(config.get("capture_market_context")),
                max_market_mints=int(config.get("max_market_mints", DEFAULT_MAX_MARKET_CONTEXT_MINTS)),
                max_market_context_calls_per_cycle=int(
                    config.get("max_market_context_calls_per_cycle", DEFAULT_MAX_MARKET_CONTEXT_CALLS_PER_CYCLE)
                ),
                max_event_snapshot_lag_seconds=float(
                    config.get("max_event_snapshot_lag_seconds", DEFAULT_MAX_EVENT_SNAPSHOT_LAG_SECONDS)
                ),
                interval_seconds=interval_seconds,
                rpc_mode="paid_rpc_explicit" if allow_paid_rpc else "free_public_rpc",
                paid_rpc_allowed=allow_paid_rpc,
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
    parser.add_argument("--max-wallets", type=int, default=DEFAULT_FORWARD_MAX_WALLETS)
    parser.add_argument("--lookback-seconds", type=int, default=86400)
    parser.add_argument("--signature-limit", type=int, default=40)
    parser.add_argument("--max-transactions-per-wallet", type=int, default=20)
    parser.add_argument("--request-pause-seconds", type=float, default=0.2)
    parser.add_argument("--max-rpc-calls-per-cycle", type=int, default=DEFAULT_MAX_RPC_CALLS_PER_CYCLE)
    parser.add_argument("--max-rpc-calls-per-day", type=int, default=DEFAULT_MAX_RPC_CALLS_PER_DAY)
    parser.add_argument("--skip-rpc-preflight", action="store_true", help="Skip the public RPC health probe before collection.")
    parser.add_argument("--disable-adaptive-free-rpc", action="store_true", help="Do not reduce wallet count when public RPC is degraded.")
    parser.add_argument("--adaptive-degraded-max-wallets", type=int, default=DEFAULT_ADAPTIVE_DEGRADED_MAX_WALLETS)
    parser.add_argument("--capture-market-context", action="store_true", help="Capture current price/liquidity/market-cap context for observed token mints.")
    parser.add_argument("--max-market-mints", type=int, default=DEFAULT_MAX_MARKET_CONTEXT_MINTS)
    parser.add_argument("--max-market-context-calls-per-cycle", type=int, default=DEFAULT_MAX_MARKET_CONTEXT_CALLS_PER_CYCLE)
    parser.add_argument("--max-event-snapshot-lag-seconds", type=float, default=DEFAULT_MAX_EVENT_SNAPSHOT_LAG_SECONDS)
    parser.add_argument("--no-persist-market-context", action="store_true", help="Write context JSONL but skip SQLite token_snapshots persistence.")
    parser.add_argument("--free-mode", action="store_true", help="Use public/free RPC only. This is the default and is kept as an explicit operator reminder.")
    parser.add_argument(
        "--free-rpc-urls",
        help="Comma-separated free/public Solana RPC fallback URLs. Helius/API-key URLs are ignored unless --allow-paid-rpc is used.",
    )
    parser.add_argument("--allow-paid-rpc", action="store_true", help="Explicitly allow Helius/paid RPC providers. Default is public/free RPC only.")
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    if args.free_mode and args.allow_paid_rpc:
        parser.error("--free-mode cannot be combined with --allow-paid-rpc")

    load_env()
    rpc_mode = "paid_rpc_explicit" if args.allow_paid_rpc else "free_public_rpc"
    rpc_preflight = bool(args.execute and not args.skip_rpc_preflight)
    adaptive_free_rpc_throttle = bool(args.execute and not args.allow_paid_rpc and not args.disable_adaptive_free_rpc)
    rpc = (
        build_forward_rpc_client(allow_paid_rpc=args.allow_paid_rpc, free_rpc_urls=args.free_rpc_urls)
        if args.execute
        else None
    )
    if args.loop:
        print(
            f"Forward wallet activity scheduler running every {args.interval}s. "
            f"Live execution remains locked. rpc_mode={rpc_mode}"
        )
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
                    "max_rpc_calls_per_cycle": args.max_rpc_calls_per_cycle,
                    "max_rpc_calls_per_day": args.max_rpc_calls_per_day,
                    "rpc_preflight": rpc_preflight,
                    "adaptive_free_rpc_throttle": adaptive_free_rpc_throttle,
                    "adaptive_degraded_max_wallets": args.adaptive_degraded_max_wallets,
                    "capture_market_context": args.capture_market_context,
                    "max_market_mints": args.max_market_mints,
                    "max_market_context_calls_per_cycle": args.max_market_context_calls_per_cycle,
                    "max_event_snapshot_lag_seconds": args.max_event_snapshot_lag_seconds,
                    "allow_paid_rpc": args.allow_paid_rpc,
                    "free_rpc_urls": args.free_rpc_urls,
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
        max_rpc_calls_per_cycle=args.max_rpc_calls_per_cycle,
        max_rpc_calls_per_day=args.max_rpc_calls_per_day,
        rpc_preflight=rpc_preflight,
        adaptive_free_rpc_throttle=adaptive_free_rpc_throttle,
        adaptive_degraded_max_wallets=args.adaptive_degraded_max_wallets,
        capture_market_context=args.capture_market_context,
        persist_market_context=not args.no_persist_market_context,
        max_market_mints=args.max_market_mints,
        max_market_context_calls_per_cycle=args.max_market_context_calls_per_cycle,
        max_event_snapshot_lag_seconds=args.max_event_snapshot_lag_seconds,
        interval_seconds=args.interval,
        rpc_mode=rpc_mode,
        paid_rpc_allowed=args.allow_paid_rpc,
    )
    summary = report["summary"]
    api_budget = report.get("api_budget", {})
    market_summary = (report.get("market_context") or {}).get("summary") or {}
    print(
        "wrote {} execute={} rpc_mode={} preflight={} wallets={} collected={} evidence_rows={} old_skipped={} budget={} est_calls={} throttled={} market_snapshots={}".format(
            Path(args.out).relative_to(ROOT),
            bool(args.execute),
            rpc_mode,
            report.get("rpc_preflight", {}).get("status") if isinstance(report.get("rpc_preflight"), dict) else None,
            summary["wallets_processed"],
            summary["wallets_collected"],
            summary["evidence_rows_created"],
            summary["old_signatures_skipped"],
            api_budget.get("budget_status"),
            api_budget.get("estimated_rpc_calls_per_cycle"),
            summary.get("wallets_throttled_by_rpc_preflight", 0),
            market_summary.get("snapshots_collected", 0),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
