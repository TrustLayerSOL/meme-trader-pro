# T008 Creator Migration Reputation Status

## Thesis Description

Does a creator's prior migration/graduation history have a descriptive relationship with launch lifecycle outcomes?

This thesis is intended to evaluate the practical creator-reputation filter:

- same creator only
- migration/graduation timestamp must exist
- prior migration/graduation must be strictly before the current launch
- missing timestamps are not counted
- no future leakage

## Current Readiness

`creator_migration_reputation_ready_for_all_collected_descriptive_thesis`

T008 is ready for an all-collected descriptive thesis run only.

T008 is not ready for a strict launch-regime-only thesis because the strict `4+ prior migrations` cohort remains empty.

## Dataset Scope

Allowed T008 dataset:

- all-collected launch cohort
- `3,000` launches
- combined Pump.fun migration and DexScreener pair-detection graduation labels
- FDV-proxy lifecycle outcomes only

Blocked T008 dataset:

- strict launch-regime-only cohort
- `1,500` launches
- blocked because strict launches with `4+` prior migrations = `0`

## Evidence Inputs

- Pump.fun 7d latest-first migration labels: `/Volumes/ORICO/MemeTraderPro/data/backtests/migration_graduation/migration_graduation_7d_desc_candidates.jsonl`
- DexScreener pair-detection graduation labels: `/Volumes/ORICO/MemeTraderPro/data/backtests/migration_graduation/dexscreener_pair_graduation_labels.jsonl`
- Combined labels: `/Volumes/ORICO/MemeTraderPro/data/backtests/migration_graduation/combined_migration_graduation_labels.jsonl`

## Readiness Metrics

| Metric | Value |
|---|---:|
| Strict launches | `1,500` |
| All-collected launches | `3,000` |
| Unique migrated/graduated mints observed | `238` |
| Strict unique migrated/graduated mints observed | `20` |
| Migration/graduation timestamp available count | `249` |
| Creators with at least 1 migration/graduation event | `180` |
| Strict launches with at least 1 prior migration/graduation | `20` |
| Strict launches with 4+ prior migrations/graduations | `0` |
| All-collected launches with at least 1 prior migration/graduation | `329` |
| All-collected launches with 4+ prior migrations/graduations | `58` |

## Caveats

- DexScreener pair detection is a graduation proxy, not a confirmed Pump.fun migrate instruction.
- True market-cap claims remain blocked.
- The run must remain descriptive: no trading rules, no profitability claims, no threshold optimization, no grid search, no ML, no thesis promotion.
- The `4+ prior migrations` cutoff is a user-provided practical filter, not an optimized threshold.
- Strict-regime conclusions remain blocked until that cohort has non-empty `4+` prior migration coverage.

## Next Allowed Command

Implement and run T008 as an all-collected descriptive thesis only, using the combined migration/graduation labels:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_creator_migration_reputation_thesis \
  --dataset all-collected \
  --migration-labels-path /Volumes/ORICO/MemeTraderPro/data/backtests/migration_graduation/combined_migration_graduation_labels.jsonl
```

The command does not exist yet and must be implemented with tests before running.

## Guardrails

- No paper trading.
- No live trading.
- No auto-buy/sell.
- No wallet execution.
- No profitability claims.
- No entry/exit logic.
- No threshold optimization.
- No grid search.
- No ML black boxes.
- No thesis promotion from a single result.
- No future leakage.

## Report Paths

- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/dexscreener_pair_graduation_enrichment/dexscreener_pair_graduation_enrichment.json`
- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/creator_migration_reputation_feasibility_combined_labels_v2/creator_migration_reputation_feasibility.json`
- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/creator_migration_reputation_feasibility_combined_labels_v2/creator_migration_reputation_feasibility.md`

## Recommendation

Proceed to implement T008 as a descriptive all-collected thesis. Do not run strict-only T008 yet.
