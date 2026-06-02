# Repeated Buyer Runner Participation Status

## Why This Report Was Created
This report checks whether historical runner wallets appear among early buyers before new explosive FDV-proxy runners, and whether that repeated-buyer layer helps explain FDV efficiency.

Readiness classification: `repeated_buyer_report_needs_enrichment`

## Data Coverage
- Launches analyzed: 14809
- Events audited: 674173
- Early-buyer coverage before 20k: 0.0502
- Repeated-runner buyer coverage before 20k: 0.0269

## Repeated-Buyer Feature Definitions
- Prior history is leakage-safe: only launches with earlier launch_time are counted.
- repeated_buyer_proxy fields aggregate early buyer prior runner participation.
- wallet_quality_proxy fields are descriptive proxies only.

## Milestone Tier Findings
- 1m_plus_vs_sub_1m / before_20k_max_buyer_prior_runner_count: higher (strong_descriptive_difference)
- 1m_plus_vs_sub_1m / at_20k_max_buyer_prior_runner_count: higher (strong_descriptive_difference)
- 1m_plus_vs_sub_1m / before_50k_max_buyer_prior_runner_count: higher (strong_descriptive_difference)
- 100k_plus_vs_sub_100k / before_20k_max_buyer_prior_runner_count: higher (strong_descriptive_difference)
- 100k_plus_vs_sub_100k / at_20k_max_buyer_prior_runner_count: higher (strong_descriptive_difference)
- 100k_plus_vs_sub_100k / before_50k_max_buyer_prior_runner_count: higher (strong_descriptive_difference)

## Interaction With FDV Efficiency
- fdv_per_event_at_20k: sharpens=True
- fdv_per_buy_at_20k: sharpens=True
- fdv_per_active_wallet_at_20k: sharpens=True

## Entry-Side vs Exit-Side Summary
- before_20k, first_60s, and first_120s fields are entry-side observable proxies.
- before_50k fields are post-trigger-only for this report.

## Recommended Next Action
B. Full structural runner fingerprint report combining repeated buyers + FDV efficiency

## Limitations
- This is not a trading signal, validation result, or thesis promotion.
- All valuation fields use FDV proxy, not true market capitalization.
- Wallet prior participation is derived from observed lifecycle events only.
- Buyer identity coverage depends on deterministic actor fields in normalized events.
- Quantile buckets are descriptive and not optimized.
- Before-20k early-buyer coverage is 0.0502.

## Artifacts
- Summary JSON: /Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/repeated_buyer_runner_participation/repeated_buyer_runner_participation_summary.json
- Summary Markdown: /Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/repeated_buyer_runner_participation/repeated_buyer_runner_participation_summary.md
- Tier comparison CSV: /Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/repeated_buyer_runner_participation/repeated_buyer_tier_comparison.csv
- FDV interaction CSV: /Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/repeated_buyer_runner_participation/fdv_efficiency_repeated_buyer_interaction.csv
