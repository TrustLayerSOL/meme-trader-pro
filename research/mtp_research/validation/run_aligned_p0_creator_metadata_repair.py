"""CLI for aligned P0 creator metadata repair and second-run planning."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.aligned_p0_creator_metadata_repair import (
    DEFAULT_ALIGNED_TARGET_PATH,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_REPO_LOCAL_ARTIFACTS,
    DEFAULT_STATUS_PATH,
    DEFAULT_STRUCTURAL_FEATURES_PATH,
    DEFAULT_SUMMARY_PATH,
    DEFAULT_UNIVERSE_PATH,
    build_aligned_p0_creator_metadata_repair,
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report, outputs = build_aligned_p0_creator_metadata_repair(
        summary_path=args.summary_path,
        structural_features_path=args.structural_features_path,
        aligned_target_path=args.aligned_target_path,
        universe_path=args.universe_path,
        creator_lookup_paths=args.creator_lookup_path,
        event_paths=args.event_path,
        repo_root=args.repo_root,
        repo_local_artifacts=args.repo_local_artifact,
        output_root=args.output_root,
        status_path=args.status_path,
        second_run_per_tier=args.second_run_per_tier,
        credit_cap=args.credit_cap,
    )
    print(f"report_id={report['report_id']}")
    print(f"network_calls_made={report['network_calls_made']}")
    print(f"unknown_creator_count_before={report['creator_audit']['unknown_creator_count_before']}")
    print(f"creator_recovered_count={report['creator_recovery']['recovered_count']}")
    print(f"unknown_creator_count_after={report['creator_audit']['unknown_creator_count_after']}")
    print(f"all_three_overlap_before={report['overlap_failure_audit']['all_three_layer_overlap_before']}")
    print(f"projected_all_three_overlap_second_plan={report['second_run_plan']['projected_all_three_layer_eligibility']}")
    print(f"second_run_target_count={report['second_run_plan']['target_count']}")
    print(f"second_run_projected_credits={report['second_run_plan']['projected_credits']}")
    print(f"second_aligned_run_recommended={report['second_run_plan']['another_helius_run_recommended']}")
    print(f"warnings={report['warnings']}")
    print(f"audit_json={outputs['audit_json_path']}")
    print(f"status_path={outputs['status_path']}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Repair aligned P0 creator metadata and plan a second aligned run.")
    parser.add_argument("--summary-path", default=DEFAULT_SUMMARY_PATH)
    parser.add_argument("--structural-features-path", default=DEFAULT_STRUCTURAL_FEATURES_PATH)
    parser.add_argument("--aligned-target-path", default=DEFAULT_ALIGNED_TARGET_PATH)
    parser.add_argument("--universe-path", default=DEFAULT_UNIVERSE_PATH)
    parser.add_argument("--creator-lookup-path", action="append", default=None)
    parser.add_argument("--event-path", action="append", default=None)
    parser.add_argument("--repo-root", default=Path("."))
    parser.add_argument("--repo-local-artifact", action="append", default=DEFAULT_REPO_LOCAL_ARTIFACTS)
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH)
    parser.add_argument("--second-run-per-tier", type=int, default=50)
    parser.add_argument("--credit-cap", type=int, default=100_000)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
