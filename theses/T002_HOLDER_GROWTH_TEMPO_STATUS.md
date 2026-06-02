# T002 Holder Growth Tempo Status

## Thesis Description

Do healthier launches exhibit different holder-growth and participation-growth trajectories than unhealthy launches?

## Dataset Used

- Strict launch-regime FDV-proxy lifecycle dataset
- Launches analyzed: `1500`

## Feature Coverage

- `holder_count`: `0.00%`
- `active_wallets`: `100.00%`
- `buy_count`: `100.00%`
- `event_count`: `100.00%`

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
- True holder-count growth is unavailable; participation proxies are reported separately.

## Next Recommendation

add replay-safe holder-count snapshots before rerunning true holder-growth analysis

- Markdown summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T002_holder_growth_tempo/T002_holder_growth_tempo_summary.md`
- JSON summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T002_holder_growth_tempo/T002_holder_growth_tempo_summary.json`
- No trading rules were generated.
- No profitability claims were generated.
- True market-cap claims remain blocked.
