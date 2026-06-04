"""CLI for initializing forward paper/shadow tracking."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.forward_paper_shadow import initialize_forward_paper_shadow, paper_bankroll_status


def main() -> int:
    args = parse_args()
    if args.paper_status:
        status = paper_bankroll_status(data_root=Path(args.data_root).expanduser() if args.data_root else None)
        print("## Forward Paper Bankroll Status")
        print(f"enabled={status.get('enabled')}")
        print(f"readiness={status.get('readiness')}")
        print(f"current_bankroll_usd={status.get('current_bankroll_usd')}")
        print(f"cash_bankroll_usd={status.get('cash_bankroll_usd')}")
        print(f"next_max_position_usd={status.get('next_max_position_usd')}")
        print(f"open_position_count={status.get('open_position_count')}")
        print(f"ledger_rows={status.get('ledger_rows')}")
        print(f"rule_performance={status.get('rule_performance')}")
        print(f"state_path={status.get('state_path')}")
        print(f"ledger_path={status.get('ledger_path')}")
        print(f"rule_performance_path={status.get('rule_performance_path')}")
        return 0
    result = initialize_forward_paper_shadow(
        data_root=Path(args.data_root).expanduser() if args.data_root else None,
        execute=args.execute,
        enable_paper_simulation=args.enable_paper_simulation,
        starting_bankroll_usd=args.starting_bankroll_usd,
        max_position_fraction=args.max_position_fraction,
    )
    print("## Forward Paper/Shadow Scaffold")
    print(f"execute={result.get('execute')}")
    print(f"enabled={result.get('enabled')}")
    print(f"readiness={result.get('readiness')}")
    print(f"config_path={result.get('config_path')}")
    print(f"decisions_path={result.get('decisions_path')}")
    if result.get("enabled"):
        print(f"current_bankroll_usd={result.get('current_bankroll_usd')}")
        print(f"next_max_position_usd={result.get('next_max_position_usd')}")
        print(f"bankroll_state_path={result.get('bankroll_state_path')}")
        print(f"bankroll_ledger_path={result.get('bankroll_ledger_path')}")
        print(f"rule_performance_path={result.get('rule_performance_path')}")
    print(f"status_path={result.get('status_path')}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize forward paper/shadow tracking.")
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--enable-paper-simulation", action="store_true")
    parser.add_argument("--starting-bankroll-usd", type=float, default=100.0)
    parser.add_argument("--max-position-fraction", type=float, default=0.10)
    parser.add_argument("--paper-status", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
