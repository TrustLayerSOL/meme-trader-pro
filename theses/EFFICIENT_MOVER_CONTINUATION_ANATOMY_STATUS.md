# Efficient-Mover Continuation Anatomy Status

This report was created to start broad inside the high FDV-efficiency universe and identify descriptive continuation, trap/stall, or path-side separators without testing a predetermined filter.

## Efficient-Mover Universe Definition
- fixed high FDV-efficiency support_count >= 3 from non-optimized quantile buckets
- Rows: `391`
- Tier distribution: `{'reached_1m_plus': 334, 'reached_500k_but_never_1m': 53, 'reached_200k_but_never_500k': 4}`

## Continuation vs Trap Labels
- Primary continuation proxy: `reached_1m_plus`
- Primary trap/stall proxy: `efficient_mover_but_failed_to_reach_1m`
- Secondary collapse proxy: `failed_to_reach_500k`
- Counts: `{'efficient_mover_rows': 391, 'continuation_rows': 334, 'trap_or_stall_rows': 57, 'failed_to_reach_500k_rows': 4, 'reached_500k_but_never_1m_rows': 53}`

## Strongest Continuation-Positive Candidates
- creator_net_flow_sol_before_20k (creator_extraction): effect `0.9966`
- early_buyer_with_prior_runner_count (wallet_buyer_quality): effect `0.5`

## Strongest Risk-Filter Candidates
- None with sufficient broad support.

## Path/Exit Candidates
- buy_count_at_20k (flow_path_secondary): effect `1.0`
- event_count_at_20k (flow_path_secondary): effect `1.0`

## Data-Limited Fields
- smart_money_quality_proxy (wallet_buyer_quality)
- wash_trade_proxy_share_before_20k (synthetic_authenticity)
- creator_linked_wallet_net_flow_sol (creator_extraction)
- buy_sell_ratio_at_20k (flow_path_secondary)
- candidate_funder_confidence (funding_creator_funder_structure)
- common_funder_candidate_id (funding_creator_funder_structure)
- metadata_quality_bucket (metadata_visibility_contract)
- holder_churn_proxy (top_holder_concentration)
- holder_retention_proxy (top_holder_concentration)
- early_buyer_prior_failure_count (wallet_buyer_quality)
- early_buyer_with_prior_100k_count (wallet_buyer_quality)
- early_buyer_with_prior_1m_count (wallet_buyer_quality)
- early_buyer_with_prior_500k_count (wallet_buyer_quality)
- repeated_buyer_quality_proxy (wallet_buyer_quality)
- time_to_100k_from_20k (flow_path_secondary)
- time_to_1m_from_20k (flow_path_secondary)
- time_to_500k_from_20k (flow_path_secondary)
- exit_liquidity_proxy (liquidity_executability)
- liquidity_depth_proxy (liquidity_executability)
- freeze_authority_status (metadata_visibility_contract)
- mint_authority_status (metadata_visibility_contract)
- token_2022_flag (metadata_visibility_contract)
- holder_count (top_holder_concentration)

## Recommended Next Action
- `A - run_formal_descriptive_thesis_for_best_risk_or_continuation_filter_candidate`

## Limitations
- Efficient-mover universe uses fixed FDV-efficiency quantile-style buckets, not optimized thresholds.
- Continuation/trap labels are milestone-tier proxies, not trade outcomes.
- Path/drawdown fields are sparse or unavailable and remain marked as missing when absent.
- FDV/valuation proxy only; true market-cap claims remain blocked.
- No thesis, validation, walk-forward validation, backtest, optimization, alerts, or execution logic was run.
