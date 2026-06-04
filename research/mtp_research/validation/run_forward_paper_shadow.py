"""CLI for initializing forward paper/shadow tracking."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.forward_paper_shadow import initialize_forward_paper_shadow


def main() -> int:
    args = parse_args()
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
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
