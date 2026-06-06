# RULE_RUNTIME_V1_STATUS

- Runtime label: `rule_runtime_v1`
- Frozen buy rule: `RULE_D_20K_EFFICIENCY_CREATOR_HOLDER_RISK_FILTER`
- Frozen exit rule: `EXIT_NO_RECLAIM_AFTER_30PCT_10M`
- Paper-only: `True`
- Live trading enabled: `False`
- Events processed: `9`
- Confirmed 10k watches: `0`
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
- Queue depth total: `9`
- Queue depth by tier: `{'tier_0_light_watch': 0, 'tier_1_fdv_path_seen': 9, 'tier_2_near_threshold_watch': 0, 'tier_3_confirmed_10k_watch': 0, 'tier_4_paper_position_open': 0}`
- Tier 1 depth: `9`
- Tier 1 oldest age: `109.391`
- Tier 1 p50/p90 age: `{'p50': 45.707696, 'p90': 70.989022}`
- Tier 1 processed count: `9`
- Tier 1 archive count: `0`
- Tier 1 promotion count: `9`
- Tier 1 retry count: `0`
- Tier 1 pressure mode: `False`
- Archived no activity: `0`
- Archived no FDV path timeout: `0`
- Promoted to FDV path: `9`
- Promoted to near-threshold: `0`
- Promoted to confirmed 10k: `0`
- Promoted to paper position: `0`
- First path success rate: `1.0`
- First-FDV success rate: `1.0`
- First-FDV timeout rate: `0.0`
- First-FDV median latency: `0.0`
- First path latency p50/p90/p99: `{'p50': 0.0, 'p90': 0.0, 'p99': 0.0}`

## First-FDV Probe Sources
- Bonding curve account-state successes: `9`
- Bonding curve account-state failures: `7`
- Transaction delta successes: `0`
- Confirmed path-state successes: `0`
- Unknown successes: `0`
- Source mix: `{'bonding_curve_account_state': 9}`
- getAccountInfo p50/p90/p99: `{'p50': 184.332, 'p90': 194.952, 'p99': 205.703}`
- Decode p50/p90/p99: `{'p50': 0.061, 'p90': 0.085, 'p99': 0.169}`
- Observed to account-state FDV p50/p90/p99: `{'p50': 190.608, 'p90': 199.479, 'p99': 213.091}`
- accountSubscribe status: `accountSubscribe_bonding_curve_not_implemented`
- Active account subscriptions: `0`

## Helius transactionSubscribe First-FDV
- transactionSubscribe supported: `True`
- endpoint used: `helius_beta`
- create events decoded: `16`
- curve PDA verified: `16`
- curve account probes started: `16`
- probes started during stream: `16`
- curve account probes succeeded: `9`
- curve account probes failed: `7`
- first FDV from bonding curve account-state: `9`
- first FDV from transaction delta: `0`
- first FDV from unknown: `0`
- observed to probe started p50/p90/p99: `{'p50': 4.713, 'p90': 8.346, 'p99': 9.973}`
- probe started to first curve state p50/p90/p99: `{'p50': 174.839, 'p90': 200.568, 'p99': 205.796}`
- observed to first FDV p50/p90/p99: `{'p50': 190.608, 'p90': 199.479, 'p99': 213.091}`
- getAccountInfo p50/p90/p99: `{'p50': 174.828, 'p90': 200.559, 'p99': 205.703}`
- accountSubscribe p50/p90/p99: `{'p50': None, 'p90': None, 'p99': None}`
- warnings: `['bonding_curve_account_probe_failures_present']`
