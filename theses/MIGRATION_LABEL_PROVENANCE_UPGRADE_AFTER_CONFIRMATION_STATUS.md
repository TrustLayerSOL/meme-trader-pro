# Migration Label Provenance Upgrade Status

- Readiness classification: `migration_label_provenance_needs_non_dexscreener_evidence`
- Ground-truth Pump.fun migrate labels: `15`
- DexScreener proxy labels: `223`
- Selected confirmation targets: `223`
- Estimated request-equivalent calls high: `669`

## Guardrails

- The after-confirmation provenance audit itself made no network calls.
- The bounded confirmation collection immediately before this audit used Helius read-only calls.
- Helius requests used by confirmation collection: `363`.
- Confirmation collection warnings: `[]`.
- No thesis was promoted.
- No validation, walk-forward, backtest, or trading logic was run.
- DexScreener pair detection remains proxy evidence only.

## Next Recommendation

review selected targets, then run a bounded non-DexScreener migration confirmation collection

- Markdown summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/migration_label_provenance_upgrade_after_confirmation/migration_label_provenance_upgrade_summary.md`
- JSON summary: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/migration_label_provenance_upgrade_after_confirmation/migration_label_provenance_upgrade_summary.json`
