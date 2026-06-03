# FRP-001 Formal Descriptive Thesis Status

This status file records the formal descriptive cycle for FRP-001 only. It does not promote a thesis and does not create trading logic.

## Frozen FRP-001 Definition
- Fingerprint: `FRP-001`
- Name: `Efficient visible expansion with better wallet-quality proxy`
- Features: `fdv_per_event_at_20k;fdv_per_buy_at_20k;smart_money_quality_proxy;early_buyer_with_prior_runner_count`
- Expected directions: `{"early_buyer_with_prior_runner_count": "flat_or_unknown", "fdv_per_buy_at_20k": "higher_in_stronger_runners", "fdv_per_event_at_20k": "higher_in_stronger_runners", "smart_money_quality_proxy": "flat_or_unknown"}`

## Dataset
- Master: `/Volumes/ORICO/MemeTraderPro/data/backtests/structural_enrichment/tier1_tier2_enrichment/master_tier1_tier2_enriched_runner_fingerprint.parquet`
- Rows analyzed: `1143`

## Feature Coverage
- Rows with all FRP-001 fields: `539`
- Coverage: `47.1566`

## Milestone Tier Results
- reached_20k_but_never_50k: support `0 / 221` (0.0%)
- reached_50k_but_never_100k: support `0 / 291` (0.0%)
- reached_100k_but_never_200k: support `0 / 62` (0.0%)
- reached_200k_but_never_500k: support `0 / 96` (0.0%)
- reached_500k_but_never_1m: support `3 / 104` (2.8846%)
- reached_1m_plus: support `71 / 369` (19.2412%)

## Visible-Only Comparison
- `{'comparison_method': 'fixed_tertile_bucket_scores_no_threshold_search', 'primary_contrast': {'contrast': '500k_plus_vs_sub_500k', 'visible_only_separation': 1.0, 'wallet_quality_separation': -0.5, 'combined_frp001_separation': 0.25, 'visible_only_support_rate_higher_pct': 82.8753, 'frp001_support_rate_higher_pct': 15.6448, 'wallet_quality_coverage_pct': 47.1566}, 'all_contrasts': [{'contrast': '100k_plus_vs_sub_100k', 'visible_only_separation': 1.0, 'wallet_quality_separation': -0.5, 'combined_frp001_separation': 0.25, 'visible_only_support_rate_higher_pct': 62.7575, 'frp001_support_rate_higher_pct': 11.7274, 'wallet_quality_coverage_pct': 47.1566}, {'contrast': '500k_plus_vs_sub_500k', 'visible_only_separation': 1.0, 'wallet_quality_separation': -0.5, 'combined_frp001_separation': 0.25, 'visible_only_support_rate_higher_pct': 82.8753, 'frp001_support_rate_higher_pct': 15.6448, 'wallet_quality_coverage_pct': 47.1566}, {'contrast': '1m_plus_vs_sub_1m', 'visible_only_separation': 1.0, 'wallet_quality_separation': 0.0, 'combined_frp001_separation': 0.25, 'visible_only_support_rate_higher_pct': 93.7669, 'frp001_support_rate_higher_pct': 19.2412, 'wallet_quality_coverage_pct': 47.1566}], 'wallet_quality_adds_information': False, 'wallet_quality_coverage_limited': True, 'wallet_quality_most_useful_tier_hint': '1m_plus_vs_sub_1m'}`

## Robustness Checks
- `{'checks_run': 12, 'checks_with_both_groups': 12, 'directionally_consistent_checks': 11, 'directional_consistency_pct': 91.6667}`

## Classification
- `data_limited`

## Limitations
- FDV-proxy only; true market-cap claims remain blocked.
- Formal descriptive thesis only; no validation, backtest, optimization, or trading logic.
- Wallet-quality proxy fields are descriptive proxies and are not identity or intent labels.
- FRP-002, FRP-003, and FRP-004 were not tested in this sprint.

No FRP-002, FRP-003, or FRP-004 execution was run. No validation, walk-forward validation, backtest, paper/live trading, alerts, buy/sell rules, wallet execution, optimization, ML, or strategy logic was run.

## Next Recommendation
- `improve_frp001_field_coverage_before_interpretation`
