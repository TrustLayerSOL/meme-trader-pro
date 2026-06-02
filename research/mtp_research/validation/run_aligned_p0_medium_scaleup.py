"""CLI for aligned medium P0 structural enrichment scale-up."""

from __future__ import annotations

import argparse

from research.mtp_research.validation.aligned_p0_medium_scaleup import (
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_STATUS_PATH,
    DEFAULT_UNIVERSE_PATH,
    build_aligned_p0_medium_scaleup,
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report, outputs = build_aligned_p0_medium_scaleup(
        universe_path=args.universe_path,
        event_paths=args.event_path,
        creator_lookup_paths=args.creator_lookup_path,
        output_root=args.output_root,
        status_path=args.status_path,
        preferred_per_tier=args.preferred_per_tier,
        minimum_total_targets=args.minimum_total_targets,
        max_early_buyer_wallets=args.max_early_buyer_wallets,
        credit_cap=args.credit_cap,
        execute=args.execute,
        transaction_workers=args.transaction_workers,
    )
    print(f"report_id={report['report_id']}")
    print(f"mode={report['execution']['mode']}")
    print(f"readiness_classification={report['readiness_classification']}")
    print(f"launches_selected={report['target_cohort']['launches_selected']}")
    print(f"unique_dates={report['target_cohort']['unique_dates']}")
    print(f"unique_creators={report['target_cohort']['unique_creators']}")
    print(f"projected_credits={report['dry_run_budget']['projected_credits']}")
    print(f"request_ceiling_status={report['dry_run_budget']['request_ceiling_status']}")
    print(f"requests_used={report['collection_summary']['total_requests_used']}")
    print(f"transactions_fetched={report['collection_summary']['total_transactions_fetched']}")
    print(f"all_three_layer_launches={report['overlap_audit']['launches_with_all_three_p0_layers']}")
    print(f"warnings={report['warnings']}")
    print(f"target_set={outputs['target_set_path']}")
    print(f"dry_run_json={outputs['dry_run_json_path']}")
    print(f"summary_json={outputs['summary_json_path']}")
    print(f"combined_jsonl={outputs['combined_jsonl_path']}")
    print(f"combined_parquet={outputs['combined_parquet_path']}")
    print(f"status_path={outputs['status_path']}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run aligned medium P0 structural enrichment scale-up.")
    parser.add_argument("--universe-path", default=DEFAULT_UNIVERSE_PATH)
    parser.add_argument("--event-path", action="append", default=None)
    parser.add_argument("--creator-lookup-path", action="append", default=None)
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH)
    parser.add_argument("--preferred-per-tier", type=int, default=50)
    parser.add_argument("--minimum-total-targets", type=int, default=180)
    parser.add_argument("--max-early-buyer-wallets", type=int, default=3_000)
    parser.add_argument("--credit-cap", type=int, default=100_000)
    parser.add_argument("--transaction-workers", type=int, default=24)
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
