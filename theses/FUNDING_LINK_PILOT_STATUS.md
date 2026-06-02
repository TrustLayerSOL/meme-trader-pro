# Funding Link Pilot Status

- Readiness classification: `funding_link_ready_for_T009`
- T009 feasible: `True`
- Creators planned: `50`
- Creators attempted: `50`
- Creators completed: `50`
- Launches covered: `667`
- Requests used: `67`
- Transactions fetched: `1880`
- Raw transactions preserved: `1870`
- Funding source coverage: `{'coverage_pct': 37.4813, 'covered_launches': 250, 'total_launches': 667}`
- Repeated funder coverage: `{'coverage_pct': 35.0825, 'launches_with_repeated_funder': 234, 'unique_repeated_funders': 25}`
- Warnings: `[]`

## Output Paths

- Funding JSONL: `/Volumes/ORICO/MemeTraderPro/data/backtests/funding_link/funding_link_pilot.jsonl`
- Funding parquet: `/Volumes/ORICO/MemeTraderPro/data/backtests/funding_link/funding_link_pilot.parquet`
- Raw transactions: `/Volumes/ORICO/MemeTraderPro/data/backtests/funding_link/raw/funding_link_pilot_raw_transactions.jsonl`
- Report JSON: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/funding_link_pilot/funding_link_pilot_summary.json`
- Report markdown: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/funding_link_pilot/funding_link_pilot_summary.md`
- Checkpoint: `/Volumes/ORICO/MemeTraderPro/data/backtests/funding_link/funding_link_pilot_checkpoint.json`

## Guardrails

- This was a bounded data-enrichment pilot only.
- No thesis was run.
- No outcome comparison, validation, backtest, paper/live trading, trading logic, optimization, grid search, or ML workflow was run.

## Next Recommendation

Design T009 Funding Lineage as a separate descriptive thesis plan. Do not run T009 until the feature definitions and leakage rules are documented.
