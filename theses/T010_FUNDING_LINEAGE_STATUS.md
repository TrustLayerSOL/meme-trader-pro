# T010 FUNDING LINEAGE STATUS

## Thesis Description

Creator pre-launch funding lineage may have descriptive relationship with FDV-proxy lifecycle outcomes.

## Dataset

- Dataset used: `funding_link_pilot_coverage_universe`
- Launch count: `667`
- Funding-link coverage: `{'launches_analyzed': 667, 'funding_source_available_count': 250, 'funding_source_available_pct': 37.481259, 'repeated_funder_count': 234, 'repeated_funder_pct': 35.082459, 'unique_repeated_funders': 25}`

## Feature Coverage

- Candidate funding wallet: `{'available_rows': 250, 'missing_rows': 417, 'coverage_pct': 37.481259}`
- Funding age seconds: `{'available_rows': 250, 'missing_rows': 417, 'coverage_pct': 37.481259}`
- Launches sharing funder: `{'available_rows': 667, 'missing_rows': 0, 'coverage_pct': 100.0}`

## Classification

- Classification: `no_signal`
- Larger funding-link rollout recommended: `False`
- Chronological robustness recommended: `False`

## Comparison To T005/T008/T009

- T005: `weak_signal`
- T008: `unstable_weak_signal`
- T009: `no_signal`

## Limitations

- Funding lineage is limited to the 50-creator, 667-launch pilot universe.
- FDV proxy outcomes are used; true market-cap claims remain blocked.
- This is descriptive only and does not create a trading rule.
- Repeated funders are deterministic candidate funders, not unsupported manipulation labels.
- Funding source coverage is partial; unavailable rows are not assumed clean or unfunded.

## Guardrails

- No thesis promotion was made.
- No validation, backtest, walk-forward, paper/live trading, trading logic, optimization, grid search, or ML workflow was run.
- No trading rules were generated.

## Outputs

- Markdown summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T010_funding_lineage/T010_funding_lineage_summary.md`
- JSON summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T010_funding_lineage/T010_funding_lineage_summary.json`

## Next Recommendation

Park funding-lineage thesis promotion and review whether broader data sources are justified.
