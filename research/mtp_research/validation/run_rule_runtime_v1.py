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
    initialize_rule_runtime,
    rule_runtime_status,
    run_rule_runtime_live_bus_collector_smoke,
    run_rule_runtime_mock_live_bus_smoke,
    run_rule_runtime_live_adapter_once,
    run_rule_runtime_once,
    run_rule_runtime_smoke,
)


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
        print(f"event_to_rule_latency={result['event_to_rule_latency_p50_p90_p99']}")
        print(f"bus_to_runtime_latency={result['bus_to_runtime_latency_p50_p90_p99']}")
        print(f"runtime_eval_latency={result['runtime_eval_latency_p50_p90_p99']}")
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
        choices=["init", "status", "once", "smoke", "smoke-file-adapter", "replay-file", "smoke-live-bus"],
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
