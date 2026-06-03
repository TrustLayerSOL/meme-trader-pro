# FP001 Formal Descriptive Thesis Status

## Frozen FP001 Definition
- Fingerprint: `Efficient Expansion With Clean Funding Structure`
- Features: `['fdv_per_event_at_20k', 'fdv_per_buy_at_20k', 'fdv_per_active_wallet_at_20k', 'active_wallets_at_20k', 'shared_funding_proxy', 'time_linked_funding_proxy', 'launches_sharing_funder', 'creators_sharing_funder']`
- Expected directions: `{'active_wallets_at_20k': 'not_zero', 'creators_sharing_funder': 'lower', 'fdv_per_active_wallet_at_20k': 'higher', 'fdv_per_buy_at_20k': 'higher', 'fdv_per_event_at_20k': 'higher', 'launches_sharing_funder': 'lower', 'shared_funding_proxy': 'lower', 'time_linked_funding_proxy': 'lower'}`

## Dataset Used
- Rows analyzed: `712`

## Feature Coverage
- `{'total_rows': 712, 'rows_with_all_fp001_fields': 0, 'coverage_pct': 0.0, 'balanced_sample_rows': 462, 'leftover_sample_rows': 250, 'all_three_p0_rows': 539, 'coverage_by_milestone_tier': {'reached_20k_but_never_50k': {'rows': 160, 'rows_with_all_fp001_fields': 0, 'coverage_pct': 0.0}, 'reached_50k_but_never_100k': {'rows': 216, 'rows_with_all_fp001_fields': 0, 'coverage_pct': 0.0}, 'reached_100k_but_never_200k': {'rows': 62, 'rows_with_all_fp001_fields': 0, 'coverage_pct': 0.0}, 'reached_200k_but_never_500k': {'rows': 71, 'rows_with_all_fp001_fields': 0, 'coverage_pct': 0.0}, 'reached_500k_but_never_1m': {'rows': 75, 'rows_with_all_fp001_fields': 0, 'coverage_pct': 0.0}, 'reached_1m_plus': {'rows': 128, 'rows_with_all_fp001_fields': 0, 'coverage_pct': 0.0}}, 'top_dates': {}, 'top_creators': {}, 'missing_reason_counts': {'fdv_per_event_at_20k;fdv_per_buy_at_20k;fdv_per_active_wallet_at_20k': 712}}`

## Milestone Tier Results
- `reached_20k_but_never_50k`: support `0` / rows `160`
- `reached_50k_but_never_100k`: support `0` / rows `216`
- `reached_100k_but_never_200k`: support `0` / rows `62`
- `reached_200k_but_never_500k`: support `0` / rows `71`
- `reached_500k_but_never_1m`: support `0` / rows `75`
- `reached_1m_plus`: support `0` / rows `128`

## Balanced Vs Leftover Results
- `{'balanced': {'rows': 462, 'support_rows': 0, 'support_pct': 0.0, 'date_concentration': {'top_value': None, 'top_share_pct': 0.0}, 'creator_concentration': {'top_value': None, 'top_share_pct': 0.0}, 'targets': {'100k_plus': {'target_rows': 294, 'target_support_rows': 0, 'target_capture_pct': 0.0, 'support_precision_like_rate_pct': 0.0, 'baseline_target_rate_pct': 63.6364, 'support_minus_baseline_pct': -63.6364}, '500k_plus': {'target_rows': 161, 'target_support_rows': 0, 'target_capture_pct': 0.0, 'support_precision_like_rate_pct': 0.0, 'baseline_target_rate_pct': 34.8485, 'support_minus_baseline_pct': -34.8485}, '1m_plus': {'target_rows': 86, 'target_support_rows': 0, 'target_capture_pct': 0.0, 'support_precision_like_rate_pct': 0.0, 'baseline_target_rate_pct': 18.6147, 'support_minus_baseline_pct': -18.6147}, '1m_plus_vs_100k_only_or_lower': {'target_rows': 86, 'target_support_rows': 0, 'target_capture_pct': 0.0, 'support_precision_like_rate_pct': 0.0, 'baseline_target_rate_pct': 18.6147, 'support_minus_baseline_pct': -18.6147}}}, 'leftover': {'rows': 250, 'support_rows': 0, 'support_pct': 0.0, 'date_concentration': {'top_value': None, 'top_share_pct': 0.0}, 'creator_concentration': {'top_value': None, 'top_share_pct': 0.0}, 'targets': {'100k_plus': {'target_rows': 42, 'target_support_rows': 0, 'target_capture_pct': 0.0, 'support_precision_like_rate_pct': 0.0, 'baseline_target_rate_pct': 16.8, 'support_minus_baseline_pct': -16.8}, '500k_plus': {'target_rows': 42, 'target_support_rows': 0, 'target_capture_pct': 0.0, 'support_precision_like_rate_pct': 0.0, 'baseline_target_rate_pct': 16.8, 'support_minus_baseline_pct': -16.8}, '1m_plus': {'target_rows': 42, 'target_support_rows': 0, 'target_capture_pct': 0.0, 'support_precision_like_rate_pct': 0.0, 'baseline_target_rate_pct': 16.8, 'support_minus_baseline_pct': -16.8}, '1m_plus_vs_100k_only_or_lower': {'target_rows': 42, 'target_support_rows': 0, 'target_capture_pct': 0.0, 'support_precision_like_rate_pct': 0.0, 'baseline_target_rate_pct': 16.8, 'support_minus_baseline_pct': -16.8}}}, 'combined': {'rows': 712, 'support_rows': 0, 'support_pct': 0.0, 'date_concentration': {'top_value': None, 'top_share_pct': 0.0}, 'creator_concentration': {'top_value': None, 'top_share_pct': 0.0}, 'targets': {'100k_plus': {'target_rows': 336, 'target_support_rows': 0, 'target_capture_pct': 0.0, 'support_precision_like_rate_pct': 0.0, 'baseline_target_rate_pct': 47.191, 'support_minus_baseline_pct': -47.191}, '500k_plus': {'target_rows': 203, 'target_support_rows': 0, 'target_capture_pct': 0.0, 'support_precision_like_rate_pct': 0.0, 'baseline_target_rate_pct': 28.5112, 'support_minus_baseline_pct': -28.5112}, '1m_plus': {'target_rows': 128, 'target_support_rows': 0, 'target_capture_pct': 0.0, 'support_precision_like_rate_pct': 0.0, 'baseline_target_rate_pct': 17.9775, 'support_minus_baseline_pct': -17.9775}, '1m_plus_vs_100k_only_or_lower': {'target_rows': 128, 'target_support_rows': 0, 'target_capture_pct': 0.0, 'support_precision_like_rate_pct': 0.0, 'baseline_target_rate_pct': 17.9775, 'support_minus_baseline_pct': -17.9775}}}}`

