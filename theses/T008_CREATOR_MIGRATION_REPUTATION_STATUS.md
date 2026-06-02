# T008 Creator Migration Reputation Status

## Thesis Description

Does leakage-safe creator migration/graduation history show a descriptive relationship with all-collected FDV-proxy lifecycle outcomes?

## Dataset Used

- All-collected 3,000-launch FDV-proxy lifecycle dataset
- Strict-only T008 was not run because strict 4+ prior history remains empty.
- Launches analyzed: `3000`

## Feature Coverage

- `creator_prior_migration_count`: `3000` available, `100.00%` coverage
- `creator_prior_graduation_count`: `3000` available, `100.00%` coverage
- `creator_prior_migration_or_graduation_count`: `3000` available, `100.00%` coverage
- `creator_has_prior_migration_or_graduation`: `3000` available, `100.00%` coverage
- `creator_has_2plus_prior_migrations_or_graduations`: `3000` available, `100.00%` coverage
- `creator_has_4plus_prior_migrations_or_graduations`: `3000` available, `100.00%` coverage
- `creator_prior_launch_count`: `3000` available, `100.00%` coverage
- `creator_prior_migration_or_graduation_rate`: `1952` available, `65.07%` coverage
- `creator_prior_last_migration_or_graduation_age_seconds`: `329` available, `10.97%` coverage

## Prior Migration / Graduation Bucket Counts

- `0`: `2671`
- `1`: `138`
- `2_to_3`: `133`
- `4_plus`: `58`

## Outcome Coverage

- `fdv_proxy_runup_available`: `3000`
- `fdv_proxy_drawdown_available`: `3000`
- `price_available_120m`: `3000`
- `liquidity_proxy_available_120m`: `3000`

## Classification

`weak_signal`

## Migration Versus Raw Prior Launch Count

`raw_prior_launch_count_more_informative_descriptively`

## Source Split

- `pumpfun_migration_event`: `15`
- `dexscreener_pair_detection`: `234`
- `other_combined_label`: `0`

## Robustness Caveats

- `four_plus_bucket_dominant_creator_share`: `0.7586`
- `two_plus_bucket_dominant_creator_share`: `0.5550`
- `source_sensitivity_interpretation`: `both_source_sensitivities_available`

## Limitations

- This is descriptive research only and does not produce trading rules.
- DexScreener pair detection is a graduation proxy and may carry survivorship/source bias.
- Pump.fun migration labels are sparse relative to DexScreener pair-detected labels.
- FDV proxy is not true market cap because circulating supply remains unavailable.
- Current launch migration/graduation outcome is reported separately from prior-history features.

## Next Recommendation

run a separate chronological and source-robustness review for T008 before any validation design

- Markdown summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T008_creator_migration_reputation/T008_creator_migration_reputation_summary.md`
- JSON summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T008_creator_migration_reputation/T008_creator_migration_reputation_summary.json`
- No thesis promotion was performed.
- No trading rules were generated.
- No profitability claims were generated.
- True market-cap claims remain blocked.
