"""CLI for historical Solana meme runner rule-discovery diagnostics."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.historical_rule_discovery import build_historical_rule_discovery


def main() -> int:
    args = parse_args()
    result = build_historical_rule_discovery(
        data_root=Path(args.data_root).expanduser() if args.data_root else None,
        source_paths=[Path(path).expanduser() for path in args.source_path] if args.source_path else None,
        execute=args.execute,
    )
    print("## Historical Rule Discovery")
    print(f"execute={result.get('execute')}")
    print(f"report_root={result.get('report_root')}")
    print(f"historical_rows_analyzed={result.get('historical_rows_analyzed')}")
    print(f"historical_mints_analyzed={result.get('historical_mints_analyzed')}")
    print(f"readiness_classification={result.get('readiness_classification')}")
    recommendation = result.get("selected_paper_shadow_candidate") or {}
    print(f"selected_buy_rule={recommendation.get('selected_buy_rule_id')}")
    print(f"selected_exit_rule={recommendation.get('selected_exit_rule_id')}")
    print(f"config_path={result.get('config_path')}")
    print(f"status_file={result.get('status_file')}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run historical rule-discovery diagnostics.")
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--source-path", action="append", default=None)
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
