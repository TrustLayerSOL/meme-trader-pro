# RULE_RUNTIME_V1_STATUS

- Runtime label: `rule_runtime_v1`
- Frozen buy rule: `RULE_D_20K_EFFICIENCY_CREATOR_HOLDER_RISK_FILTER`
- Frozen exit rule: `EXIT_NO_RECLAIM_AFTER_30PCT_10M`
- Paper-only: `True`
- Live trading enabled: `False`
- Events processed: `4`
- Confirmed 10k watches: `1`
- Confirmed 20k candidates: `0`
- Paper buys: `0`
- Paper sells: `0`
- Threshold status: `baseline-label-mode`
- Monitor: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/forward_observation/rule_runtime_v1/rule_runtime_v1_monitor.html`

## Rule Runtime v1 Variants
- `FDV_BASELINE_20K`: buys `0`, sells `0`, open `0`, rejected `0`, not_evaluable `0`, missing_fields `0`
- `FDV_CREATOR_HOLDER_AVAILABLE_FILTER`: buys `0`, sells `0`, open `0`, rejected `0`, not_evaluable `0`, missing_fields `0`
- `FDV_FULL_RISK_FILTER_WHEN_AVAILABLE`: buys `0`, sells `0`, open `0`, rejected `0`, not_evaluable `0`, missing_fields `0`

## First FDV Queue
- Scheduler mode: `priority_single_worker`
- Queue depth total: `3`
- Queue depth by tier: `{'tier_0_light_watch': 0, 'tier_1_fdv_path_seen': 1, 'tier_2_near_threshold_watch': 1, 'tier_3_confirmed_10k_watch': 1, 'tier_4_paper_position_open': 0}`
- Archived no activity: `0`
- Archived no FDV path timeout: `0`
- Promoted to FDV path: `3`
- Promoted to near-threshold: `2`
- Promoted to confirmed 10k: `1`
- Promoted to paper position: `0`
- First path success rate: `1.0`
- First path latency p50/p90/p99: `{'p50': 0.0, 'p90': 0.0, 'p99': 0.0}`
