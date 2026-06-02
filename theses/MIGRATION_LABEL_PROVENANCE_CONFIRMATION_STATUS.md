# Migration Label Provenance Confirmation Status

- Confirmation targets attempted: `234`
- Confirmation targets completed: `234`
- Helius requests used: `363`
- Signatures fetched: `14057`
- Transactions fetched: `14057`
- Raw transactions preserved: `14057`
- Confirmed Pump.fun migrate labels found: `11`
- Targets not confirmed in window: `223`
- Warnings: `[]`

## Output Paths

- Candidate labels: `/Volumes/ORICO/MemeTraderPro/data/backtests/migration_graduation/provenance_confirmation_candidates.jsonl`
- Candidate parquet: `/Volumes/ORICO/MemeTraderPro/data/backtests/migration_graduation/provenance_confirmation_candidates.parquet`
- Raw transactions: `/Volumes/ORICO/MemeTraderPro/data/backtests/migration_graduation/provenance_confirmation_raw/migration_graduation_raw_transactions.jsonl`
- Collection report JSON: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/migration_label_provenance_confirmation/migration_graduation_collection_summary.json`
- Collection report markdown: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/migration_label_provenance_confirmation/migration_graduation_collection_summary.md`
- Provenance-upgraded labels: `/Volumes/ORICO/MemeTraderPro/data/backtests/migration_graduation/combined_migration_graduation_labels_provenance_upgraded.jsonl`

## Result

The bounded confirmation collection improved provenance modestly but did not resolve the source-quality blocker. The upgraded label set still depends mainly on DexScreener proxy labels: `15` ground-truth Pump.fun migrate labels versus `223` DexScreener proxy labels.

## Guardrails

- Read-only Helius collection only.
- No thesis promotion was performed.
- No validation, walk-forward, backtest, or trading logic was run.
- DexScreener pair detection remains proxy evidence only.

## Next Recommendation

Do not validate T008 yet. Either park T008 or improve migration-label quality with a different non-DexScreener source/parser before further testing.