## Robustness Checks
- `[{'check_name': 'combined_sample', 'rows': 712, 'support_rows': 0, 'support_pct': 0.0, 'target_100k_plus_support_minus_baseline_pct': -47.191, 'target_500k_plus_support_minus_baseline_pct': -28.5112, 'target_1m_plus_support_minus_baseline_pct': -17.9775, 'leftover_rows_driving_result': False}, {'check_name': 'balanced_sample_only', 'rows': 462, 'support_rows': 0, 'support_pct': 0.0, 'target_100k_plus_support_minus_baseline_pct': -63.6364, 'target_500k_plus_support_minus_baseline_pct': -34.8485, 'target_1m_plus_support_minus_baseline_pct': -18.6147, 'leftover_rows_driving_result': False}, {'check_name': 'leftover_sample_only', 'rows': 250, 'support_rows': 0, 'support_pct': 0.0, 'target_100k_plus_support_minus_baseline_pct': -16.8, 'target_500k_plus_support_minus_baseline_pct': -16.8, 'target_1m_plus_support_minus_baseline_pct': -16.8, 'leftover_rows_driving_result': False}, {'check_name': 'exclude_top_date', 'rows': 619, 'support_rows': 0, 'support_pct': 0.0, 'target_100k_plus_support_minus_baseline_pct': -53.4733, 'target_500k_plus_support_minus_baseline_pct': -32.6333, 'target_1m_plus_support_minus_baseline_pct': -20.517, 'leftover_rows_driving_result': False}, {'check_name': 'exclude_top_3_dates', 'rows': 498, 'support_rows': 0, 'support_pct': 0.0, 'target_100k_plus_support_minus_baseline_pct': -52.4096, 'target_500k_plus_support_minus_baseline_pct': -31.9277, 'target_1m_plus_support_minus_baseline_pct': -20.6827, 'leftover_rows_driving_result': False}, {'check_name': 'exclude_top_creator', 'rows': 682, 'support_rows': 0, 'support_pct': 0.0, 'target_100k_plus_support_minus_baseline_pct': -45.6012, 'target_500k_plus_support_minus_baseline_pct': -28.1525, 'target_1m_plus_support_minus_baseline_pct': -18.1818, 'leftover_rows_driving_result': False}, {'check_name': 'exclude_top_3_creators', 'rows': 637, 'support_rows': 0, 'support_pct': 0.0, 'target_100k_plus_support_minus_baseline_pct': -48.8226, 'target_500k_plus_support_minus_baseline_pct': -30.1413, 'target_1m_plus_support_minus_baseline_pct': -19.4662, 'leftover_rows_driving_result': False}]`

## Classification
- `data_limited`

## Later Robustness Or Validation
Robustness design can be considered later. No validation was run here.

## Limitations
- `true_market_cap_claims_remain_blocked`
- `uses_fdv_or_valuation_proxy_fields_only`
- `support_rule_is_fixed_from_prior_support_audit_not_optimized`
- `leftover_sample_is_date_concentrated_and_reported_separately`
- `formal_descriptive_only_no_validation_or_trading_claim`

## Next Recommendation
expand descriptive coverage before interpretation
