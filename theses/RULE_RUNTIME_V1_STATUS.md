# RULE_RUNTIME_V1_STATUS

- Runtime label: `rule_runtime_v1`
- Frozen buy rule: `RULE_D_20K_EFFICIENCY_CREATOR_HOLDER_RISK_FILTER`
- Frozen exit rule: `EXIT_NO_RECLAIM_AFTER_30PCT_10M`
- Paper-only: `True`
- Live trading enabled: `False`
- Events processed: `1580`
- Confirmed 10k watches: `4`
- Confirmed 20k candidates: `3`
- Paper buys: `0`
- Paper sells: `0`
- Threshold status: `baseline-label-mode`
- Monitor: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/forward_observation/rule_runtime_v1/rule_runtime_v1_monitor.html`

## Rule Runtime v1 Variants
- `FDV_BASELINE_20K`: buys `0`, sells `0`, open `0`, rejected `5`, not_evaluable `0`, missing_fields `0`
- `FDV_CREATOR_HOLDER_AVAILABLE_FILTER`: buys `0`, sells `0`, open `0`, rejected `5`, not_evaluable `0`, missing_fields `0`
- `FDV_FULL_RISK_FILTER_WHEN_AVAILABLE`: buys `0`, sells `0`, open `0`, rejected `5`, not_evaluable `0`, missing_fields `0`

## First FDV Queue
- Scheduler mode: `priority_single_worker`
- Queue depth total: `7`
- Queue depth by tier: `{'tier_0_light_watch': 1, 'tier_1_fdv_path_seen': 0, 'tier_2_near_threshold_watch': 3, 'tier_3_confirmed_10k_watch': 3, 'tier_4_paper_position_open': 0}`
- Tier 1 depth: `0`
- Tier 1 oldest age: `None`
- Tier 1 p50/p90 age: `{'p50': None, 'p90': None}`
- Tier 1 processed count: `301`
- Tier 1 archive count: `1230`
- Tier 1 promotion count: `301`
- Tier 1 retry count: `478`
- Tier 1 pressure mode: `True`
- Archived no activity: `1264`
- Archived no FDV path timeout: `0`
- Promoted to FDV path: `301`
- Promoted to near-threshold: `45`
- Promoted to confirmed 10k: `3`
- Promoted to paper position: `0`
- First path success rate: `1.0`
- First-FDV success rate: `1.0`
- First-FDV timeout rate: `0.0`
- First-FDV median latency: `0.0`
- First path latency p50/p90/p99: `{'p50': 0.0, 'p90': 0.0, 'p99': 0.0}`

## First-FDV Probe Sources
- Bonding curve account-state successes: `1580`
- Bonding curve account-state failures: `13`
- Transaction delta successes: `0`
- Confirmed path-state successes: `0`
- Unknown successes: `0`
- Source mix: `{'bonding_curve_account_state': 1580}`
- getAccountInfo p50/p90/p99: `{'p50': 189.3715, 'p90': 217.439, 'p99': 252.522}`
- Decode p50/p90/p99: `{'p50': 0.022, 'p90': 0.054, 'p99': 0.125}`
- Observed to account-state FDV p50/p90/p99: `{'p50': 121521.232, 'p90': 325275.126, 'p99': 453620.772}`
- accountSubscribe status: `accountSubscribe_bonding_curve_not_implemented`
- Active account subscriptions: `0`

## Helius transactionSubscribe First-FDV
- transactionSubscribe supported: `True`
- endpoint used: `helius_beta`
- create events decoded: `302`
- curve PDA verified: `302`
- curve account probes started: `1593`
- probes started during stream: `1593`
- post-birth watch scheduled/probes/successes/pending: `1431` / `1245` / `1233` / `93`
- post-birth watch promotions 5k/10k/20k: `17` / `6` / `3`
- post-birth watch archives/rechecked runners: `215` / `3`
- low-FDV watch oldest age/due count: `521.084279` / `1200`
- post-birth watch lane counts: `{'confirmed_10k_candidate': 5, 'low_fdv': 1200, 'near_threshold': 40}`
- curve account probes succeeded: `1580`
- curve account probes failed: `13`
- first-attempt successes: `1566`
- account-not-found retries: `15`
- account-not-found recovered by retry: `14`
- account-not-found final failures: `0`
- account-not-found retry recovery rate: `1.0`
- first FDV from bonding curve account-state: `1580`
- first FDV from transaction delta: `0`
- first FDV from unknown: `0`
- observed to probe started p50/p90/p99: `{'p50': 121346.398, 'p90': 327373.175, 'p99': 455262.378}`
- probe started to first curve state p50/p90/p99: `{'p50': 396.087, 'p90': 437.929, 'p99': 624.998}`
- observed to first FDV p50/p90/p99: `{'p50': 121521.232, 'p90': 325275.126, 'p99': 453620.772}`
- getAccountInfo p50/p90/p99: `{'p50': 189.392, 'p90': 217.521, 'p99': 252.522}`
- accountSubscribe p50/p90/p99: `{'p50': None, 'p90': None, 'p99': None}`
- warnings: `['bonding_curve_account_probe_failures_present']`

## Entry Gate Hot-Watch Patch - 2026-06-06
- Commit: `0142382 fix: tighten rule runtime entry gates`
- Paper-only: `True`
- Real trading / signing / swaps / routing: `disabled`
- Token-2022 Pump.fun support: `added when Pump.fun create, bonding-curve PDA, account-state decode, FDV units, and calculation status are valid`
- Unknown/unsupported token-program reject: `retained`
- Duplicate-state sticky reject: `fixed; stale duplicate block clears after later distinct confirmation`
- Same-timestamp major jump: `still hard reject`
- Hot watch: `added via bounded due-time follow-up queue`
- Hot-watch trigger: `$8k`
- Entry zone: `$18k-$23k`
- Paper buy band: `$20k-$23k`
- Chase guard: `15% above $20k; max $23k`
- Missed-entry-zone reject: `implemented`
- Replay candidates reviewed: `4`
- Replay paper buys that would now pass: `0`
- Latest 20-minute scan decoded creates: `302`
- Latest 20-minute scan confirmed 10k / 20k: `4 / 3`
- Latest 20-minute scan paper buys/sells: `0 / 0`
- Latest 20-minute scan hot-watch probes: `6`
- Patch plan: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/forward_observation/rule_runtime_v1/entry_gate_patch_plan.md`
- Replay review: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/forward_observation/rule_runtime_v1/entry_gate_patch_replay_review.md`
- Smoke summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/forward_observation/rule_runtime_v1/entry_gate_hot_watch_patch_smoke_summary.md`
