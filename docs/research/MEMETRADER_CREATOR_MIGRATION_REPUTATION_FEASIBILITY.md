# MemeTraderPro Creator Migration Reputation Feasibility

## Executive Answer

Question: do we already have enough data to compute prior migration count per creator, leakage-safely, before each launch?

Answer: **partially**.

The repo can mechanically compute leakage-safe creator prior migration fields from current launch timestamps, creator wallets, and the sparse `pumpfun_migrate` event rows. However, the current migration evidence is too sparse to make the `4+ prior migrations` filter testable now.

Readiness classification: `creator_migration_reputation_partial_needs_migration_enrichment`.

T008 Creator Migration Reputation is **not feasible now**.

## Current Observability

| Metric | Value |
|---|---:|
| Strict launches | `1500` |
| All-collected launches | `3000` |
| Normalized lifecycle events | `184189` |
| `pumpfun_migrate` event rows | `2` |
| Deduped migration records | `1` |
| Unique migrated mints observed | `1` |
| Strict unique migrated mints observed | `1` |
| Migration timestamp available count | `2` |
| Creators available for migrated launches | `1` |
| Migrated launches identifiable from outcomes | `0` |
| Migrated launches identifiable from other fields | `0` |

## Leakage-Safe Computability

The leakage rule is:

- same creator only
- migration timestamp must exist
- migration timestamp must be strictly earlier than the current launch timestamp
- missing migration timestamps are not counted as prior migrations

| Field | Status | Notes |
|---|---|---|
| `creator_prior_migration_count` | `computable_now` | Computable from sparse current migration events, but undercounted. |
| `creator_prior_migration_rate` | `computable_now` | Uses prior migration count divided by prior launch count. |
| `creator_prior_launch_count` | `computable_now` | Creator and launch timestamp are available. |
| `creator_prior_failed_to_migrate_count` | `computable_now` | Prior launch count minus prior migration count. |
| `creator_prior_last_migration_age_seconds` | `computable_now` | Uses latest strictly prior migration timestamp. |
| `creator_has_4plus_prior_migrations` | `computable_partial` | Mechanically computable, but currently empty. |

## Derived Counts

| Metric | Value |
|---|---:|
| Creators with at least 1 observed migration event | `1` |
| Strict creators with at least 1 prior migration | `1` |
| All-collected creators with at least 1 prior migration | `1` |
| Strict launches with prior migration count available | `1500` |
| All launches with prior migration count available | `3000` |
| Strict launches with at least 1 prior migration | `1` |
| All launches with at least 1 prior migration | `1` |
| Strict launches with 4+ prior migrations | `0` |
| All launches with 4+ prior migrations | `0` |

## Why This Is Not Ready For T008

The practical manual-trading filter is whether a creator has migrated at least four prior tokens. Current data has only one deduped migrated mint and zero launches with `creator_has_4plus_prior_migrations`.

That means the filter is currently trivially empty. Running a thesis now would mostly test missing migration coverage, not creator reputation.

## Main Data Quality Concerns

- Current lifecycle classification observed only `2` `pumpfun_migrate` event rows.
- Those rows dedupe to `1` migrated mint.
- Migration events may occur outside the first `120m` lifecycle window.
- Outcome rows do not currently expose migration or graduation labels.
- PumpSwap/Raydium migration markers are not currently joined into creator history.
- Migration may exist in raw transactions but not be normalized into the current migration label set.
- Any missing migration timestamp must be excluded from leakage-safe prior counts.

## Report Paths

- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/creator_migration_reputation_feasibility/creator_migration_reputation_feasibility.json`
- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/creator_migration_reputation_feasibility/creator_migration_reputation_feasibility.md`
- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/creator_migration_reputation_feasibility/creator_migration_reputation_sample.csv`

## Recommendation

Do not run T008 yet.

Next action: enrich migration/graduation labels beyond the current first-two-hour lifecycle event set. The enrichment should identify migration/graduation events with timestamps and join them back to creator history. Only after the `4+ prior migrations` cohort is non-empty and meaningful should T008 be considered.

## 2026-06-02 Migration Enrichment Update

Bounded migration/graduation enrichment was run against the all-collected `3,000` launch cohort using Helius address-window transaction reads. This was data enrichment only; no thesis, backtest, validation, paper trading, live trading, optimization, grid search, or ML workflow was run.

### Runtime Fixes

- Added a positive-control migration probe and verified the known Pump.fun migration signature can be found through the bonding-curve address strategy.
- Replaced per-signature hydration with Helius address-window transaction reads for migration collection.
- Changed migration-window reads to scan latest transactions first so late lifecycle migration events are not pushed out by early high-activity transactions.
- Added corrected request preflight estimation for address-window collection.
- Future large API pulls should add coordinated concurrent mint workers before execution.

### Completed Enrichment Runs

| Run | Window | Candidate rows | Requests used | Transactions fetched | Migrated mints detected | Warnings |
|---|---:|---:|---:|---:|---:|---|
| 24h all-collected | `24h` | `3,000` | `11,566` | `42,132` | `1` | `[]` |
| 7d all-collected latest-first | `7d` | `3,000` | `5,582` | `90,721` | `15` | `[]` |

### Readiness Result After 7d Labels

| Metric | Value |
|---|---:|
| Unique migrated mints observed | `15` |
| Strict unique migrated mints observed | `9` |
| Migration timestamp available count | `15` |
| Creators with at least 1 migration event | `14` |
| Strict launches with 4+ prior migrations | `0` |
| T008 feasible now | `false` |
| Readiness classification | `creator_migration_reputation_partial_needs_migration_enrichment` |

The migration parser and collection path are now proven and bounded, but the enriched label density is still too sparse for the intended `4+ prior migrations` creator-reputation filter. T008 remains blocked because the target cohort is empty, not because the code path cannot collect or join migration labels.

### Updated Report Paths

- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/migration_graduation_collection/migration_graduation_collection_summary.json`
- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/migration_graduation_collection_7d_desc/migration_graduation_collection_summary.json`
- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/creator_migration_reputation_feasibility_7d_desc/creator_migration_reputation_feasibility.json`
- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/creator_migration_reputation_feasibility_7d_desc/creator_migration_reputation_feasibility.md`

### Updated Recommendation

Do not run T008 yet. The next useful data step is source expansion for migration/graduation labels, not another thesis. Candidate sources to evaluate are PumpSwap pool creation, Raydium/PumpSwap pair detection, and DexScreener pair-discovery enrichment by mint. Before the next large API pull, implement coordinated concurrent mint workers to reduce wall time safely.
