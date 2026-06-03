# Non-FDV Incremental Information Audit Status

This audit was created after FRP-001 showed that visible FDV-efficiency separated strongly while the wallet-quality component was coverage-limited.

- Rows analyzed: `1143`
- Recommendation: `consider_risk_filter_descriptive_design_or_improve_feature_coverage`

## FDV Baseline Result
- high_fdv_efficiency: `{'category': 'fdv_baseline_bucket', 'bucket': 'high_fdv_efficiency', 'rows': 391, '100k_plus_rate_pct': 100.0, '500k_plus_rate_pct': 98.977, '1m_plus_rate_pct': 85.422, 'tier_distribution_json': '{"reached_1m_plus": 334, "reached_200k_but_never_500k": 4, "reached_500k_but_never_1m": 53}'}`
- low_medium_fdv_efficiency: `{'category': 'fdv_baseline_bucket', 'bucket': 'low_medium_fdv_efficiency', 'rows': 752, '100k_plus_rate_pct': 31.9149, '500k_plus_rate_pct': 11.4362, '1m_plus_rate_pct': 4.6543, 'tier_distribution_json': '{"reached_100k_but_never_200k": 62, "reached_1m_plus": 35, "reached_200k_but_never_500k": 92, "reached_20k_but_never_50k": 221, "reached_500k_but_never_1m": 51, "reached_50k_but_never_100k": 291}'}`
- 100k_plus_vs_sub_100k: `{'category': 'fdv_baseline_separation', 'bucket': '100k_plus_vs_sub_100k', 'rows': 1143, 'high_fdv_rate_high_group_pct': 61.9651, 'high_fdv_rate_low_group_pct': 0.0, 'separation_pct_points': 61.9651}`
- 500k_plus_vs_sub_500k: `{'category': 'fdv_baseline_separation', 'bucket': '500k_plus_vs_sub_500k', 'rows': 1143, 'high_fdv_rate_high_group_pct': 81.8182, 'high_fdv_rate_low_group_pct': 0.597, 'separation_pct_points': 81.2212}`
- 1m_plus_vs_sub_1m: `{'category': 'fdv_baseline_separation', 'bucket': '1m_plus_vs_sub_1m', 'rows': 1143, 'high_fdv_rate_high_group_pct': 90.5149, 'high_fdv_rate_low_group_pct': 7.3643, 'separation_pct_points': 83.1506}`
- 1m_plus_vs_100k_to_1m: `{'category': 'fdv_baseline_separation', 'bucket': '1m_plus_vs_100k_to_1m', 'rows': 1143, 'high_fdv_rate_high_group_pct': 90.5149, 'high_fdv_rate_low_group_pct': 21.7557, 'separation_pct_points': 68.7592}`

## Non-FDV Families Audited
- wallet_buyer_quality: available `3`, absent `0`
- funding_creator_funder_structure: available `6`, absent `0`
- top_holder_concentration: available `5`, absent `1`
- synthetic_authenticity: available `6`, absent `0`
- creator_extraction: available `3`, absent `0`
- liquidity_executability: available `4`, absent `2`
- contract_metadata_visibility: available `4`, absent `3`

## Features Adding Information
- None under fixed descriptive buckets.

## Risk-Filter Candidates
- synthetic_activity_proxy (synthetic_authenticity)

## Features Without Incremental Information
- aggregator_visibility_proxy (contract_metadata_visibility)
- dexscreener_boost_present (contract_metadata_visibility)
- dexscreener_paid_order_present (contract_metadata_visibility)
- creator_net_flow_sol_before_20k (creator_extraction)
- circular_buy_sell_wallet_count (synthetic_authenticity)
- rapid_round_trip_count (synthetic_authenticity)
- creator_extraction_proxy_before_20k (creator_extraction)
- creator_direct_sell_amount_sol (creator_extraction)
- top_holder_share_proxy (top_holder_concentration)
- early_holder_concentration (top_holder_concentration)
- early_buyer_with_prior_runner_count (wallet_buyer_quality)
- shared_funding_proxy (funding_creator_funder_structure)
- launches_sharing_funder (funding_creator_funder_structure)
- creators_sharing_funder (funding_creator_funder_structure)
- time_linked_funding_proxy (funding_creator_funder_structure)
- top_10_holder_share_proxy (top_holder_concentration)

## Data-Limited Fields
- wash_trade_proxy_share_before_20k (synthetic_authenticity)
- smart_money_quality_proxy (wallet_buyer_quality)
- repeated_buyer_quality_proxy (wallet_buyer_quality)
- holder_retention_proxy (top_holder_concentration)
- holder_churn_proxy (top_holder_concentration)
- bot_sniper_proxy_share (synthetic_authenticity)
- coordinated_timing_proxy (synthetic_authenticity)
- early_buyer_with_prior_100k_count (wallet_buyer_quality)
- early_buyer_with_prior_500k_count (wallet_buyer_quality)
- early_buyer_with_prior_1m_count (wallet_buyer_quality)
- early_buyer_prior_failure_count (wallet_buyer_quality)
- candidate_funder_confidence (funding_creator_funder_structure)
- common_funder_candidate_id (funding_creator_funder_structure)
- creator_linked_wallet_net_flow_sol (creator_extraction)
- metadata_quality_bucket (contract_metadata_visibility)
- holder_count (top_holder_concentration)
- liquidity_depth_proxy (liquidity_executability)
- exit_liquidity_proxy (liquidity_executability)
- mint_authority_status (contract_metadata_visibility)
- freeze_authority_status (contract_metadata_visibility)
- token_2022_flag (contract_metadata_visibility)

## Candidate Next Fingerprints
- NFDV-001: FDV efficiency plus synthetic_activity_proxy possible_risk_filter

## What Not To Do Next
- Do not create trading rules, optimize thresholds, run validation, or promote a thesis from this diagnostic audit.

No thesis, validation, walk-forward validation, backtest, paper/live trading, alerts, buy/sell rules, wallet execution, optimization, ML, or strategy logic was run.
