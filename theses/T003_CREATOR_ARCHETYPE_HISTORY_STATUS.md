# T003 Creator Archetype History Status

## Thesis Description

Do creators/deployers leave repeatable historical fingerprints that are associated with launch outcomes?

## Dataset Used

- Strict launch-regime FDV-proxy lifecycle dataset
- Launches analyzed: `1500`
- Creator count: `583`
- Repeat creator count: `171`

## Feature Coverage

- `creator`: `100.00%`
- `deployer`: `100.00%`
- `mint`: `100.00%`
- `launch_id`: `100.00%`
- `block_time`: `100.00%`
- `FDV-proxy outcomes`: `100.00%`
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

- FDV proxy is not true market cap because circulating supply is unavailable.
- This cycle is descriptive research only and does not produce trading rules.
- Creator/deployer history is limited to creators visible in the strict launch-regime dataset.

## Leakage Controls

- Rows are sorted by block_time before history construction.
- A creator's current launch is added to history only after its features are computed.
- Creator quality history uses only prior rows where prior.block_time < current.block_time.
- Same-timestamp launches do not count as prior history.

## Next Recommendation

rerun with broader chronological launch census before any thesis status change

- Markdown summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T003_creator_archetype_history/T003_creator_archetype_history_summary.md`
- JSON summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T003_creator_archetype_history/T003_creator_archetype_history_summary.json`
- No trading rules were generated.
- No profitability claims were generated.
- True market-cap claims remain blocked.
