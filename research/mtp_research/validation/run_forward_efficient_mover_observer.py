"""CLI for forward efficient-mover observation logger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research.mtp_research.validation.forward_efficient_mover_observer import (
    ForwardObserverConfig,
    MockCandidateSource,
    print_status,
    run_dry_run,
    run_live_program_probe,
    run_observe,
    run_status,
)


def main() -> int:
    args = parse_args()
    config = ForwardObserverConfig(
        mode=args.mode,
        data_root=Path(args.data_root).expanduser() if args.data_root else None,
        target_candidates=args.target_candidates,
        start_trigger=float(args.start_trigger),
        poll_seconds=float(args.poll_seconds),
        status_interval_seconds=args.status_interval_seconds,
        max_runtime_minutes=args.max_runtime_minutes,
        max_api_calls=args.max_api_calls,
        max_helius_credits=args.max_helius_credits,
        max_dexscreener_calls=args.max_dexscreener_calls,
        max_active_watches=args.max_active_watches,
        metadata_refresh_interval_seconds=args.metadata_refresh_interval_seconds,
        holder_refresh_interval_seconds=args.holder_refresh_interval_seconds,
        max_observe_iterations=args.max_observe_iterations,
        source=args.source,
        local_source_path=args.local_source_path,
        perform_live_health_checks=args.live_health_check,
    )
    if args.mode == "dry-run":
        report = run_dry_run(config)
        print("## Forward Efficient Mover Observer Dry Run")
        print(f"readiness_classification={report['readiness_classification']}")
        print(f"observation_readiness={report['observation_readiness']}")
        print(f"observation_root={report['observation_root']}")
        print(f"report_root={report['report_root']}")
        print(f"target_candidates={report['target_candidates']}")
        print(f"source_availability={report['source_availability']}")
        return 0
    if args.mode == "status":
        tally = run_status(config)
        print(print_status(tally))
        return 0
    if args.mode == "probe":
        report = run_live_program_probe(
            config,
            source=args.source,
            limit=args.probe_limit,
            hydrate_sample=args.hydrate_sample,
        )
        print("## Forward Efficient Mover Live Program Probe")
        print(f"source={report.get('source')}")
        print(f"readiness_classification={report.get('readiness_classification')}")
        print(f"signatures_seen={report.get('signatures_seen', 0)}")
        print(f"transactions_hydrated={report.get('transactions_hydrated', 0)}")
        print(f"program_instruction_count={report.get('program_instruction_count', 0)}")
        print(f"parseable_event_count={report.get('parseable_event_count', 0)}")
        print(f"candidate_rows_created={report.get('candidate_rows_created', 0)}")
        print(f"network_calls_made={report.get('network_calls_made', 0)}")
        print(f"warnings={report.get('warnings', [])}")
        print(f"report_root={config.report_root}")
        return 0
    if args.mode == "observe":
        source = None
        if args.source == "mock":
            source = MockCandidateSource([json.loads(args.mock_candidate_json)] if args.mock_candidate_json else None)
        result = run_observe(config, source=source)
        print("## Forward Efficient Mover Observation Loop")
        print(f"total_candidates={result.get('total_candidates_observed', 0)}")
        print(f"active={result.get('active_candidates_currently_watched', 0)}")
        print(f"completed={result.get('completed_candidates', 0)}")
        print(f"latest_candidate={result.get('latest_observed_candidate')}")
        print(f"reached_100k={result.get('candidates_that_reached_100k', 0)}")
        print(f"reached_500k={result.get('candidates_that_reached_500k', 0)}")
        print(f"reached_1m={result.get('candidates_that_reached_1m', 0)}")
        print(f"drawdown_recovery_count={result.get('candidates_with_recoveries_after_30pct_drawdown', 0)}")
        print(f"warnings={result.get('warnings', [])}")
        print(f"output_path={result.get('output_path')}")
        return 0
    raise ValueError(f"unsupported mode: {args.mode}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Forward efficient-mover observation logger.")
    parser.add_argument("--mode", choices=["dry-run", "observe", "status", "probe"], default="dry-run")
    parser.add_argument("--data-root", default=None)
    parser.add_argument(
        "--source",
        choices=["auto", "mock", "local", "helius", "helius-pumpfun", "helius-pumpswap", "helius-raydium", "helius-all"],
        default="auto",
    )
    parser.add_argument("--local-source-path", default=None)
    parser.add_argument("--mock-candidate-json", default=None)
    parser.add_argument("--target-candidates", type=int, default=300)
    parser.add_argument("--start-trigger", type=float, default=10_000)
    parser.add_argument("--poll-seconds", type=float, default=2)
    parser.add_argument("--status-interval-seconds", type=int, default=30)
    parser.add_argument("--max-runtime-minutes", type=int, default=240)
    parser.add_argument("--max-api-calls", type=int, default=100_000)
    parser.add_argument("--max-helius-credits", type=int, default=250_000)
    parser.add_argument("--max-dexscreener-calls", type=int, default=10_000)
    parser.add_argument("--max-active-watches", type=int, default=50)
    parser.add_argument("--metadata-refresh-interval-seconds", type=int, default=60)
    parser.add_argument("--holder-refresh-interval-seconds", type=int, default=30)
    parser.add_argument("--max-observe-iterations", type=int, default=None)
    parser.add_argument("--probe-limit", type=int, default=10)
    parser.add_argument("--hydrate-sample", action="store_true")
    parser.add_argument("--live-health-check", action="store_true")
    parser.add_argument("--enable-dexscreener-metadata", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Compatibility flag; use --mode dry-run for dry-run behavior.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
