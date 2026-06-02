# T004 Liquidity Persistence Status

## Thesis Description

Do launches with stronger early liquidity-proxy persistence and healthier liquidity trajectory have better FDV-proxy lifecycle outcomes?

## Dataset Used

- Strict launch-regime FDV-proxy lifecycle dataset
- Launches analyzed: `1500`

## Liquidity Proxy Semantics

- Dominant source: `bonding_curve_post_balance`
- Exact semantics: liquidity_proxy is treated as a bonding-curve reserve/balance proxy when source is bonding_curve_post_balance; it is not confirmed DEX order-book depth.
- Confirmed DEX depth: `False`

## Feature Coverage

- `launch_id`: `100.00%`
- `mint`: `100.00%`
- `block_time`: `100.00%`
- `snapshot age / snapshot label`: `100.00%`
- `liquidity_proxy`: `100.00%`
- `bonding_curve_post_balance`: `100.00%`
- `price/FDV proxy fields`: `100.00%`
- `120m liquidity-proxy availability`: `100.00%`
- `120m price availability`: `100.00%`
- `FDV-proxy runup`: `100.00%`
- `FDV-proxy drawdown`: `100.00%`

## Outcome Coverage

- `fdv_proxy_runup_available`: `1500`
- `fdv_proxy_drawdown_available`: `1500`
- `price_available_120m`: `1500`
- `liquidity_proxy_available_120m`: `1500`

## Classification

`no_signal`

## Limitations

- Liquidity proxy is not confirmed DEX order-book depth.
- FDV proxy is not true market cap because circulating supply is unavailable.
- This cycle is descriptive research only and does not produce trading rules.

## True Market-Cap Blocked Warning

True market-cap claims remain blocked; this report uses FDV proxy only.

## Next Recommendation

keep liquidity proxy as descriptive diagnostic and test next thesis family

- Markdown summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T004_liquidity_persistence/T004_liquidity_persistence_summary.md`
- JSON summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T004_liquidity_persistence/T004_liquidity_persistence_summary.json`
- No trading rules were generated.
- No profitability claims were generated.
- True market-cap claims remain blocked.
