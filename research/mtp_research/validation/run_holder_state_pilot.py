"""CLI for the bounded holder-state enrichment feasibility pilot."""

from __future__ import annotations

import argparse

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.holder_state_pilot import (
    MAX_LAUNCHES,
    build_holder_state_pilot_report,
    write_holder_state_pilot_outputs,
)


DEFAULT_CANDIDATES_PATH = data_lake_path(
    "data",
    "normalized",
    "launch_regime_classified",
    "launch_regime_candidates.jsonl",
)
DEFAULT_EVENTS_PATH = data_lake_path(
    "data",
    "normalized",
    "pumpfun_lifecycle_events_classified.jsonl",
)
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "holder_state_pilot",
)


def main() -> int:
    args = parse_args()
    report = build_holder_state_pilot_report(
        candidates_path=args.candidates_path,
        events_path=args.events_path,
        launch_limit=args.launch_limit,
    )
    paths = write_holder_state_pilot_outputs(report, output_dir=args.output_dir)
    print(f"feasibility_result={report['feasibility_result']}")
    print(f"launches_attempted={report['launches_attempted']}")
    print(f"snapshots_attempted={report['snapshots_attempted']}")
    print(f"snapshots_built={report['snapshots_built']}")
    print(f"missing_snapshots={report['missing_snapshots']}")
    print(f"holder_count_coverage_pct={report['holder_count_coverage_pct']:.2f}")
    print(f"top_holder_share_coverage_pct={report['top_holder_share_coverage_pct']:.2f}")
    print(f"top_10_holder_share_coverage_pct={report['top_10_holder_share_coverage_pct']:.2f}")
    print(f"creator_holder_share_coverage_pct={report['creator_holder_share_coverage_pct']:.2f}")
    print(f"api_calls_used={report['api_calls_used']}")
    print(f"helius_credits_used={report['helius_credits_used']}")
    print(
        "estimated_scale_holder_snapshots="
        f"{report['estimated_cost_to_scale_to_1500_launches']['holder_snapshots']}"
    )
    print(f"estimated_helius_credits_1500={report['api_requirements']['estimated_helius_credits_for_1500_launches']}")
    print(f"estimated_helius_credits_3000={report['api_requirements']['estimated_helius_credits_for_3000_launches']}")
    print(f"t001_v2_feasible={report['t001_v2_feasible']}")
    print(f"t002_v2_feasible={report['t002_v2_feasible']}")
    print(f"t001_t002_v2_feasible={report['t001_t002_v2_feasible']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run bounded holder-state feasibility pilot.")
    parser.add_argument("--candidates-path", default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument("--events-path", default=DEFAULT_EVENTS_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--launch-limit", type=int, default=MAX_LAUNCHES)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
