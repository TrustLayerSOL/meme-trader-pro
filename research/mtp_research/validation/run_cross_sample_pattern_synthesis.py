"""CLI for descriptive cross-sample runner-pattern synthesis."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research.mtp_research.data_paths import data_lake_root
from research.mtp_research.validation.cross_sample_pattern_synthesis import run_cross_sample_pattern_synthesis


def main() -> int:
    parser = argparse.ArgumentParser(description="Run read-only cross-sample MemeTraderPro runner-pattern synthesis.")
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--timestamp", default=None)
    args = parser.parse_args()

    report = run_cross_sample_pattern_synthesis(
        Path(args.data_root) if args.data_root else data_lake_root(),
        timestamp=args.timestamp,
        status_root=Path.cwd(),
    )
    print("## Cross-Sample Pattern Synthesis")
    print(f"collector_left_running={report['guardrails']['collector_left_running']}")
    print(f"no_live_trading={report['guardrails']['no_live_trading']}")
    print(f"no_enabled_paper_trading={report['guardrails']['no_enabled_paper_trading']}")
    print(f"snapshot={report['snapshot']['snapshot_root']}")
    print(f"datasets_combined={report['summary']['datasets_combined']}")
    print(f"mints_analyzed={report['summary']['mints_analyzed']}")
    print(f"recommendation={report['recommendation']['recommendation_id']}")
    print(f"summary_json={report['paths']['summary_json']}")
    print(json.dumps({"findings": report["findings"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
