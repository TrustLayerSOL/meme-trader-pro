# P0 Helius Enrichment Planners Status

## Why These Planners Were Created
The structural enrichment master plan requires capped dry-run planners before any Helius collection for top-holder, early-buyer wallet history, and creator/funder transfer graph fields.

Overall classification: `p0_helius_planners_ready_for_user_review`

## Pilots Included
- top_holder_milestone_snapshot_pilot: targets={'mints_selected': 250, 'milestone_snapshots_selected': 753}, projected_credits=20000, readiness=planner_ready_for_review
- early_buyer_wallet_history_pilot: targets={'wallets_selected': 1000, 'launches_covered': 117}, projected_credits=25000, readiness=planner_ready_for_review
- creator_funder_transfer_graph_pilot: targets={'creators_selected': 37, 'candidate_funders_selected': 41, 'launches_covered': 250}, projected_credits=25000, readiness=planner_ready_for_review

Combined projected credits: 70000

## First Executed Pilot
The early-buyer wallet-history pilot was executed as the first capped P0 pilot.

- selected_wallets: `1000`
- wallets_completed: `1000`
- wallets_with_prior_history: `880`
- launches_covered: `117`
- requests_used: `1000`
- network_calls_made: `1000`
- transactions_fetched: `19769`
- prior_history_coverage_pct: `88.0`
- readiness_classification: `early_buyer_history_ready_for_review`
- warnings: `[]`

## Top-Holder Replay Pilot
The top-holder replay pilot was executed as a bounded source-yield test. This uses mint transaction balance-delta replay and is not a confirmed full-chain historical account-state snapshot.

- selected_mints: `25`
- selected_milestones: `75`
- mints_completed: `25`
- milestones_completed: `75`
- requests_used: `49`
- network_calls_made: `49`
- transactions_fetched: `754`
- milestones_with_holder_proxy: `75`
- replay_proxy_coverage_pct: `100.0`
- readiness_classification: `top_holder_replay_ready_for_review`
- warnings: `[]`

## Creator/Funder Transfer Graph Pilot
The creator/funder transfer graph pilot was executed as the final capped P0 structural enrichment pilot. This uses neutral creator/funder structural proxy labels only.

- creators_selected: `37`
- candidate_funders_selected: `41`
- launches_covered: `250`
- creators_attempted: `37`
- creators_completed: `37`
- requests_used: `125`
- actual_helius_credits_estimate: `125`
- transactions_fetched: `7471`
- raw_responses_preserved: `7000`
- candidate_funder_coverage_pct: `99.2`
- shared_funder_coverage_pct: `92.8`
- time_linked_funding_coverage_pct: `92.8`
- creator_to_early_buyer_links_found: `0`
- creator_to_top_holder_links_found: `0`
- readiness_classification: `creator_funder_graph_ready_for_review`
- warnings: `[]`

## Warning
The executed pilots did not run a thesis, validation, backtest, paper trading, live trading, optimization, grid search, or ML workflow. Top-holder replay fields remain proxy fields unless validated against a confirmed historical account-state source. Creator/funder fields are structural proxies, not identity or unsupported relation labels.

## Next Recommended Action
Build a combined structural proxy audit that joins early-buyer wallet history, top-holder replay, and creator/funder transfer graph outputs before any thesis or outcome comparison.

## Artifacts
- Summary JSON: /Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/p0_helius_planners/p0_helius_planner_summary.json
- Summary Markdown: /Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/p0_helius_planners/p0_helius_planner_summary.md
- Budget Projection: /Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/p0_helius_planners/p0_helius_budget_projection.csv
- Top Holder Targets: /Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/p0_helius_planners/top_holder_snapshot_targets.csv
- Early Buyer Targets: /Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/p0_helius_planners/early_buyer_wallet_history_targets.csv
- Creator/Funder Targets: /Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/p0_helius_planners/creator_funder_transfer_graph_targets.csv
- Early Buyer Pilot Summary JSON: /Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/p0_early_buyer_wallet_history_pilot/early_buyer_wallet_history_pilot_summary.json
- Early Buyer Pilot Summary Markdown: /Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/p0_early_buyer_wallet_history_pilot/early_buyer_wallet_history_pilot_summary.md
- Early Buyer Parsed JSONL: /Volumes/ORICO/MemeTraderPro/data/backtests/structural_enrichment/early_buyer_wallet_history_pilot.jsonl
- Early Buyer Parsed Parquet: /Volumes/ORICO/MemeTraderPro/data/backtests/structural_enrichment/early_buyer_wallet_history_pilot.parquet
- Early Buyer Raw Transactions: /Volumes/ORICO/MemeTraderPro/data/raw/structural_enrichment/early_buyer_wallet_history_pilot/early_buyer_wallet_history_raw_transactions.jsonl
- Top Holder Replay Summary JSON: /Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/p0_top_holder_replay_pilot/top_holder_replay_pilot_summary.json
- Top Holder Replay Summary Markdown: /Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/p0_top_holder_replay_pilot/top_holder_replay_pilot_summary.md
- Top Holder Replay JSONL: /Volumes/ORICO/MemeTraderPro/data/backtests/structural_enrichment/top_holder_replay_pilot.jsonl
- Top Holder Replay Parquet: /Volumes/ORICO/MemeTraderPro/data/backtests/structural_enrichment/top_holder_replay_pilot.parquet
- Top Holder Replay Raw Transactions: /Volumes/ORICO/MemeTraderPro/data/raw/structural_enrichment/top_holder_replay_pilot/top_holder_replay_raw_transactions.jsonl
- Creator/Funder Graph Summary JSON: /Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/p0_creator_funder_transfer_graph_pilot/creator_funder_transfer_graph_pilot_summary.json
- Creator/Funder Graph Summary Markdown: /Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/p0_creator_funder_transfer_graph_pilot/creator_funder_transfer_graph_pilot_summary.md
- Creator/Funder Graph JSONL: /Volumes/ORICO/MemeTraderPro/data/backtests/structural_enrichment/creator_funder_transfer_graph_pilot.jsonl
- Creator/Funder Graph Parquet: /Volumes/ORICO/MemeTraderPro/data/backtests/structural_enrichment/creator_funder_transfer_graph_pilot.parquet
- Creator/Funder Graph Raw Transactions: /Volumes/ORICO/MemeTraderPro/data/raw/structural_enrichment/creator_funder_transfer_graph_pilot/creator_funder_transfer_graph_raw_transactions.jsonl
- Creator/Funder Graph Checkpoint: /Volumes/ORICO/MemeTraderPro/data/backtests/structural_enrichment/creator_funder_transfer_graph_checkpoint.json
