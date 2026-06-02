# T002 Holder Growth Tempo v2 Robustness Status

## Original Classification

`weak_signal`

## Robustness Classification

`no_robust_signal`

## Dataset Used

- Strict launch-regime FDV-proxy lifecycle dataset
- Holder-state snapshots: `/Volumes/ORICO/MemeTraderPro/data/backtests/holder_state/strict_cohort_holder_state_snapshots.jsonl`
- Launches analyzed: `1500`

## Split Definitions

- Chronological halves: `{'first_half': 750, 'second_half': 750}`
- Chronological thirds: `{'first_third': 500, 'middle_third': 500, 'final_third': 500}`
- Weekly and monthly buckets are reported with counts and not overinterpreted when small.

## Feature Coverage

- `holder_growth_30s_to_3m`: `1499` available, `99.93%` coverage
- `holder_growth_3m_to_10m`: `1497` available, `99.80%` coverage
- `holder_growth_10m_to_30m`: `1496` available, `99.73%` coverage
- `holder_growth_30s_to_30m`: `1496` available, `99.73%` coverage
- `holder_count_30s`: `1499` available, `99.93%` coverage
- `holder_count_3m`: `1499` available, `99.93%` coverage
- `holder_count_10m`: `1497` available, `99.80%` coverage
- `holder_count_30m`: `1496` available, `99.73%` coverage
- `holder_retention_proxy`: `1099` available, `73.27%` coverage
- `holder_churn_proxy`: `1496` available, `99.73%` coverage

## Outcome Coverage

- `fdv_proxy_runup_available`: `1500`
- `fdv_proxy_drawdown_available`: `1500`
- `price_available_120m`: `1500`
- `liquidity_proxy_available_120m`: `1500`

## Outlier Sensitivity Result

`{'primary_feature': 'holder_growth_30s_to_30m', 'outlier_views_consistent_count': 0, 'outlier_view_count': 3}`

## Chronological Consistency Result

`{'halves_consistent_count': 0, 'thirds_consistent_count': 0, 'primary_feature': 'holder_growth_30s_to_30m'}`

## Limitations

- This is a descriptive robustness review only.
- FDV proxy is not true market cap.
- Holder state is observed delta replay, not confirmed full-chain account state.
- No thesis promotion or validation design was executed.

## Next Recommendation

park T002 v2 and prioritize manipulation/entity enrichment before further thesis cycles

- Markdown summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T002_holder_growth_tempo_v2_chronological_robustness/T002_holder_growth_chronological_robustness_summary.md`
- JSON summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T002_holder_growth_tempo_v2_chronological_robustness/T002_holder_growth_chronological_robustness_summary.json`
- No thesis promotion was performed.
- No trading rules were generated.
- True market-cap claims remain blocked.
