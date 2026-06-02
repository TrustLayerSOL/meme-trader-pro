# T011 EXPLOSIVE RUNNER RAW-FLOW CONTINUATION STATUS

## Thesis Description

T011 tests whether raw flow and participation features at the first observable $20k FDV-proxy crossing distinguish tokens that continue into higher explosive-runner tiers.

## Why Explosive Runner Continuation

Prior descriptive cycles exhausted several health, entity, and funding hypotheses. Winner anatomy showed enough higher-tier runner examples to formalize a continuation-focused descriptive thesis.

## Dataset Used

- Scope: `all_collected_fdv_proxy_lifecycle`
- Launches analyzed: `3000`
- Snapshots: `36000`
- Valuation semantics: `fdv_proxy_only`; true market-cap claims remain blocked.

## Trigger And Tier Counts

- $20k trigger count: `422`
- `reached_20k_but_never_50k`: `73`
- `reached_50k_but_never_100k`: `64`
- `reached_100k_but_never_200k`: `13`
- `reached_200k_but_never_500k`: `19`
- `reached_500k_but_never_1m`: `30`
- `reached_1m_plus`: `223`

## Feature Coverage

- `event_count_at_20k`: `100.0%`
- `buy_count_at_20k`: `100.0%`
- `active_wallets_at_20k`: `100.0%`
- `holder_count_at_20k`: `23.696682%`
- `repeated_actor_overlap_proxy`: `23.696682%`
- `funding_source_available`: `10.189573%`

## Strongest Feature Differences

- `1m_plus_vs_sub_1m` / `fdv_per_holder_at_20k` delta `3319074.0610826514`
- `100k_plus_vs_sub_100k` / `fdv_per_holder_at_20k` delta `501746.8636749885`
- `200k_plus_vs_100k_only` / `fdv_per_holder_at_20k` delta `489014.27235285204`
- `500k_plus_vs_100k_to_500k` / `fdv_per_holder_at_20k` delta `379892.0467301138`
- `100k_plus_vs_sub_100k` / `event_count_at_20k` delta `-12.0`
- `200k_plus_vs_100k_only` / `event_count_at_20k` delta `-10.0`

## Interpretive Checks

- Raw flow separates $100k+ / sub-$100k: `True`
- Raw flow separates $500k+ / $100k-$500k: `True`
- Active-wallet breadth helped: `True`
- Holder count helped: `True`
- Holder/FDV relationship helped: `True`
- Entity overlays helped: `True`
- Funding overlays helped where available: `False`

## Classification

- Final classification: `descriptive_signal_present`
- Chronological robustness recommended: `True`

## Limitations

- FDV/valuation proxy is used; true market-cap claims remain blocked.
- Features are descriptive at the first $20k FDV-proxy crossing and are not entry/exit rules.
- Holder state is observed-delta replay, not confirmed full-chain account state.
- Entity, migration, and funding overlays may have sidecar-limited coverage.
- Holder coverage at trigger: 23.696682%.

## Outputs

- JSON summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T011_explosive_runner_raw_flow/T011_explosive_runner_raw_flow_summary.json`
- Markdown summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T011_explosive_runner_raw_flow/T011_explosive_runner_raw_flow_summary.md`
- Tier feature table: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T011_explosive_runner_raw_flow/milestone_tier_feature_table.csv`
- Trigger feature rows: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T011_explosive_runner_raw_flow/trigger_20k_feature_rows.csv`

## Guardrails

- No trading rules were generated.
- No thesis promotion, validation, backtest, walk-forward, paper/live trading, optimization, grid search, or ML was run.

## Next Recommendation

Run a separate robustness-only review before any validation; do not promote this thesis from one descriptive result.
