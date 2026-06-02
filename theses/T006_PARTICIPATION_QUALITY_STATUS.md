# T006 Participation Quality Status

## Thesis Description

Do participation-quality ratios add descriptive information beyond raw activity and flow counts?

## Dataset Used

- Strict launch-regime FDV-proxy lifecycle dataset
- Launches analyzed: `1500`

## Feature Coverage

- `launch_id`: `100.00%`
- `mint`: `100.00%`
- `block_time`: `100.00%`
- `snapshot label / snapshot age`: `100.00%`
- `buy_count`: `100.00%`
- `sell_count`: `100.00%`
- `event_count`: `100.00%`
- `active_wallets`: `100.00%`
- `unique_actors`: `100.00%`
- `liquidity_proxy`: `100.00%`
- `FDV-proxy runup`: `100.00%`
- `FDV-proxy drawdown`: `100.00%`
- `120m price availability`: `100.00%`
- `120m liquidity-proxy availability`: `100.00%`

## Outcome Coverage

- `fdv_proxy_runup_available`: `1500`
- `fdv_proxy_drawdown_available`: `1500`
- `price_available_120m`: `1500`
- `liquidity_proxy_available_120m`: `1500`

## Classification

`no_signal`

## Limitations

- T006 is descriptive only and does not produce trading rules.
- Participation quality ratios are proxies derived from lifecycle snapshots, not identity-resolved holder state.
- Intensity proxy features are not direct evidence of manipulation or wash trading.
- FDV proxy is not true market cap because circulating supply is unavailable.

## Comparison To T001-T005

- `T001`: `no_signal`
- `T002`: `weak_signal`
- `T003`: `no_signal`
- `T004`: `no_signal`
- `T005`: `weak_signal`
- `T006`: `no_signal`
- `comparison_note`: `Qualitative comparison only. T006 checks whether participation ratios add descriptive structure beyond raw T005 activity counts.`

## True Market-Cap Blocked Warning

True market-cap claims remain blocked; this report uses FDV proxy only.

## Next Recommendation

treat participation quality as descriptive-only and continue testing non-flow thesis families

- Markdown summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T006_participation_quality/T006_participation_quality_summary.md`
- JSON summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T006_participation_quality/T006_participation_quality_summary.json`
- No trading rules were generated.
- No profitability claims were generated.
- True market-cap claims remain blocked.
