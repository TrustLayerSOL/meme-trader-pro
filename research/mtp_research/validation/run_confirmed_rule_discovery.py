"""CLI for confirmed-only lifecycle rule discovery diagnostics."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.confirmed_rule_discovery import build_confirmed_rule_discovery


def main() -> int:
    args = parse_args()
    result = build_confirmed_rule_discovery(
        data_root=Path(args.data_root).expanduser() if args.data_root else None,
        source_roots=[Path(path).expanduser() for path in args.source_root] if args.source_root else None,
        execute=args.execute,
    )
    print("## Confirmed Rule Discovery")
    print(f"execute={result.get('execute')}")
    print(f"report_root={result.get('report_root')}")
    print(f"raw_crossed_20k_count={result.get('raw_crossed_20k_count')}")
    print(f"confirmed_crossed_20k_count={result.get('confirmed_crossed_20k_count')}")
    print(f"confirmed_actionable_crossed_20k_count={result.get('confirmed_actionable_crossed_20k_count')}")
    print(f"B1/B2/B3/B4={result.get('B1_confirmed_pass_count')}/{result.get('B2_confirmed_pass_count')}/{result.get('B3_confirmed_pass_count')}/{result.get('B4_confirmed_pass_count')}")
    print(f"E2_confirmed_exit_count={result.get('E2_confirmed_exit_count')}")
    recommendation = result.get("recommendation") or {}
    print(f"recommendation={recommendation.get('decision')}")
    print(f"paper_config_path={result.get('paper_config_path')}")
    print(f"status_file={result.get('status_file')}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run confirmed-only rule discovery diagnostics.")
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--source-root", action="append", default=None)
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
