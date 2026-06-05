"""CLI for fixed buy/exit start-rule paper-shadow design."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.buy_exit_start_rule_design import run_buy_exit_start_rule_design


def main() -> int:
    args = parse_args()
    result = run_buy_exit_start_rule_design(
        data_root=Path(args.data_root).expanduser() if args.data_root else None,
        source_root=Path(args.source_root).expanduser() if args.source_root else None,
        execute=args.execute,
    )
    print("## Buy/Exit Start Rule Design")
    print(f"execute={result.get('execute')}")
    print(f"snapshot_label={result.get('snapshot_label')}")
    print(f"snapshot_source={result.get('snapshot_source') or result.get('source_root')}")
    print(f"all_crossed_20k_count={result.get('all_crossed_20k_count')}")
    print(f"actionable_crossed_20k_count={result.get('actionable_crossed_20k_count')}")
    print(f"quality_gate_result={result.get('quality_gate_result')}")
    print(f"selected_buy_rule_id={result.get('selected_buy_rule_id')}")
    print(f"selected_exit_rule_id={result.get('selected_exit_rule_id')}")
    print(f"readiness_classification={result.get('readiness_classification') or result.get('readiness')}")
    print(f"disabled_config_path={result.get('disabled_config_path')}")
    print(f"status_file={result.get('status_file')}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build fixed buy/exit paper-shadow start-rule design artifacts.")
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--source-root", default=None)
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
