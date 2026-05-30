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
from core.json_store import atomic_write_json
from utils.run_forward_wallet_activity import build_forward_rpc_client
from utils.run_forward_wallet_activity import run_forward_wallet_activity_cycle
from wallets.forward_free_rpc_canary import build_forward_free_rpc_canary_report


DEFAULT_REPORT = ROOT / "data" / "reports" / "forward_testing" / "forward_free_rpc_canary_report.json"


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def write_forward_free_rpc_canary_report(
    *,
    out_path: Path | str = DEFAULT_REPORT,
    duration_seconds: int = 1800,
    cycle_interval_seconds: int = 300,
    max_wallets: int = 10,
    signature_limit: int = 8,
    max_transactions_per_wallet: int = 3,
    lookback_seconds: int = 86400,
    request_pause_seconds: float = 1.5,
    max_rpc_calls_per_cycle: int = 1050,
    max_rpc_calls_per_day: int = 120000,
    capture_market_context: bool = True,
    max_market_mints: int = 25,
    max_market_context_calls_per_cycle: int = 100,
    adaptive_degraded_max_wallets: int = 5,
    free_rpc_urls: str | None = None,
    sleep_seconds_override: float | None = None,
) -> dict[str, Any]:
    load_env()

    def cycle_runner(**kwargs):
        rpc = build_forward_rpc_client(allow_paid_rpc=False, free_rpc_urls=free_rpc_urls)
        return run_forward_wallet_activity_cycle(rpc=rpc, **kwargs)

    sleeper = time.sleep if sleep_seconds_override is None else (lambda _seconds: time.sleep(float(sleep_seconds_override)))
    report = build_forward_free_rpc_canary_report(
        cycle_runner=cycle_runner,
        sleep=sleeper,
        duration_seconds=duration_seconds,
        cycle_interval_seconds=cycle_interval_seconds,
        max_wallets=max_wallets,
        signature_limit=signature_limit,
        max_transactions_per_wallet=max_transactions_per_wallet,
        lookback_seconds=lookback_seconds,
        request_pause_seconds=request_pause_seconds,
        max_rpc_calls_per_cycle=max_rpc_calls_per_cycle,
        max_rpc_calls_per_day=max_rpc_calls_per_day,
        capture_market_context=capture_market_context,
        max_market_mints=max_market_mints,
        max_market_context_calls_per_cycle=max_market_context_calls_per_cycle,
        adaptive_degraded_max_wallets=adaptive_degraded_max_wallets,
    )
    out = Path(out_path)
    atomic_write_json(out, report)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(report["generated_at"]))
    snapshot_path = out.parent / f"forward_free_rpc_canary_{stamp}.json"
    atomic_write_json(snapshot_path, report)
    report["report_path"] = display_path(out)
    report["snapshot_path"] = display_path(snapshot_path)
    atomic_write_json(out, report)
    atomic_write_json(snapshot_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a small review-only public/free RPC forward evidence canary.")
    parser.add_argument("--duration-seconds", type=int, default=1800)
    parser.add_argument("--cycle-interval-seconds", type=int, default=300)
    parser.add_argument("--max-wallets", type=int, default=10)
    parser.add_argument("--signature-limit", type=int, default=8)
    parser.add_argument("--max-transactions-per-wallet", type=int, default=3)
    parser.add_argument("--lookback-seconds", type=int, default=86400)
    parser.add_argument("--request-pause-seconds", type=float, default=1.5)
    parser.add_argument("--max-rpc-calls-per-cycle", type=int, default=1050)
    parser.add_argument("--max-rpc-calls-per-day", type=int, default=120000)
    parser.add_argument("--max-market-mints", type=int, default=25)
    parser.add_argument("--max-market-context-calls-per-cycle", type=int, default=100)
    parser.add_argument("--adaptive-degraded-max-wallets", type=int, default=5)
    parser.add_argument("--free-rpc-urls")
    parser.add_argument("--no-market-context", action="store_true")
    parser.add_argument("--sleep-seconds-override", type=float)
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    report = write_forward_free_rpc_canary_report(
        out_path=args.out,
        duration_seconds=args.duration_seconds,
        cycle_interval_seconds=args.cycle_interval_seconds,
        max_wallets=args.max_wallets,
        signature_limit=args.signature_limit,
        max_transactions_per_wallet=args.max_transactions_per_wallet,
        lookback_seconds=args.lookback_seconds,
        request_pause_seconds=args.request_pause_seconds,
        max_rpc_calls_per_cycle=args.max_rpc_calls_per_cycle,
        max_rpc_calls_per_day=args.max_rpc_calls_per_day,
        capture_market_context=not args.no_market_context,
        max_market_mints=args.max_market_mints,
        max_market_context_calls_per_cycle=args.max_market_context_calls_per_cycle,
        adaptive_degraded_max_wallets=args.adaptive_degraded_max_wallets,
        free_rpc_urls=args.free_rpc_urls,
        sleep_seconds_override=args.sleep_seconds_override,
    )
    summary = report["summary"]
    print(json.dumps({
        "report_path": report["report_path"],
        "recommendation": report["recommendation"],
        "cycles_attempted": summary["cycles_attempted"],
        "wallets_processed": summary["wallets_processed"],
        "evidence_rows_created": summary["evidence_rows_created"],
        "market_snapshots_collected": summary["market_snapshots_collected"],
        "provider_status_counts": report["provider_status_counts"],
        "blockers": report["blockers"],
        "projected_rpc_calls_per_day": report["budget"].get("projected_rpc_calls_per_day"),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
