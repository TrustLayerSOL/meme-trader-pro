# T011 Explosive Runner Raw-Flow Robustness Status

- Original T011 classification: `descriptive_signal_present`
- Robustness classification: `robust_descriptive_signal`
- $20k trigger count analyzed: `422`

## Chronological Result

- Halves direction stable: `True`
- Thirds direction stable: `False`

## Trigger Sensitivity Result

- 15k: True (448 rows), 20k: True (422 rows), 30k: True (395 rows)

## Outlier Sensitivity Result

- Top 1% exclusion stable: `True`
- Top 5% exclusion stable: `True`
- $1M+ exclusion stable: `True`

## Creator / Date Dominance Result

- Dominant creator exclusion stable: `True`
- Top date exclusion stable: `True`

## Low-Flow Interpretation

- Refined pattern: `low_total_flow_with_high_fdv_efficiency`
- Active-wallet refinement: `low_total_flow_and_lower_event_density_per_wallet`

## Validation Recommendation

- Validation design recommended: `True`
- No validation was run.

## Limitations

- FDV/valuation proxy is used; true market-cap claims remain blocked.
- This is a robustness review only, not validation or thesis promotion.
- Trigger sensitivity uses fixed $15k/$20k/$30k thresholds and does not optimize trigger choice.
- Holder/entity/funding overlays are partial-coverage context only.
- Snapshot timing around fast crossings may still compress the apparent trigger path.

## Outputs

- JSON summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T011_explosive_runner_raw_flow_robustness/T011_explosive_runner_raw_flow_robustness_summary.json`
- Markdown summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T011_explosive_runner_raw_flow_robustness/T011_explosive_runner_raw_flow_robustness_summary.md`
- Split table: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T011_explosive_runner_raw_flow_robustness/robustness_split_table.csv`

## Next Recommendation

Design a formal validation plan for T011, but do not run validation in this sprint.
