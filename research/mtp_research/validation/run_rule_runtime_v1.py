"""CLI for Rule Runtime v1 paper-only observation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research.mtp_research.validation.rule_runtime_v1 import (
    FROZEN_BUY_RULE_ID,
    FROZEN_EXIT_RULE_ID,
    RuleRuntimeConfig,
    RuleRuntimeLiveAdapterConfig,
    birth_coverage_audit,
    bonding_curve_resolution_audit,
    first_fdv_queue_triage_audit,
    initialize_rule_runtime,
    paper_buy_fdv_reconciliation_audit,
    run_rule_runtime_safety_patch_review,
    rule_runtime_status,
    run_helius_transaction_subscribe_bonding_curve_probe_smoke,
    run_first_fdv_queue_triage_smoke,
    run_rule_runtime_live_bus_collector_smoke,
    run_rule_runtime_mock_live_bus_smoke,
    run_rule_runtime_live_adapter_once,
    run_rule_runtime_once,
    run_rule_runtime_smoke,
)
from research.mtp_research.validation.helius_transaction_subscribe_source import helius_transaction_subscribe_capability_audit


def main() -> int:
    args = parse_args()
    config = RuleRuntimeConfig(
        data_root=Path(args.data_root).expanduser() if args.data_root else None,
        starting_wallet_usd=args.starting_wallet_usd,
        position_fraction=args.position_fraction,
    )
    if args.mode == "init":
        result = initialize_rule_runtime(config, reset=args.reset)
        print("## Rule Runtime v1 Initialized")
        print(f"Runtime namespace: {result['runtime_root']}")
        print("Live trading enabled: false")
        print("Paper trading enabled: true")
        print(f"Monitor path: {result['monitor_html_path']}")
        return 0
    if args.mode == "once":
        if args.source_followup_path:
            result = run_rule_runtime_live_adapter_once(
                config,
                adapter_config=RuleRuntimeLiveAdapterConfig(
                    data_root=config.root,
                    source_sample_label=args.source_sample_label,
                    source_followup_paths_path=Path(args.source_followup_path).expanduser(),
                ),
                limit=args.max_events,
            )
            print("## Rule Runtime v1 Live Adapter Update")
            print(f"events_processed={result['events_processed']}")
            print(f"paper_buys={result['paper_buys']}")
            print(f"paper_sells={result['paper_sells']}")
            print(f"confirmed_10k_watches={result['confirmed_10k_watches']}")
            print(f"confirmed_20k_entry_candidates={result['confirmed_20k_entry_candidates']}")
            return 0
        events = []
        if args.event_json:
            events.append(json.loads(args.event_json))
        result = run_rule_runtime_once(config, events=events)
        print("## Rule Runtime v1 Update")
        print(f"processed_events={result['processed_events']}")
        print(f"paper_buys_created={result['paper_buys_created']}")
        print(f"paper_sells_created={result['paper_sells_created']}")
        print(f"confirmed_10k_watches={result['confirmed_10k_watches']}")
        print(f"confirmed_20k_entry_candidates={result['confirmed_20k_entry_candidates']}")
        return 0
    if args.mode in {"smoke", "smoke-file-adapter", "replay-file"}:
        if args.reset:
            initialize_rule_runtime(config, reset=True)
        result = run_rule_runtime_smoke(
            config,
            adapter_config=RuleRuntimeLiveAdapterConfig(
                data_root=config.root,
                source_sample_label=args.source_sample_label,
                source_followup_paths_path=Path(args.source_followup_path).expanduser() if args.source_followup_path else None,
            ),
            max_events=args.max_events,
            max_seconds=args.max_seconds,
            target_confirmed_10k_watches=args.target_confirmed_10k_watches,
            target_confirmed_20k_candidates=args.target_confirmed_20k_candidates,
        )
        print("## Rule Runtime v1 Smoke")
        print(f"events_processed={result['events_processed']}")
        print(f"confirmed_10k_watches={result['confirmed_10k_watches']}")
        print(f"confirmed_20k_candidates={result['confirmed_20k_candidates']}")
        print(f"paper_buys={result['paper_buys']}")
        print(f"paper_sells={result['paper_sells']}")
        print(f"variant_a_buys_sells={result.get('variant_a_paper_buys')}/{result.get('variant_a_paper_sells')}")
        print(
            "variant_b_buys_sells_not_evaluable="
            f"{result.get('variant_b_paper_buys')}/{result.get('variant_b_paper_sells')}/{result.get('variant_b_not_evaluable')}"
        )
        print(
            "variant_c_buys_sells_not_evaluable="
            f"{result.get('variant_c_paper_buys')}/{result.get('variant_c_paper_sells')}/{result.get('variant_c_not_evaluable')}"
        )
        print(f"threshold_status={result['threshold_status']}")
        print(f"monitor_path={result['monitor_path']}")
        return 0
    if args.mode == "smoke-live-bus":
        if args.reset:
            initialize_rule_runtime(config, reset=True)
        if args.mock_live_bus_events:
            events = _read_jsonl(Path(args.mock_live_bus_events).expanduser())
            result = run_rule_runtime_mock_live_bus_smoke(config, events)
        else:
            collector_root = Path(args.collector_data_root).expanduser() if args.collector_data_root else (
                config.runtime_root / "live_collector_roots" / "latest_live_bus_smoke"
            )
            result = run_rule_runtime_live_bus_collector_smoke(
                config,
                collector_data_root=collector_root,
                target_births=args.target_births,
                target_crossed_20k=args.target_crossed_20k,
                max_runtime_seconds=args.max_seconds,
                max_helius_credits=args.max_helius_credits,
                signatures_per_mint=args.signatures_per_mint,
                transactions_per_mint=args.transactions_per_mint,
            )
        print("## Rule Runtime v1 Live Bus Smoke")
        print(f"runtime_mode={result['runtime_mode']}")
        print(f"events_processed={result['events_processed']}")
        print(f"live_bus_events={result['live_bus_events']}")
        print(f"file_adapter_events={result['file_adapter_events']}")
        print(f"confirmed_10k_watches={result['confirmed_10k_watches']}")
        print(f"confirmed_20k_candidates={result['confirmed_20k_candidates']}")
        print(f"paper_buys={result['paper_buys']}")
        print(f"paper_sells={result['paper_sells']}")
        print(f"variant_a_buys_sells={result.get('variant_a_paper_buys')}/{result.get('variant_a_paper_sells')}")
        print(
            "variant_b_buys_sells_not_evaluable="
            f"{result.get('variant_b_paper_buys')}/{result.get('variant_b_paper_sells')}/{result.get('variant_b_not_evaluable')}"
        )
        print(
            "variant_c_buys_sells_not_evaluable="
            f"{result.get('variant_c_paper_buys')}/{result.get('variant_c_paper_sells')}/{result.get('variant_c_not_evaluable')}"
        )
        print(f"event_to_rule_latency={result['event_to_rule_latency_p50_p90_p99']}")
        print(f"bus_to_runtime_latency={result['bus_to_runtime_latency_p50_p90_p99']}")
        print(f"runtime_eval_latency={result['runtime_eval_latency_p50_p90_p99']}")
        print(f"monitor_path={result['monitor_path']}")
        return 0
    if args.mode == "triage-audit":
        result = first_fdv_queue_triage_audit(config)
        print("## First FDV Queue Triage Audit")
        print(f"scheduler_mode={result['scheduler_mode']}")
        print(f"parallel_workers_added={result['parallel_workers_added']}")
        print(f"queue_entries_created_from={result['queue_entries_created_from']}")
        print(f"report_path={config.first_fdv_queue_triage_audit_json_path}")
        return 0
    if args.mode == "triage-smoke":
        if args.reset:
            initialize_rule_runtime(config, reset=True)
        result = run_first_fdv_queue_triage_smoke(config, events=_read_jsonl(Path(args.mock_live_bus_events).expanduser()) if args.mock_live_bus_events else [])
        queue = result.get("first_fdv_queue") or {}
        print("## First FDV Queue Triage Smoke")
        print(f"runtime_mode={result['runtime_mode']}")
        print(f"scheduler_mode={result['scheduler_mode']}")
        print(f"parallel_workers_added={result['parallel_workers_added']}")
        print(f"events_processed={result['events_processed']}")
        print(f"queue_depth_by_tier={queue.get('queue_depth_by_tier')}")
        print(f"archived_no_activity={queue.get('archived_no_activity')}")
        print(f"archived_no_fdv_path_timeout={queue.get('archived_no_fdv_path_timeout')}")
        print(f"promotions={queue.get('promoted_to_fdv_path')}/{queue.get('promoted_to_near_threshold')}/{queue.get('promoted_to_confirmed_10k')}/{queue.get('promoted_to_paper_position')}")
        print(f"first_path_latency={queue.get('first_path_latency_p50_p90_p99')}")
        print(f"monitor_path={result['monitor_path']}")
        return 0
    if args.mode == "birth-coverage-audit":
        result = birth_coverage_audit(
            config,
            source_root=Path(args.collector_data_root).expanduser() if args.collector_data_root else None,
        )
        print("## Birth Coverage Audit")
        print(f"provisional_birth_logs={result['provisional_birth_logs']}")
        print(f"confirmed_create_parses={result['confirmed_create_parses']}")
        print(f"fresh_accepted_births={result['fresh_accepted_births']}")
        print(f"stale_quarantined_births={result['stale_quarantined_births']}")
        print(f"parser_failures={result['parser_failures']}")
        print(f"hydration_failures={result['hydration_failures']}")
        print(f"duplicate_births={result['duplicate_births']}")
        print(f"unrecognized_layouts={result['unrecognized_layouts']}")
        print(f"accepted_birth_rate={result['accepted_birth_rate']}")
        print(f"rejected_stale_rate={result['rejected_stale_rate']}")
        print(f"report_path={config.birth_coverage_audit_json_path}")
        return 0
    if args.mode == "paper-buy-fdv-audit":
        result = paper_buy_fdv_reconciliation_audit(config)
        summary = result.get("summary") or {}
        print("## Paper Buy FDV Reconciliation Audit")
        print(f"paper_buys_checked={summary.get('paper_buys_checked')}")
        print(f"manual_axiom_mismatch_count={summary.get('manual_axiom_mismatch_count')}")
        print(f"duplicate_confirmation_count={summary.get('duplicate_confirmation_count')}")
        print(f"same_slot_or_signature_confirmation_count={summary.get('same_slot_or_signature_confirmation_count')}")
        print(f"rugged_count={summary.get('rugged_count')}")
        print(f"report_path={config.paper_buy_fdv_reconciliation_audit_json_path}")
        print(f"rows_path={config.paper_buy_fdv_reconciliation_rows_csv_path}")
        return 0
    if args.mode == "runtime-safety-patch-review":
        result = run_rule_runtime_safety_patch_review(config, apply_voids=not args.no_apply_voids)
        retro = result.get("retroactive_review") or {}
        print("## Rule Runtime v1 Safety Patch Review")
        print(f"duplicate_confirmation_patch={result.get('duplicate_confirmation_patch')}")
        print(f"max_entry_above_trigger_pct={(result.get('chase_guard_threshold') or {}).get('max_entry_above_trigger_pct')}")
        print(f"valid_paper_buys={retro.get('valid_paper_buys')}")
        print(f"voided_paper_buys={retro.get('voided_paper_buys')}")
        print(f"paper_wallet_cash_after_voids={retro.get('paper_wallet_cash_after_voids')}")
        print(f"report_path={config.runtime_safety_patch_summary_json_path}")
        print(f"retroactive_review_path={config.retroactive_paper_buy_safety_review_json_path}")
        return 0
    if args.mode == "bonding-curve-resolution-audit":
        result = bonding_curve_resolution_audit(
            config,
            source_root=Path(args.collector_data_root).expanduser() if args.collector_data_root else None,
        )
        print("## Bonding Curve Resolution Audit")
        print(f"pumpfun_create_rows={result['pumpfun_create_rows']}")
        print(f"mint_available={result['mint_available']}")
        print(f"bonding_curve_available={result['bonding_curve_available']}")
        print(f"associated_bonding_curve_available={result['associated_bonding_curve_available']}")
        print(f"creator_available={result['creator_available']}")
        print(f"bonding_curve_pda_derivable={result['bonding_curve_pda_derivable']}")
        print(f"bonding_curve_pda_matches_known={result['bonding_curve_pda_matches_known']}")
        print(f"path_rows_with_curve_or_pool_fields={result['path_rows_with_curve_or_pool_fields']}")
        print(f"report_path={config.bonding_curve_resolution_audit_json_path}")
        return 0
    if args.mode == "transaction-subscribe-capability-audit":
        result = helius_transaction_subscribe_capability_audit(config)
        recommended = result.get("recommended_endpoint") or {}
        print("## Helius transactionSubscribe Capability Audit")
        print(f"recommended_endpoint={recommended.get('name')}")
        for row in result.get("endpoints") or []:
            print(
                f"endpoint={row.get('name')} transactionSubscribe={row.get('transactionSubscribe_supported')} "
                f"accountSubscribe={row.get('accountSubscribe_supported')} getAccountInfo={row.get('getAccountInfo_processed_supported')}"
            )
        print(f"report_path={config.helius_transaction_subscribe_capability_audit_json_path}")
        return 0
    if args.mode == "transaction-subscribe-smoke":
        if args.reset:
            initialize_rule_runtime(config, reset=True)
        collector_root = Path(args.collector_data_root).expanduser() if args.collector_data_root else (
            config.runtime_root / "live_collector_roots" / "latest_transaction_subscribe_smoke"
        )
        result = run_helius_transaction_subscribe_bonding_curve_probe_smoke(
            config,
            collector_data_root=collector_root,
            target_births=args.target_births,
            target_crossed_20k=args.target_crossed_20k,
            max_runtime_seconds=args.max_seconds,
            max_helius_credits=args.max_helius_credits,
            signatures_per_mint=args.signatures_per_mint,
            transactions_per_mint=args.transactions_per_mint,
        )
        print("## Helius transactionSubscribe Bonding-Curve Probe Smoke")
        print(f"transactionSubscribe_supported={result['transactionSubscribe_supported']}")
        print(f"transactionSubscribe_used={result['transactionSubscribe_used']}")
        print(f"endpoint_used={result.get('endpoint_used')}")
        print(f"decoded_create_events={result['decoded_create_events']}")
        print(
            "decoded_create_probe_coverage="
            f"{result.get('decoded_create_mints_with_probe')}/{result.get('decoded_create_unique_mints')} "
            f"rate={result.get('decoded_create_probe_coverage_rate')} "
            f"missing={result.get('decoded_create_mints_without_probe')}"
        )
        print(f"accepted_births={result['accepted_births']}")
        print(f"bonding_curve_probes={result['bonding_curve_probes_started']}/{result['bonding_curve_probes_succeeded']}/{result['bonding_curve_probes_failed']}")
        print(f"probes_started_during_stream={result['probes_started_during_stream']}")
        print(
            "confirmation_followups="
            f"{result.get('confirmation_follow_up_futures')}/"
            f"{result.get('confirmation_follow_up_probe_rows')}/"
            f"{result.get('confirmation_follow_up_successes')}"
        )
        print(f"first_attempt_successes={result['first_attempt_successes']}")
        print(f"account_not_found_retries={result['account_not_found_retries']}")
        print(f"account_not_found_recovered_by_retry={result['account_not_found_recovered_by_retry']}")
        print(f"account_not_found_final_failures={result['account_not_found_final_failures']}")
        print(f"account_not_found_retry_recovery_rate={result['account_not_found_retry_recovery_rate']}")
        print(f"observed_to_probe_started={result['observed_to_probe_started_p50_p90_p99']}")
        print(f"probe_started_to_first_curve_state={result['probe_started_to_first_curve_state_p50_p90_p99']}")
        print(f"observed_to_first_fdv={result['observed_to_first_fdv_p50_p90_p99']}")
        print(f"first_fdv_source_mix={result['first_fdv_source_mix']}")
        print(f"observed_to_first_fdv_account_state={result['observed_to_first_fdv_account_state_p50_p90_p99']}")
        print(f"first_path_latency={result['first_path_latency_p50_p90_p99']}")
        print(f"queue_total={result['first_fdv_queue_total']}")
        print(f"tier_1_depth={result['tier_1_depth']}")
        print(f"confirmed_10k_watches={result['confirmed_10k_watches']}")
        print(f"confirmed_20k_candidates={result['confirmed_20k_candidates']}")
        print(f"paper_buys={result['paper_buys']}")
        print(f"paper_sells={result['paper_sells']}")
        print(f"http_429={result['http_429']}")
        print(f"monitor_path={result['monitor_path']}")
        return 0
    print_status(rule_runtime_status(config))
    return 0


def print_status(status: dict) -> None:
    print("## Rule Runtime v1 Status")
    print(f"Runtime mode: {status['runtime_mode']}")
    print(f"Frozen buy rule: {FROZEN_BUY_RULE_ID}")
    print(f"Frozen exit rule: {FROZEN_EXIT_RULE_ID}")
    print("Live trading enabled: false")
    print("Paper trading enabled: true")
    print(f"Events processed: {status['events_processed']}")
    print(f"Live bus events: {status['live_bus_events']}")
    print(f"File adapter events: {status['file_adapter_events']}")
    print(f"Confirmed 10k watches: {status['confirmed_10k_watches']}")
    print(f"Confirmed 20k entry candidates: {status['confirmed_20k_entry_candidates']}")
    print(f"Paper buys: {status['paper_buys']}")
    print(f"Open paper positions: {status['open_paper_positions']}")
    print(f"Paper sells: {status['paper_sells']}")
    print("## Rule Runtime v1 Variants")
    for variant_id, row in (status.get("variants") or {}).items():
        print(
            f"{variant_id}: buys={row.get('paper_buys')} sells={row.get('paper_sells')} "
            f"open={row.get('open_positions')} rejected={row.get('rejected')} "
            f"not_evaluable={row.get('not_evaluable')} missing_fields={row.get('missing_fields')}"
        )
    print(f"Rejected spike candidates: {status['rejected_spike_candidates']}")
    print(f"Rejected same-timestamp jumps: {status['rejected_same_timestamp_jumps']}")
    print(f"Rejected FDV anomalies: {status['rejected_fdv_anomalies']}")
    print(f"Archived no-activity: {status['archived_no_activity']}")
    print(f"Latency p50/p90/p99: {status['latency_p50_p90_p99']}")
    print(f"Latency event_to_rule p50/p90/p99: {status['event_to_rule_p50_p90_p99']}")
    print(f"Latency bus_to_runtime p50/p90/p99: {status['bus_to_runtime_p50_p90_p99']}")
    print(f"Latency runtime_eval p50/p90/p99: {status['runtime_eval_p50_p90_p99']}")
    print(f"State age p50/p90/p99: {status['state_age_p50_p90_p99']}")
    print(f"Bus queue depth: {status['bus_queue_depth']}")
    print(f"Queue sizes: {status['queue_sizes']}")
    queue = status.get("first_fdv_queue") or {}
    print("## First FDV Queue")
    print(f"Scheduler mode: {queue.get('scheduler_mode')}")
    print(f"Queue depth total: {queue.get('queue_depth_total')}")
    print(f"Queue depth by tier: {queue.get('queue_depth_by_tier')}")
    print(f"Oldest queued age by tier: {queue.get('oldest_queued_age_seconds_by_tier')}")
    print(f"Average queued age by tier: {queue.get('average_queued_age_seconds_by_tier')}")
    print(f"Tier 1 depth: {queue.get('tier_1_depth')}")
    print(f"Tier 1 oldest age: {queue.get('tier_1_oldest_age_seconds')}")
    print(f"Tier 1 p50/p90 age: {queue.get('tier_1_age_p50_p90')}")
    print(f"Tier 1 processed count: {queue.get('tier_1_processed_count')}")
    print(f"Tier 1 archive count: {queue.get('tier_1_archive_count')}")
    print(f"Tier 1 promotion count: {queue.get('tier_1_promotion_count')}")
    print(f"Tier 1 retry count: {queue.get('tier_1_retry_count')}")
    print(f"Tier 1 pressure mode: {queue.get('tier_1_pressure_mode')}")
    print(f"Archived no activity: {queue.get('archived_no_activity')}")
    print(f"Archived no FDV path timeout: {queue.get('archived_no_fdv_path_timeout')}")
    print(f"Archived parser failure: {queue.get('archived_parser_failure')}")
    print(f"Archived duplicate: {queue.get('archived_duplicate')}")
    print(f"Archived provenance failure: {queue.get('archived_provenance_failure')}")
    print(f"Promoted to FDV path: {queue.get('promoted_to_fdv_path')}")
    print(f"Promoted to near-threshold: {queue.get('promoted_to_near_threshold')}")
    print(f"Promoted to confirmed 10k: {queue.get('promoted_to_confirmed_10k')}")
    print(f"Promoted to paper position: {queue.get('promoted_to_paper_position')}")
    print(f"First path success rate: {queue.get('first_path_success_rate')}")
    print(f"First-FDV success rate: {queue.get('first_fdv_success_rate')}")
    print(f"First-FDV timeout rate: {queue.get('first_fdv_timeout_rate')}")
    print(f"First-FDV median latency: {queue.get('first_fdv_median_latency_ms')}")
    print(f"First path latency p50/p90/p99: {queue.get('first_path_latency_p50_p90_p99')}")
    print(f"Downgrade count: {queue.get('downgrade_count')}")
    print(f"Reactivation count: {queue.get('reactivation_count')}")
    print(f"HTTP 429 count: {queue.get('http_429_count')}")
    sources = status.get("first_fdv_probe_sources") or {}
    print("## First-FDV Probe Sources")
    print(f"Bonding curve account-state successes: {sources.get('bonding_curve_account_state_successes')}")
    print(f"Bonding curve account-state failures: {sources.get('bonding_curve_account_state_failures')}")
    print(f"Transaction delta successes: {sources.get('transaction_delta_successes')}")
    print(f"Confirmed path-state successes: {sources.get('confirmed_path_state_successes')}")
    print(f"Unknown successes: {sources.get('unknown_successes')}")
    print(f"Source mix: {sources.get('source_mix')}")
    print(f"getAccountInfo p50/p90/p99: {sources.get('getAccountInfo_p50_p90_p99')}")
    print(f"Decode p50/p90/p99: {sources.get('decode_p50_p90_p99')}")
    print(f"Observed to account-state FDV p50/p90/p99: {sources.get('observed_to_first_fdv_account_state_p50_p90_p99')}")
    print(f"accountSubscribe status: {sources.get('accountSubscribe_bonding_curve_status')}")
    print(f"Active account subscriptions: {sources.get('active_account_subscriptions')}")
    txsub = status.get("helius_transaction_subscribe_first_fdv") or {}
    print("## Helius transactionSubscribe First-FDV")
    print(f"transactionSubscribe supported: {txsub.get('transactionSubscribe_supported')}")
    print(f"endpoint used: {txsub.get('endpoint_used')}")
    print(f"create events decoded: {txsub.get('create_events_decoded')}")
    print(f"curve PDA verified: {txsub.get('curve_pda_verified')}")
    print(f"curve account probes started: {txsub.get('curve_account_probes_started')}")
    print(f"curve account probes succeeded: {txsub.get('curve_account_probes_succeeded')}")
    print(f"curve account probes failed: {txsub.get('curve_account_probes_failed')}")
    print(f"first FDV from bonding_curve_account_state: {txsub.get('first_fdv_from_bonding_curve_account_state')}")
    print(f"first FDV from transaction_delta: {txsub.get('first_fdv_from_transaction_delta')}")
    print(f"first FDV from unknown: {txsub.get('first_fdv_from_unknown')}")
    print(f"getAccountInfo p50/p90/p99: {txsub.get('getAccountInfo_p50_p90_p99')}")
    print(f"accountSubscribe p50/p90/p99: {txsub.get('accountSubscribe_p50_p90_p99')}")
    print(f"decode failures: {txsub.get('decode_failures')}")
    print(f"probe failures by reason: {txsub.get('probe_failures_by_reason')}")
    print(f"HTTP 429: {txsub.get('http_429')}")
    print(f"warnings: {txsub.get('warnings')}")
    print("Metadata hot path blocked: true")
    print("No real trade flag: true")
    print(f"Monitor path: {status['monitor_html_path']}")
    print(f"Paper trades path: {status['paper_trades_path']}")
    print(f"Latency events path: {status['latency_events_path']}")
    warnings = status.get("warnings") or []
    print(f"Warnings: {warnings}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run or inspect the Rule Runtime v1 paper-only observer.")
    parser.add_argument(
        "--mode",
        choices=[
            "init",
            "status",
            "once",
            "smoke",
            "smoke-file-adapter",
            "replay-file",
            "smoke-live-bus",
            "triage-audit",
            "triage-smoke",
            "birth-coverage-audit",
            "paper-buy-fdv-audit",
            "runtime-safety-patch-review",
            "bonding-curve-resolution-audit",
            "transaction-subscribe-capability-audit",
            "transaction-subscribe-smoke",
        ],
        default="status",
    )
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--starting-wallet-usd", type=float, default=300.0)
    parser.add_argument("--position-fraction", type=float, default=0.05)
    parser.add_argument("--event-json", default=None)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--source-sample-label", default="official_lifecycle_watch_v2")
    parser.add_argument("--source-followup-path", default=None)
    parser.add_argument("--max-events", type=int, default=500)
    parser.add_argument("--max-seconds", type=float, default=60.0)
    parser.add_argument("--target-confirmed-10k-watches", type=int, default=1)
    parser.add_argument("--target-confirmed-20k-candidates", type=int, default=1)
    parser.add_argument("--mock-live-bus-events", default=None)
    parser.add_argument("--collector-data-root", default=None)
    parser.add_argument("--target-births", type=int, default=5)
    parser.add_argument("--target-crossed-20k", type=int, default=1)
    parser.add_argument("--max-helius-credits", type=int, default=10_000)
    parser.add_argument("--signatures-per-mint", type=int, default=7)
    parser.add_argument("--transactions-per-mint", type=int, default=7)
    parser.add_argument("--no-apply-voids", action="store_true")
    return parser.parse_args()


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


if __name__ == "__main__":
    raise SystemExit(main())
