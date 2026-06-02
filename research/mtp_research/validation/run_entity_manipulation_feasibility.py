"""CLI for bounded entity-proxy feasibility audit."""

from __future__ import annotations

import argparse

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.entity_manipulation_feasibility import (
    build_entity_proxy_feasibility_report,
    write_entity_proxy_feasibility_outputs,
)


DEFAULT_CANDIDATES_PATH = data_lake_path(
    "data", "normalized", "launch_regime_classified", "launch_regime_candidates.jsonl"
)
DEFAULT_EVENTS_PATH = data_lake_path("data", "normalized", "pumpfun_lifecycle_events_classified.jsonl")
DEFAULT_HOLDER_STATE_SNAPSHOTS_PATH = data_lake_path(
    "data", "backtests", "holder_state", "strict_cohort_holder_state_snapshots.jsonl"
)
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "entity_manipulation_feasibility"
)


def main() -> int:
    args = parse_args()
    report = build_entity_proxy_feasibility_report(
        candidates_path=args.candidates_path,
        events_path=args.events_path,
        holder_state_snapshots_path=args.holder_state_snapshots_path,
        max_launches=args.max_launches,
        max_events=args.max_events,
    )
    paths = write_entity_proxy_feasibility_outputs(report, output_dir=args.output_dir)
    print(f"report_id={report['report_id']}")
    print(f"readiness_classification={report['readiness_classification']}")
    print(f"launches_attempted={report['scope']['launches_attempted']}")
    print(f"events_inspected={report['scope']['events_inspected']}")
    print(f"repeated_actors_across_launches={report['coverage_summary']['repeated_actors_across_launches']}")
    print(f"launches_with_quick_buy_sell_churn={report['coverage_summary']['launches_with_quick_buy_sell_churn']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run bounded entity-proxy feasibility audit.")
    parser.add_argument("--candidates-path", default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument("--events-path", default=DEFAULT_EVENTS_PATH)
    parser.add_argument("--holder-state-snapshots-path", default=DEFAULT_HOLDER_STATE_SNAPSHOTS_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-launches", type=int, default=100)
    parser.add_argument("--max-events", type=int, default=10_000)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
