# 2026-05-24 Context Blocker Reduction

## Purpose

This run builds a review-only priority queue for reducing forward entry-context blockers. It focuses on the `fix_context` wallets from the merged forward recommendation layer and separates blockers by missing evidence type.

This packet does not promote wallets, mutate wallet trust, mutate wallet lists, unlock execution, or claim profitability.

## Commands

```bash
python3 -m utils.build_forward_entry_context_repair_plan
python3 -m utils.build_forward_entry_context_resolver
python3 -m utils.build_forward_merged_calibration_scorecard
python3 -m utils.build_forward_merged_calibration_recommendations
python3 -m utils.build_forward_wallet_trust_review_packet --bucket review_behavioral_signal --limit 3 --run-id 20260524-forward-wallet-trust-review
python3 -m utils.build_forward_context_blocker_reduction --run-id 20260524-context-blocker-reduction
```

## Outputs

- `data/reports/forward_testing/context_blocker_reduction/forward_context_blocker_reduction_20260524-context-blocker-reduction.json`
- `data/reports/forward_testing/context_blocker_reduction/forward_context_blocker_reduction_20260524-context-blocker-reduction.csv`
- `data/reports/forward_testing/context_blocker_reduction/forward_context_blocker_reduction_20260524-context-blocker-reduction.md`

## Summary

- Fix-context wallets: `21`
- Blocked records in fix-context queue: `1,209`
- Repair-plan blocked rows represented: `1,213`
- Missing later market snapshot rows: `468`
- Missing valid execution price quote rows: `741`
- Priority market-snapshot wallets: `3`
- Priority entry-timestamp/quote wallets: `18`
- Resolver rows already repaired: `84`
- Resolver known 15m outcomes after repair: `60`
- Promotions allowed: `0`
- Wallet-list mutations: `0`
- Auto trust mutations: `0`

## Top Priority Queue

| Wallet | Recommended action | Blocked | Missing snapshots | Missing quote | Tokens | Context completion |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `HLnpSz9h2S4hiLQ43rnSD9XkcUThA7B8hQMKmDaiTLcC` | `repair_market_snapshot` | 457 | 455 | 2 | 259 | 0.0022 |
| `35dR1ZNF7WAcfLsPbnAEr9YcJbooNapWN6WPZnkAa3LK` | `repair_market_snapshot` | 9 | 9 | 0 | 1 | 0.0 |
| `3tkxn3YHxv5nghH1FTJ4hqxKredqWqbDVVT2ouatU3ih` | `repair_market_snapshot` | 4 | 4 | 0 | 3 | 0.4286 |
| `6b86E2apHeeHoLeeZs5bRSW8gFGDNqYH468mqVGuccdi` | `repair_entry_timestamp` | 301 | 0 | 301 | 60 | 0.0 |
| `HnnfuREPudg1gRPBPiFyzQukTY9SQpsBdidq86vVtR4E` | `repair_entry_timestamp` | 103 | 0 | 103 | 35 | 0.0 |

## Interpretation

The fastest possible blocker reduction is likely the market-snapshot lane, especially `HLnpSz9h2S4hiLQ43rnSD9XkcUThA7B8hQMKmDaiTLcC`, because many rows already have quote anchors and mostly need later market snapshots. The broader blocker mass is the entry-price quote/timestamp lane, where rows cannot be repaired safely until a valid same-transaction execution-price quote is recovered.

## Next Step

Work the `repair_market_snapshot` queue first, then rerun the resolver and merged scorecard. Do not use any repaired row for wallet trust validation until the resolver emits clean review-only repaired records.
