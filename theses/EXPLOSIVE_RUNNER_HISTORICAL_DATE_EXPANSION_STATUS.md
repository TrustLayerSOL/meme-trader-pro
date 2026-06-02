# Explosive Runner Historical Date Expansion Status

## Why Expand Dates

T011 validation failed because the selected holdout bucket was date-dominated. The project must broaden historical dates before rerunning winner anatomy, T011, robustness, or validation.

## Current Limitation

- Current $20k-trigger sample has only `3` unique dates.
- The validation holdout was entirely `2026-06-01`.

## Preferred Target

- `30+` unique $20k-trigger dates
- `1,000+` total $20k-trigger rows
- median at least `10` rows per active date
- no single date above `35%`
- top 3 dates below `60%`
- forward path coverage at least `90%`

## Sources Audited

- Existing local normalized events beyond current all-collected sample: `blocked`
- Raw launch census not yet included in all-collected sample: `usable_with_enrichment`
- Pump.fun create-event census: `usable_with_enrichment`
- PumpSwap/Pump.fun transaction archives: `usable_with_parser_repair`
- DexScreener pair detection records: `usable_with_enrichment`
- Helius historical transaction fetch: `needs_external_fetch`
- DexScreener current/pair API: `needs_external_fetch`
- Other cached ORICO project files: `usable_with_parser_repair`

## Expansion Path Chosen

- `parallel Helius/Pump.fun historical acquisition by date shard`
- Use the faster parallel date-sharded pull design. Do not run a slow serial acquisition for the next large pull.

## Coverage Result

- Expanded $20k-trigger dates: `3`
- Expanded $20k-trigger rows: `422`
- Top date share: `0.7630331753554502`
- Top 3 date share: `1.0`
- Readiness: `historical_expansion_requires_external_acquisition`

## Outputs

- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/historical_date_expansion/historical_coverage_audit.json`
- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/historical_date_expansion/historical_coverage_audit.md`
- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/historical_date_expansion/historical_date_expansion_summary.json`
- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/historical_date_expansion/historical_date_expansion_summary.md`
- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/historical_date_expansion/historical_expansion_plan.json`
- `/Volumes/ORICO/MemeTraderPro/data/backtests/explosive_runner_expanded/expanded_launches.parquet`
- `/Volumes/ORICO/MemeTraderPro/data/backtests/explosive_runner_expanded/expanded_lifecycle_snapshots.parquet`
- `/Volumes/ORICO/MemeTraderPro/data/backtests/explosive_runner_expanded/expanded_trigger_labels.parquet`
- `/Volumes/ORICO/MemeTraderPro/data/backtests/explosive_runner_expanded/expanded_trigger_labels.jsonl`

## Next Recommended Action

Run a bounded external acquisition pilot using parallel date shards. Do not rerun winner anatomy, T011, or validation until the preferred date-balance target is met.
