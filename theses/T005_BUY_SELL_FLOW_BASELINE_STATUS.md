# T005 Buy/Sell Flow Baseline Status

## Thesis Description

Do early buy/sell flow features have any descriptive relationship with FDV-proxy outcome quality?

## Baseline/Control Framing

T005 is a baseline/control thesis for quantifying simple flow behavior, not a priority alpha thesis.

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

`weak_signal`

## Limitations

- T005 is a baseline/control thesis and does not produce trading rules.
- Simple flow features can be noisy and outlier-sensitive.
- FDV proxy is not true market cap because circulating supply is unavailable.

## Comparison To T001-T004

- `T001`: `no_signal`
- `T002`: `weak_signal`
- `T003`: `no_signal`
- `T004`: `no_signal`
- `T005`: `weak_signal`
- `comparison_note`: `Qualitative baseline/control comparison only; no thesis promotion is made.`

## True Market-Cap Blocked Warning

True market-cap claims remain blocked; this report uses FDV proxy only.

## Next Recommendation

keep simple flow as baseline/control and compare against stronger non-flow thesis families

- Markdown summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T005_buy_sell_flow_baseline/T005_buy_sell_flow_baseline_summary.md`
- JSON summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T005_buy_sell_flow_baseline/T005_buy_sell_flow_baseline_summary.json`
- No trading rules were generated.
- No profitability claims were generated.
- True market-cap claims remain blocked.
