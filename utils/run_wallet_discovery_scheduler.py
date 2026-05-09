#!/usr/bin/env python3
"""
Run the safe wallet discovery scheduler.

This process refreshes watch-only candidate wallets, paper-watch wallets, and
dry-run apply preview status. It never applies tracked-wallet mutations and
never executes trades.
"""

import argparse
import asyncio
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.wallet_discovery_scheduler import run_wallet_discovery_cycle
from core.wallet_discovery_scheduler import wallet_discovery_loop


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run the wallet discovery scheduler.")
    parser.add_argument("--once", action="store_true", help="Run one safe scheduler cycle and exit.")
    parser.add_argument("--interval", type=int, default=300, help="Seconds between cycles.")
    parser.add_argument("--local-hours", type=float, default=6, help="Hours of local scanner events to mine.")
    parser.add_argument("--local-limit", type=int, default=5000, help="Maximum local scanner events per cycle.")
    parser.add_argument("--from-paper-winners", action="store_true", help="Also inspect recent winning paper mints with read-only RPC.")
    return parser.parse_args(argv)


def config_from_args(args):
    return {
        "interval_seconds": args.interval,
        "local_hours": args.local_hours,
        "local_limit": args.local_limit,
        "from_paper_winners": args.from_paper_winners,
    }


def main(argv=None):
    args = parse_args(argv)
    config = config_from_args(args)
    if args.once:
        summary = run_wallet_discovery_cycle(config=config)
        print(
            "Wallet discovery cycle complete | "
            f"candidates={summary['candidate_wallets']} "
            f"paper_watch={summary['paper_watch_wallets']} "
            f"approved_preview={summary['apply_preview']['summary'].get('approved_decisions', 0)}"
        )
        return 0

    print(f"Wallet discovery scheduler running every {args.interval}s. Live execution remains locked.")
    asyncio.run(wallet_discovery_loop(interval_seconds=args.interval, config=config))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
