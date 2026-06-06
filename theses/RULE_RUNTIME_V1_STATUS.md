# RULE_RUNTIME_V1_STATUS

- Runtime label: `rule_runtime_v1`
- Frozen buy rule: `RULE_D_20K_EFFICIENCY_CREATOR_HOLDER_RISK_FILTER`
- Frozen exit rule: `EXIT_NO_RECLAIM_AFTER_30PCT_10M`
- Paper-only: `True`
- Live trading enabled: `False`
- Events processed: `112`
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
- Queue depth total: `112`
- Queue depth by tier: `{'tier_0_light_watch': 0, 'tier_1_fdv_path_seen': 111, 'tier_2_near_threshold_watch': 1, 'tier_3_confirmed_10k_watch': 0, 'tier_4_paper_position_open': 0}`
- Tier 1 depth: `111`
- Tier 1 oldest age: `595.726`
- Tier 1 p50/p90 age: `{'p50': 306.522053, 'p90': 539.239891}`
- Tier 1 processed count: `112`
- Tier 1 archive count: `0`
- Tier 1 promotion count: `112`
- Tier 1 retry count: `0`
- Tier 1 pressure mode: `True`
- Archived no activity: `0`
- Archived no FDV path timeout: `0`
- Promoted to FDV path: `112`
- Promoted to near-threshold: `1`
- Promoted to confirmed 10k: `0`
- Promoted to paper position: `0`
- First path success rate: `1.0`
- First-FDV success rate: `1.0`
- First-FDV timeout rate: `0.0`
- First-FDV median latency: `0.0`
- First path latency p50/p90/p99: `{'p50': 0.0, 'p90': 0.0, 'p99': 0.0}`

## First-FDV Probe Sources
- Bonding curve account-state successes: `112`
- Bonding curve account-state failures: `0`
- Transaction delta successes: `0`
- Confirmed path-state successes: `0`
- Unknown successes: `0`
- Source mix: `{'bonding_curve_account_state': 112}`
- getAccountInfo p50/p90/p99: `{'p50': 171.5165, 'p90': 189.748, 'p99': 234.069}`
- Decode p50/p90/p99: `{'p50': 0.062, 'p90': 0.134, 'p99': 0.447}`
- Observed to account-state FDV p50/p90/p99: `{'p50': 443.0455, 'p90': 477.908, 'p99': 882.645}`
- accountSubscribe status: `accountSubscribe_bonding_curve_not_implemented`
- Active account subscriptions: `0`

## Helius transactionSubscribe First-FDV
- transactionSubscribe supported: `True`
- endpoint used: `helius_beta`
- create events decoded: `112`
- curve PDA verified: `112`
- curve account probes started: `112`
- probes started during stream: `112`
- curve account probes succeeded: `112`
- curve account probes failed: `0`
- first-attempt successes: `39`
- account-not-found retries: `77`
- account-not-found recovered by retry: `73`
- account-not-found final failures: `0`
- account-not-found retry recovery rate: `1.0`
- first FDV from bonding curve account-state: `112`
- first FDV from transaction delta: `0`
- first FDV from unknown: `0`
- observed to probe started p50/p90/p99: `{'p50': 4.453, 'p90': 8.075, 'p99': 13.933}`
- probe started to first curve state p50/p90/p99: `{'p50': 437.966, 'p90': 468.127, 'p99': 878.424}`
- observed to first FDV p50/p90/p99: `{'p50': 443.0455, 'p90': 477.908, 'p99': 882.645}`
- getAccountInfo p50/p90/p99: `{'p50': 171.5165, 'p90': 189.748, 'p99': 234.069}`
- accountSubscribe p50/p90/p99: `{'p50': None, 'p90': None, 'p99': None}`
- warnings: `[]`
