# RULE_RUNTIME_V1_STATUS

- Runtime label: `rule_runtime_v1`
- Frozen buy rule: `RULE_D_20K_EFFICIENCY_CREATOR_HOLDER_RISK_FILTER`
- Frozen exit rule: `EXIT_NO_RECLAIM_AFTER_30PCT_10M`
- Paper-only: `True`
- Live trading enabled: `False`
- Events processed: `652`
- Confirmed 10k watches: `3`
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
- Queue depth total: `13`
- Queue depth by tier: `{'tier_0_light_watch': 0, 'tier_1_fdv_path_seen': 4, 'tier_2_near_threshold_watch': 6, 'tier_3_confirmed_10k_watch': 3, 'tier_4_paper_position_open': 0}`
- Tier 1 depth: `4`
- Tier 1 oldest age: `20.695`
- Tier 1 p50/p90 age: `{'p50': 11.534691, 'p90': 20.695337}`
- Tier 1 processed count: `606`
- Tier 1 archive count: `542`
- Tier 1 promotion count: `606`
- Tier 1 retry count: `541`
- Tier 1 pressure mode: `True`
- Archived no activity: `593`
- Archived no FDV path timeout: `0`
- Promoted to FDV path: `606`
- Promoted to near-threshold: `60`
- Promoted to confirmed 10k: `3`
- Promoted to paper position: `0`
- First path success rate: `1.0`
- First-FDV success rate: `1.0`
- First-FDV timeout rate: `0.0`
- First-FDV median latency: `0.0`
- First path latency p50/p90/p99: `{'p50': 0.0, 'p90': 0.0, 'p99': 0.0}`

## First-FDV Probe Sources
- Bonding curve account-state successes: `652`
- Bonding curve account-state failures: `2`
- Transaction delta successes: `0`
- Confirmed path-state successes: `0`
- Unknown successes: `0`
- Source mix: `{'bonding_curve_account_state': 652}`
- getAccountInfo p50/p90/p99: `{'p50': 180.2145, 'p90': 213.127, 'p99': 408.939}`
- Decode p50/p90/p99: `{'p50': 0.0475, 'p90': 0.112, 'p99': 0.617}`
- Observed to account-state FDV p50/p90/p99: `{'p50': 386.553, 'p90': 1537.0, 'p99': 7940.16}`
- accountSubscribe status: `accountSubscribe_bonding_curve_not_implemented`
- Active account subscriptions: `0`

## Helius transactionSubscribe First-FDV
- transactionSubscribe supported: `True`
- endpoint used: `helius_beta`
- create events decoded: `609`
- curve PDA verified: `609`
- curve account probes started: `654`
- probes started during stream: `654`
- curve account probes succeeded: `652`
- curve account probes failed: `2`
- first-attempt successes: `542`
- account-not-found retries: `115`
- account-not-found recovered by retry: `110`
- account-not-found final failures: `0`
- account-not-found retry recovery rate: `1.0`
- first FDV from bonding curve account-state: `652`
- first FDV from transaction delta: `0`
- first FDV from unknown: `0`
- observed to probe started p50/p90/p99: `{'p50': 4.658, 'p90': 1216.418, 'p99': 7735.025}`
- probe started to first curve state p50/p90/p99: `{'p50': 370.5645, 'p90': 640.162, 'p99': 764.913}`
- observed to first FDV p50/p90/p99: `{'p50': 386.553, 'p90': 1537.0, 'p99': 7940.16}`
- getAccountInfo p50/p90/p99: `{'p50': 180.2145, 'p90': 213.127, 'p99': 408.939}`
- accountSubscribe p50/p90/p99: `{'p50': None, 'p90': None, 'p99': None}`
- warnings: `['bonding_curve_account_probe_failures_present']`

## Entry Gate Hot-Watch Patch - 2026-06-06
- Paper-only: `True`
- Real trading / signing / swaps / routing: `disabled`
- Token-2022 Pump.fun support: `added when Pump.fun create, bonding-curve PDA, account-state decode, FDV units, and calculation status are valid`
- Unknown/unsupported token-program reject: `retained`
- Duplicate-state sticky reject: `fixed; stale duplicate block clears after later distinct confirmation`
- Same-timestamp major jump: `still hard reject`
- Hot watch: `added via bounded due-time follow-up queue; no parallel worker expansion beyond existing bounded pools`
- Hot-watch trigger: `$8k`
- Entry zone: `$18k-$23k`
- Paper buy band: `$20k-$23k`
- Chase guard: `15% above $20k; max $23k`
- Missed-entry-zone reject: `implemented`
- Replay candidates reviewed: `4`
- Replay paper buys that would now pass: `0`
- Patch plan: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/forward_observation/rule_runtime_v1/entry_gate_patch_plan.md`
- Replay review: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/forward_observation/rule_runtime_v1/entry_gate_patch_replay_review.md`
- Smoke summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/forward_observation/rule_runtime_v1/entry_gate_hot_watch_patch_smoke_summary.md`
