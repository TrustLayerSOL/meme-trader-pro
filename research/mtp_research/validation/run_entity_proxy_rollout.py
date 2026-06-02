"""CLI for full strict-cohort entity-proxy rollout."""

from __future__ import annotations

import argparse

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.entity_proxy_rollout import (
    build_entity_proxy_rollout,
    write_entity_proxy_rollout_outputs,
)


DEFAULT_CANDIDATES_PATH = data_lake_path(
    "data", "normalized", "launch_regime_classified", "launch_regime_candidates.jsonl"
)
DEFAULT_EVENTS_PATH = data_lake_path("data", "normalized", "pumpfun_lifecycle_events_classified.jsonl")
DEFAULT_HOLDER_STATE_SNAPSHOTS_PATH = data_lake_path(
    "data", "backtests", "holder_state", "strict_cohort_holder_state_snapshots.jsonl"
)
DEFAULT_DATASET_DIR = data_lake_path("data", "backtests", "entity_proxy")
DEFAULT_REPORT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "entity_proxy_strict_cohort"
)


def main() -> int:
    args = parse_args()
    rollout = build_entity_proxy_rollout(
        candidates_path=args.candidates_path,
        events_path=args.events_path,
        holder_state_snapshots_path=args.holder_state_snapshots_path,
    )
    paths = write_entity_proxy_rollout_outputs(
        rollout,
        dataset_dir=args.dataset_dir,
        report_dir=args.report_dir,
    )
    print(f"rollout_id={rollout['rollout_id']}")
    print(f"readiness_classification={rollout['readiness_classification']}")
    print(f"launches_processed={rollout['launches_processed']}")
    print(f"events_processed={rollout['events_processed']}")
    print(f"coverage_pct={rollout['audit']['coverage_pct']:.2f}")
    print(f"t007_feasible={rollout['t007_feasible']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run full strict-cohort entity-proxy rollout.")
    parser.add_argument("--candidates-path", default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument("--events-path", default=DEFAULT_EVENTS_PATH)
    parser.add_argument("--holder-state-snapshots-path", default=DEFAULT_HOLDER_STATE_SNAPSHOTS_PATH)
    parser.add_argument("--dataset-dir", default=DEFAULT_DATASET_DIR)
    parser.add_argument("--report-dir", default=DEFAULT_REPORT_DIR)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
