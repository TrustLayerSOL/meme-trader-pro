# Axiom Historical Parity Status

## Why This Matters
The next structural research layer needs historical fields that approximate what real-time token dashboards expose, while keeping MemeTraderPro replay-safe and neutral in its terminology.

## Current Coverage
- Concepts mapped: `12`
- Historical fields mapped: `76`
- Ready now or with local joins: `27`
- Need Helius to scale or validate: `46`
- Blocked: `6`

## Fields Already Available
top_holder_change_after_trigger, top_10_holder_change_after_trigger, creator_holder_share_at_milestone, creator_balance_at_milestone, creator_sell_count_after_trigger, creator_net_flow_after_trigger, creator_distribution_proxy, early_buyer_concentration_proxy, first_5_buyer_share, first_10_buyer_share, first_20_buyer_share, first_block_buyer_share

## Fields Requiring Helius
top_holder_share_at_milestone, top_10_holder_share_at_milestone, top_holder_addresses_at_milestone, top_10_holder_addresses_at_milestone, top_holder_balance_at_milestone, top_10_balances_at_milestone, top_holder_change_after_trigger, top_10_holder_change_after_trigger, creator_linked_wallet_proxy, creator_linked_buyer_count, creator_linked_top10_share, shared_funder_with_creator_flag

## Fields Requiring Parser Or Source Repair
dex_paid_flag, dex_boost_status, dex_profile_status, dex_order_status, first_dexscreener_seen_time, visibility_lag_from_launch

## Recommended Next Execution Step
`run_creator_funder_transfer_graph_pilot`

Do not execute it from this sprint. It needs a separate bounded run request with explicit execute approval.

## What Should Not Be Done Next
- Do not run a thesis from this mapping sprint.
- Do not compare these fields to outcomes yet.
- Do not build trading rules or alerts.
- Do not run uncapped Helius collection.
- Do not make true market-cap claims.

## Reports
- Field map CSV: /Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/axiom_historical_parity/axiom_historical_field_map.csv
- Summary JSON: /Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/axiom_historical_parity/axiom_historical_parity_summary.json
- Summary Markdown: /Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/axiom_historical_parity/axiom_historical_parity_summary.md
