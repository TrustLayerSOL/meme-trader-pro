"""CLI for creator migration reputation feasibility audit."""

from __future__ import annotations

import argparse

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.creator_migration_reputation_feasibility import (
    build_creator_migration_reputation_report,
    write_creator_migration_reputation_outputs,
)


DEFAULT_STRICT_CANDIDATES_PATH = data_lake_path(
    "data", "normalized", "launch_regime_classified", "launch_regime_candidates.jsonl"
)
DEFAULT_ALL_CANDIDATES_PATH = data_lake_path(
    "data", "normalized", "launch_lifecycle_collected_classified", "launch_regime_candidates.jsonl"
)
DEFAULT_EVENTS_PATH = data_lake_path("data", "normalized", "pumpfun_lifecycle_events_classified.jsonl")
DEFAULT_STRICT_OUTCOMES_PATH = data_lake_path(
    "data", "normalized", "launch_regime_classified", "launch_lifecycle_outcomes.jsonl"
)
DEFAULT_ALL_OUTCOMES_PATH = data_lake_path(
    "data", "normalized", "launch_lifecycle_collected_classified", "launch_lifecycle_outcomes.jsonl"
)
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "creator_migration_reputation_feasibility",
)


def main() -> int:
    args = parse_args()
    report = build_creator_migration_reputation_report(
        strict_candidates_path=args.strict_candidates_path,
        all_candidates_path=args.all_candidates_path,
        events_path=args.events_path,
        strict_outcomes_path=args.strict_outcomes_path,
        all_outcomes_path=args.all_outcomes_path,
        sample_limit=args.sample_limit,
    )
    paths = write_creator_migration_reputation_outputs(report, output_dir=args.output_dir)
    obs = report["migration_observability"]
    derived = report["derived_field_summary"]
    print(f"report_id={report['report_id']}")
    print(f"readiness_classification={report['readiness_classification']}")
    print(f"strict_launches={obs['strict_total_launches']}")
    print(f"all_collected_launches={obs['all_collected_total_launches']}")
    print(f"pumpfun_migrate_event_rows={obs['pumpfun_migrate_event_rows']}")
    print(f"unique_migrated_mints_observed={obs['unique_migrated_mints_observed']}")
    print(f"strict_unique_migrated_mints_observed={obs['strict_unique_migrated_mints_observed']}")
    print(f"migration_timestamp_available_count={obs['migration_timestamp_available_count']}")
    print(f"creators_with_at_least_1_migration_event={derived['creators_with_at_least_1_migration_event']}")
    print(f"strict_launches_with_4plus_prior_migrations={derived['launches_with_4plus_prior_migrations']}")
    print(f"t008_feasible_now={report['t008_creator_migration_reputation_feasible_now']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run creator migration reputation feasibility audit.")
    parser.add_argument("--strict-candidates-path", default=DEFAULT_STRICT_CANDIDATES_PATH)
    parser.add_argument("--all-candidates-path", default=DEFAULT_ALL_CANDIDATES_PATH)
    parser.add_argument("--events-path", default=DEFAULT_EVENTS_PATH)
    parser.add_argument("--strict-outcomes-path", default=DEFAULT_STRICT_OUTCOMES_PATH)
    parser.add_argument("--all-outcomes-path", default=DEFAULT_ALL_OUTCOMES_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--sample-limit", type=int, default=100)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
