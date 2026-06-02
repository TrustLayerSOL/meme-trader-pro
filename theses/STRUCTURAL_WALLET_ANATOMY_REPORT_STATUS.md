# Structural Wallet Anatomy Report Status

## Why This Report Was Created
The previous winner anatomy report found visible valuation-efficiency separation. This report checks whether hidden wallet/dev/cluster proxy structure is observable before explosive FDV-proxy milestones.

Readiness classification: `structural_wallet_report_ready_for_next_thesis`

## Data Availability Summary
- Launches analyzed: 14809
- Holder-state coverage: 0.1013
- Entity-proxy coverage: 0.1013
- Funding-link coverage: 0.0450
- Event coverage: 0.8323

## Structural Feature Families
- creator_linked_ownership: partial_needs_more_data
- top_holder_structure: partial_needs_more_data
- top_holder_address_behavior: blocked_requires_external_fetch
- repeated_buyer_wallet_overlap: ready_for_anatomy_report
- wallet_quality_proxy: ready_for_anatomy_report
- funder_lineage: partial_needs_more_data
- creator_to_wallet_relationship_proxy: partial_needs_more_data
- cluster_coordination_proxy: partial_needs_more_data
- distribution_behavior: partial_needs_more_data
- valuation_efficiency_context: ready_for_anatomy_report

## What Is Blocked
- top_holder_addresses: holder address snapshots or replayed per-wallet holder balances
- complete_creator_funder_graph: bounded pre-launch funding enrichment over expanded creators
- bundle_or_execution_group_ids: transaction metadata enrichment with bundle or execution grouping if available
- per_wallet_realized_behavior_after_trigger: per-wallet event replay keyed to milestone crossing time

## Entry-Side Candidate Features
- churn_proxy
- circularity_proxy
- creator_funder_reuse_count
- creator_holder_share_at_20k
- creator_linked_share_proxy
- creator_prior_migration_or_graduation_count
- early_buyer_count_proxy
- early_buyer_seen_in_prior_launches_count
- event_actor_count
- fdv_per_active_wallet_at_20k
- fdv_per_buy_at_20k
- fdv_per_event_at_20k
- funding_age_seconds
- funding_source_available
- launches_sharing_funder
- repeated_actor_overlap_proxy
- repeated_buyer_overlap_proxy
- repeated_funder_flag
- synchronized_participation_proxy
- top_10_holder_share_at_20k
- top_holder_share_at_20k
- valuation_growth_per_buy_at_20k
- valuation_growth_per_event_at_20k

## Exit-Side Candidate Features
- creator_holder_share_drop_after_20k
- creator_sell_count_after_20k
- distribution_before_drawdown_proxy
- sell_pressure_from_early_buyers_after_20k
- top_10_holder_share_drop_after_20k
- top_holder_share_drop_after_20k

## Recommended Next Reports/Theses
- Repeated Buyer Runner Participation Descriptive Report: formal descriptive report with frozen proxy definitions
- Funder Link Proxy Expansion Sprint: scale bounded funding-link enrichment before thesis work
- Structural Runner Fingerprint Report With Visible And Hidden Layers: combine valuation efficiency with available structural proxies

## Limitations
- This is a descriptive discovery report, not a thesis or validation result.
- All valuation language uses FDV proxy, not true market capitalization.
- Holder-state rows are observed delta replay when present, not confirmed full-chain snapshots.
- Funding-link data is partial pilot data unless coverage reaches the expanded cohort.
- Address-level top-holder and complete graph features remain blocked when address lists are unavailable.
- Funding-link coverage is 0.0450.

## Artifacts
- Summary JSON: /Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/structural_wallet_anatomy/structural_wallet_anatomy_summary.json
- Summary Markdown: /Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/structural_wallet_anatomy/structural_wallet_anatomy_summary.md
- Availability Markdown: /Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/structural_wallet_anatomy/structural_wallet_data_availability.md
- Feasibility CSV: /Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/structural_wallet_anatomy/structural_feature_feasibility.csv
- Tier comparison CSV: /Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/structural_wallet_anatomy/structural_milestone_tier_comparison.csv
- Entry/exit CSV: /Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/structural_wallet_anatomy/entry_vs_exit_structural_features.csv
- Gap plan CSV: /Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/structural_wallet_anatomy/structural_data_gap_plan.csv

Next action: formal descriptive report with frozen proxy definitions
