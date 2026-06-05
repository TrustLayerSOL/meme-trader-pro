"""CLI for the official lifecycle v2 paper-only trade monitor."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from research.mtp_research.validation.official_lifecycle_v2_paper_trader import (
    OfficialV2PaperTradeConfig,
    initialize_paper_trader,
    paper_trade_status,
    run_paper_trade_once,
)


def main() -> int:
    args = parse_args()
    config = OfficialV2PaperTradeConfig(
        data_root=Path(args.data_root).expanduser() if args.data_root else None,
        starting_wallet_usd=args.starting_wallet_usd,
        position_fraction=args.position_fraction,
    )
    if args.status:
        status = paper_trade_status(config)
        print("## Official Lifecycle v2 Paper Monitor")
        for key, value in status.items():
            print(f"{key}={value}")
        return 0
    if args.initialize:
        result = initialize_paper_trader(config, reset=args.reset)
        print("## Official Lifecycle v2 Paper Monitor Initialized")
        for key, value in result.items():
            print(f"{key}={value}")
        if not args.loop:
            return 0
    if args.loop:
        initialize_paper_trader(config, reset=args.reset)
        while True:
            result = run_paper_trade_once(config)
            print(
                "paper_monitor "
                f"buys={result['buys_created']} sells={result['sells_created']} "
                f"open={result['open_positions']} closed={result['closed_trades']} wallet={result['wallet_usd']}",
                flush=True,
            )
            time.sleep(max(1.0, float(args.poll_seconds)))
    result = run_paper_trade_once(config)
    print("## Official Lifecycle v2 Paper Monitor Update")
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run official lifecycle v2 paper-only trade monitor.")
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--starting-wallet-usd", type=float, default=300.0)
    parser.add_argument("--position-fraction", type=float, default=0.05)
    parser.add_argument("--poll-seconds", type=float, default=30.0)
    parser.add_argument("--initialize", action="store_true")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--status", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
