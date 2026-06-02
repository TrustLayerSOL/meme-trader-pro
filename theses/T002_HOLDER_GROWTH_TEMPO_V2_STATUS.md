# T002 Holder Growth Tempo Status

## Thesis Description

Do healthier launches exhibit different holder-growth and participation-growth trajectories than unhealthy launches?

## Dataset Used

- Strict launch-regime FDV-proxy lifecycle dataset
- Holder-state snapshots: `/Volumes/ORICO/MemeTraderPro/data/backtests/holder_state/strict_cohort_holder_state_snapshots.jsonl`
- Launches analyzed: `1500`

## Feature Coverage

- `holder_count`: `41.59%`
- `active_wallets`: `100.00%`
- `buy_count`: `100.00%`
- `event_count`: `100.00%`
- `holder_growth_30s_to_3m` available launches: `1499`
- `holder_growth_30s_to_30m` available launches: `1496`

## Outcome Coverage

- `fdv_proxy_runup_available`: `1500`
- `fdv_proxy_drawdown_available`: `1500`
- `price_available_120m`: `1500`
- `liquidity_proxy_available_120m`: `1500`

## Classification

`weak_signal`

## Limitations

- FDV proxy is not true market cap because circulating supply is unavailable.
- This cycle is descriptive research only and does not produce trading rules.

## Next Recommendation

rerun with chronological validation before changing thesis status

- Markdown summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T002_holder_growth_tempo_v2/T002_holder_growth_tempo_summary.md`
- JSON summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T002_holder_growth_tempo_v2/T002_holder_growth_tempo_summary.json`
- No trading rules were generated.
- No profitability claims were generated.
- True market-cap claims remain blocked.
