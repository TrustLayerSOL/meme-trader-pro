# T007 Entity / Coordination Proxy Status

## Thesis Description

Do deterministic entity proxy and coordination proxy features have a descriptive relationship with FDV-proxy lifecycle outcomes in the strict launch-regime dataset?

## Dataset Used

- Strict launch-regime FDV-proxy lifecycle dataset
- Entity proxy dataset: `/Volumes/ORICO/MemeTraderPro/data/backtests/entity_proxy/entity_proxy_strict_cohort.jsonl`
- Launches analyzed: `1500`

## Proxy Coverage

- `creator_linked_share_proxy`: `1499` available, `99.93%` coverage
- `repeated_actor_overlap_proxy`: `1500` available, `100.00%` coverage
- `repeated_buyer_overlap_proxy`: `1500` available, `100.00%` coverage
- `synchronized_participation_proxy`: `1500` available, `100.00%` coverage
- `circularity_proxy`: `1500` available, `100.00%` coverage
- `churn_proxy`: `1500` available, `100.00%` coverage

## Outcome Coverage

- `fdv_proxy_runup_available`: `1500`
- `fdv_proxy_drawdown_available`: `1500`
- `price_available_120m`: `1500`
- `liquidity_proxy_available_120m`: `1500`

## Comparison To T001-T006

- `T001`: `no_signal`
- `T001_v2`: `no_signal`
- `T002`: `weak_signal`
- `T002_v2`: `weak_signal`
- `T002_v2_chronological_robustness`: `no_robust_signal`
- `T003`: `no_signal`
- `T004`: `no_signal`
- `T005`: `weak_signal_baseline_control`
- `T006`: `no_signal`
- `entity_proxy_vs_T005`: `entity_proxies_do_not_add_clear_descriptive_separation_beyond_T005_baseline_control`
- `comparison_note`: `Qualitative comparison only; no combined strategy or thesis promotion is made.`

## Classification

`no_signal`

## Limitations

- This is descriptive research only and does not produce trading rules.
- FDV proxy is not true market cap because circulating supply remains unavailable.
- Actor overlap is not entity resolution.
- Funding-link fields remain unavailable.
- Grouped entity holder share remains blocked.

## Blocked Fields

- `funding_link_proxy`
- `safe_entity_resolution_groups`
- `grouped_entity_holder_share`
- `true_market_cap`

## True Market-Cap Blocked Warning

True market-cap claims remain blocked; this report uses FDV proxy only.

## Chronological Robustness Recommendation

`False`

## Next Recommendation

park entity proxies or revisit blocked funding-link fields before expanding this thesis family

- Markdown summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T007_entity_coordination_proxy/T007_entity_coordination_proxy_summary.md`
- JSON summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T007_entity_coordination_proxy/T007_entity_coordination_proxy_summary.json`
- No thesis promotion was performed.
- No trading rules were generated.
- No profitability claims were generated.
- True market-cap claims remain blocked.
