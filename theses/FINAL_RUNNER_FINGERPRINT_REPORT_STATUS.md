# Final Runner Fingerprint Report Status

This report was created to summarize broad descriptive runner fingerprints from the enriched FDV-proxy master dataset before formal thesis selection.

- Dataset used: `/Volumes/ORICO/MemeTraderPro/data/backtests/structural_enrichment/tier1_tier2_enrichment/master_tier1_tier2_enriched_runner_fingerprint.parquet`
- Rows analyzed: `1143`
- Readiness classification: `final_fingerprint_ready_for_formal_thesis_selection`
- Recommendation: `ready_for_formal_thesis_selection_from_broad_report`

## Coverage Summary
- has_aggregator_visibility_layer: `29 / 1143` (2.5372%)
- has_bot_sniper_proxy_layer: `422 / 1143` (36.9204%)
- has_cluster_proxy_layer: `100 / 1143` (8.7489%)
- has_contract_layer: `1143 / 1143` (100.0%)
- has_creator_extraction_layer: `411 / 1143` (35.958%)
- has_creator_funder_layer: `627 / 1143` (54.8556%)
- has_distribution_layer: `1143 / 1143` (100.0%)
- has_early_buyer_history_layer: `720 / 1143` (62.9921%)
- has_fdv_efficiency_layer: `1143 / 1143` (100.0%)
- has_holder_retention_layer: `100 / 1143` (8.7489%)
- has_liquidity_depth_layer: `422 / 1143` (36.9204%)
- has_lp_control_layer: `0 / 1143` (0.0%)
- has_metadata_profile_layer: `11 / 1143` (0.9624%)
- has_metadata_quality_layer: `11 / 1143` (0.9624%)
- has_priority_fee_layer: `0 / 1143` (0.0%)
- has_smart_money_quality_layer: `547 / 1143` (47.8565%)
- has_synthetic_activity_layer: `422 / 1143` (36.9204%)
- has_top_holder_layer: `715 / 1143` (62.5547%)
- has_topicality_layer: `11 / 1143` (0.9624%)
- has_visibility_layer: `29 / 1143` (2.5372%)
- has_visible_attention_and_flow_layer: `1143 / 1143` (100.0%)

## Major Commonalities
- `liquidity_token_proxy_at_20k`: lower_in_stronger_runners for `sub_100k_vs_100k_plus` with effect-size proxy `-1.183586` and coverage `36.9204%`.
- `fdv_per_active_wallet_at_20k`: higher_in_stronger_runners for `sub_1m_vs_1m_plus` with effect-size proxy `1.154097` and coverage `100.0%`.
- `fdv_per_buy_at_20k`: higher_in_stronger_runners for `sub_1m_vs_1m_plus` with effect-size proxy `1.111297` and coverage `100.0%`.
- `fdv_per_event_at_20k`: higher_in_stronger_runners for `sub_1m_vs_1m_plus` with effect-size proxy `1.03892` and coverage `100.0%`.
- `liquidity_sol_proxy_at_20k`: lower_in_stronger_runners for `sub_100k_vs_100k_plus` with effect-size proxy `-1.027477` and coverage `36.9204%`.
- `estimated_slippage_25_sol_at_20k`: higher_in_stronger_runners for `sub_100k_vs_100k_plus` with effect-size proxy `1.026455` and coverage `36.9204%`.
- `estimated_slippage_10_sol_at_20k`: higher_in_stronger_runners for `sub_100k_vs_100k_plus` with effect-size proxy `1.025059` and coverage `36.9204%`.
- `estimated_sell_impact_10_sol_at_20k`: higher_in_stronger_runners for `sub_100k_vs_100k_plus` with effect-size proxy `1.025059` and coverage `36.9204%`.

## Candidate Fingerprints
- `FRP-001` Efficient visible expansion with better wallet-quality proxy
- `FRP-002` Efficient expansion with lower synthetic-activity pressure
- `FRP-003` Wallet-quality positive with lower creator-extraction proxy
- `FRP-004` Junk-risk screen from synthetic activity, shared funding, and extraction proxies

## Missing Layers
- LP control / LP ownership: `blocked`
- Priority fee / compute-budget contention: `blocked`
- True market cap: `blocked`
- Confirmed full-chain historical holder state: `partial`
- Visibility / social / topicality: `sparse`
- Jito bundle truth: `blocked`

## Limitations

- All outcome language is FDV-proxy only; true market cap remains blocked.
- This is descriptive comparison only, not a thesis, validation, backtest, or trading-rule generator.
- LP control and priority-fee contention are unavailable in the current enriched master.
- Holder retention is partial and based on observed replay proxies, not confirmed full-chain account state.

No thesis, validation, backtest, paper/live trading, alerts, buy/sell rules, wallet execution, optimization, or strategy logic was run.
