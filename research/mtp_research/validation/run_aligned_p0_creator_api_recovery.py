"""CLI for bounded aligned P0 creator API recovery."""

from __future__ import annotations

import argparse

from research.mtp_research.validation.aligned_p0_creator_api_recovery import (
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_STATUS_PATH,
    DEFAULT_STRUCTURAL_FEATURES_PATH,
    run_aligned_p0_creator_api_recovery,
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_aligned_p0_creator_api_recovery(
        structural_features_path=args.structural_features_path,
        output_root=args.output_root,
        status_path=args.status_path,
        execute=args.execute,
        max_mints=args.max_mints,
        pre_launch_buffer_seconds=args.pre_launch_buffer_seconds,
        post_launch_buffer_seconds=args.post_launch_buffer_seconds,
        max_pages_per_mint=args.max_pages_per_mint,
        max_transactions_per_mint=args.max_transactions_per_mint,
        max_total_transactions=args.max_total_transactions,
        request_ceiling=args.request_ceiling,
        transaction_workers=args.transaction_workers,
    )
    print(f"report_id={report['report_id']}")
    print(f"executed={report['executed']}")
    print(f"selected_unknown_mints={report['selected_unknown_mints']}")
    print(f"projected_requests={report['projected_requests']}")
    print(f"network_calls_made={report['network_calls_made']}")
    print(f"transactions_seen={report['transactions_seen']}")
    print(f"raw_transactions_preserved={report['raw_transactions_preserved']}")
    print(f"recovered_creator_count={report['recovered_creator_count']}")
    print(f"unknown_or_missing_count={report['unknown_or_missing_count']}")
    print(f"readiness_classification={report['readiness_classification']}")
    print(f"warnings={report['warnings']}")
    print(f"summary_json={report['outputs']['summary_json_path']}")
    print(f"recovery_jsonl={report['outputs']['jsonl_path']}")
    print(f"raw_jsonl={report['outputs']['raw_jsonl_path']}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run bounded API recovery for missing aligned P0 creator metadata.")
    parser.add_argument("--structural-features-path", default=DEFAULT_STRUCTURAL_FEATURES_PATH)
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--max-mints", type=int, default=150)
    parser.add_argument("--pre-launch-buffer-seconds", type=int, default=600)
    parser.add_argument("--post-launch-buffer-seconds", type=int, default=600)
    parser.add_argument("--max-pages-per-mint", type=int, default=1)
    parser.add_argument("--max-transactions-per-mint", type=int, default=25)
    parser.add_argument("--max-total-transactions", type=int, default=5_000)
    parser.add_argument("--request-ceiling", type=int, default=500)
    parser.add_argument("--transaction-workers", type=int, default=8)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
