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
from research.mtp_research.validation.official_lifecycle_watch import (
    OFFICIAL_SAMPLE_LABEL,
    OFFICIAL_V2_SAMPLE_LABEL,
    OfficialLifecycleConfig,
    OfficialLifecycleV2Config,
    initialize_official_lifecycle_namespace,
    official_lifecycle_status,
    run_official_lifecycle_live_smoke,
    run_official_lifecycle_smoke,
)
from research.mtp_research.validation.no_laserstream_lifecycle_collector import (
    extended_no_laserstream_status,
    format_no_laserstream_status,
    run_no_laserstream_lifecycle_smoke,
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
        enable_probed_adapters=args.enable_probed_adapters,
        enable_birth_watch_candidates=args.enable_birth_watch_candidates,
        birth_scan_max_batches=args.birth_scan_max_batches,
        birth_scan_signatures_per_batch=args.birth_scan_signatures_per_batch,
        birth_scan_hydrate_limit_per_batch=args.birth_scan_hydrate_limit_per_batch,
        birth_scan_target_create_candidates=args.birth_scan_target_create_candidates,
        birth_scan_max_signatures_total=args.birth_scan_max_signatures_total,
        birth_scan_min_confidence=args.birth_scan_min_confidence,
        birth_scan_cursor_before=args.birth_scan_cursor_before,
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
        if args.sample in {OFFICIAL_SAMPLE_LABEL, OFFICIAL_V2_SAMPLE_LABEL}:
            lifecycle_config = _official_config(args)
            initialize_official_lifecycle_namespace(lifecycle_config)
            has_no_laserstream_rows = (
                lifecycle_config.provisional_births_path.exists()
                and lifecycle_config.provisional_births_path.read_text(encoding="utf-8").strip() != ""
            )
            if args.source == "helius-pumpfun-no-laserstream" or has_no_laserstream_rows:
                status = extended_no_laserstream_status(lifecycle_config, target_crossed_20k=args.target_crossed_20k)
                print(format_no_laserstream_status(status))
            else:
                from research.mtp_research.validation.official_lifecycle_watch import format_official_lifecycle_status

                status = official_lifecycle_status(lifecycle_config, target_crossed_20k=args.target_crossed_20k)
                print(format_official_lifecycle_status(status))
            return 0
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
    if args.mode == "observe-lifecycle":
        if args.sample not in {OFFICIAL_SAMPLE_LABEL, OFFICIAL_V2_SAMPLE_LABEL}:
            raise ValueError("observe-lifecycle requires --sample official_lifecycle_watch_v1 or official_lifecycle_watch_v2")
        lifecycle_config = _official_config(args)
        if args.source == "helius-pumpfun-no-laserstream":
            result = run_no_laserstream_lifecycle_smoke(
                lifecycle_config,
                target_births=args.target_births,
                target_crossed_20k=args.target_crossed_20k,
                max_runtime_minutes=args.max_runtime_minutes,
                signatures_per_mint=args.signatures_per_mint,
                transactions_per_mint=args.transactions_per_mint,
                execute=args.execute,
            )
        elif args.source != "mock":
            result = run_official_lifecycle_live_smoke(
                lifecycle_config,
                target_births=args.target_births,
                target_crossed_20k=args.target_crossed_20k,
                max_runtime_minutes=args.max_runtime_minutes,
                signatures_per_mint=args.signatures_per_mint,
                transactions_per_mint=args.transactions_per_mint,
                execute=args.execute,
            )
        else:
            result = run_official_lifecycle_smoke(
                lifecycle_config,
                target_births=args.target_births,
                target_crossed_20k=args.target_crossed_20k,
                execute=args.execute,
            )
        version = "v2" if args.sample == OFFICIAL_V2_SAMPLE_LABEL else "v1"
        print(f"## Official Lifecycle Watch {version} Smoke")
        print(f"execute={result.get('execute')}")
        print(f"smoke_births_observed={result.get('smoke_births_observed', 0)}")
        print(f"under_5s_followup_count={result.get('under_5s_followup_count', 0)}")
        print(f"active_watches_created={result.get('active_watches_created', 0)}")
        print(f"matured_counts={result.get('matured_counts', {})}")
        print(f"estimated_helius_credits_used={result.get('estimated_helius_credits_used', 0)}")
        print(f"network_calls_made={result.get('network_calls_made', 0)}")
        print(f"quality_status={result.get('quality_audit_result', {}).get('quality_status')}")
        print(f"readiness_classification={result.get('readiness_classification')}")
        print(f"warnings={result.get('warnings', [])}")
        print(f"lifecycle_state_file={result.get('lifecycle_state_file', lifecycle_config.state_path)}")
        print(f"report_root={lifecycle_config.report_root}")
        return 0
    if args.mode == "observe-births-with-immediate-followup":
        from research.mtp_research.validation.forward_birth_watch_followup_collector import (
            run_immediate_birth_followup_observation,
        )

        result = run_immediate_birth_followup_observation(
            args.data_root or "/Volumes/ORICO/MemeTraderPro",
            target_births=args.target_births,
            followup_duration_seconds=args.followup_duration_seconds,
            first_pass_delay_seconds=args.first_pass_delay_seconds,
            followup_poll_seconds=args.followup_poll_seconds,
            max_followup_passes_per_mint=args.max_followup_passes_per_mint,
            max_active_birth_followups=args.max_active_birth_followups,
            max_runtime_minutes=args.max_runtime_minutes,
            max_helius_credits=args.max_helius_credits,
            birth_candidate_source_method=args.birth_candidate_source_method,
            birth_scan_max_batches=args.birth_scan_max_batches,
            birth_scan_signatures_per_batch=args.birth_scan_signatures_per_batch,
            birth_scan_hydrate_limit_per_batch=args.birth_scan_hydrate_limit_per_batch,
            birth_scan_max_signatures_total=args.birth_scan_max_signatures_total,
            birth_scan_min_confidence=args.birth_scan_min_confidence,
            birth_scan_cursor_before=args.birth_scan_cursor_before,
            signatures_per_mint=args.signatures_per_mint,
            transactions_per_mint=args.transactions_per_mint,
            execute=args.execute,
        )
        print("## Forward Birth Watch Immediate Follow-up")
        print(f"execute={result.get('execute')}")
        print(f"smoke_birth_count={result.get('smoke_birth_count', 0)}")
        print(f"immediate_followup_started_count={result.get('immediate_followup_started_count', 0)}")
        print(f"first_followup_path_rows={result.get('first_followup_path_rows', 0)}")
        print(f"first_followup_before_10k_count={result.get('first_followup_before_10k_count', 0)}")
        print(f"first_followup_before_20k_count={result.get('first_followup_before_20k_count', 0)}")
        print(f"true_near_birth_observed_count={result.get('true_near_birth_observed_count', 0)}")
        print(f"crossed_10k_count={result.get('crossed_10k_count', 0)}")
        print(f"crossed_20k_count={result.get('crossed_20k_count', 0)}")
        print(f"median_seconds_create_to_first_followup_attempt={result.get('median_seconds_create_to_first_followup_attempt')}")
        print(f"median_seconds_create_to_first_path={result.get('median_seconds_create_to_first_path')}")
        print(f"network_calls_made={result.get('network_calls_made', 0)}")
        print(f"estimated_helius_credits_used={result.get('estimated_helius_credits_used', 0)}")
        print(f"readiness_classification={result.get('readiness_classification')}")
        print(f"warnings={result.get('warnings', [])}")
        print(f"output_files={result.get('output_files', {})}")
        return 0
    raise ValueError(f"unsupported mode: {args.mode}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Forward efficient-mover observation logger.")
    parser.add_argument(
        "--mode",
        choices=["dry-run", "observe", "status", "probe", "observe-births-with-immediate-followup", "observe-lifecycle"],
        default="dry-run",
    )
    parser.add_argument("--sample", choices=["efficient_movers", OFFICIAL_SAMPLE_LABEL, OFFICIAL_V2_SAMPLE_LABEL], default="efficient_movers")
    parser.add_argument("--data-root", default=None)
    parser.add_argument(
        "--source",
        choices=[
            "auto",
            "mock",
            "local",
            "helius",
            "helius-pumpfun",
            "helius-pumpfun-no-laserstream",
            "helius-pumpfun-create-scanner",
            "helius-pumpswap",
            "helius-raydium",
            "helius-all",
        ],
        default="auto",
    )
    parser.add_argument("--local-source-path", default=None)
    parser.add_argument("--mock-candidate-json", default=None)
    parser.add_argument("--target-candidates", type=int, default=300)
    parser.add_argument("--target-crossed-20k", type=int, default=300)
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
    parser.add_argument("--enable-probed-adapters", action="store_true")
    parser.add_argument("--enable-birth-watch-candidates", action="store_true")
    parser.add_argument("--birth-scan-max-batches", type=int, default=20)
    parser.add_argument("--birth-scan-signatures-per-batch", type=int, default=50)
    parser.add_argument("--birth-scan-hydrate-limit-per-batch", type=int, default=50)
    parser.add_argument("--birth-scan-target-create-candidates", type=int, default=10)
    parser.add_argument("--birth-scan-max-signatures-total", type=int, default=1_000)
    parser.add_argument("--birth-scan-min-confidence", choices=["low", "medium", "high"], default="medium")
    parser.add_argument("--birth-scan-cursor-before", default=None)
    parser.add_argument("--target-births", type=int, default=25)
    parser.add_argument("--birth-candidate-source-method", choices=["websocket_logs", "signature_scan"], default="websocket_logs")
    parser.add_argument("--followup-duration-seconds", type=int, default=120)
    parser.add_argument("--first-pass-delay-seconds", type=float, default=0.0)
    parser.add_argument("--followup-poll-seconds", type=float, default=2.0)
    parser.add_argument("--max-followup-passes-per-mint", type=int, default=60)
    parser.add_argument("--max-active-birth-followups", type=int, default=100)
    parser.add_argument("--signatures-per-mint", type=int, default=10)
    parser.add_argument("--transactions-per-mint", type=int, default=10)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--live-health-check", action="store_true")
    parser.add_argument("--enable-dexscreener-metadata", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Compatibility flag; use --mode dry-run for dry-run behavior.")
    return parser.parse_args()


def _official_config(args: argparse.Namespace) -> OfficialLifecycleConfig:
    config_cls = OfficialLifecycleV2Config if args.sample == OFFICIAL_V2_SAMPLE_LABEL else OfficialLifecycleConfig
    return config_cls(
        data_root=Path(args.data_root).expanduser() if args.data_root else None,
        followup_poll_seconds=float(args.followup_poll_seconds),
        trigger_qualified_followup_poll_seconds=float(args.followup_poll_seconds),
        max_active_birth_followups=args.max_active_birth_followups,
        max_active_trigger_watches=args.target_crossed_20k,
        max_observation_age_minutes=args.max_runtime_minutes,
        max_helius_credits_per_run=args.max_helius_credits,
        global_observation_credit_cap=args.max_helius_credits,
        target_crossed_20k=args.target_crossed_20k,
    )


if __name__ == "__main__":
    raise SystemExit(main())
