# MemeTraderPro Migration / Graduation Enrichment Plan

## Executive Decision

Readiness classification: `migration_enrichment_pilot_ready`.

Recommendation: build a dry-run estimator first, then run a capped 100-mint migration/graduation enrichment pilot only after reviewing projected request counts. Do not run T008 until migration labels are enriched and the `4+ prior migrations` cohort is non-empty.

This is a planning and data-readiness sprint only. No data was fetched. No thesis, backtest, validation, paper/live trading, strategy logic, optimization, grid search, or ML was run.

## Current Blocker Summary

Creator migration reputation is not testable yet because migration/graduation observability is too sparse:

- Strict cohort launches: `1,500`
- All-collected launches: `3,000`
- Normalized lifecycle events: `184,189`
- Current `pumpfun_migrate` event rows: `2`
- Deduped migrated mints: `1`
- Migration timestamps available: `2`
- Creators with observed migration event: `1`
- Strict launches with at least 1 prior migration: `1`
- Strict launches with `4+` prior migrations: `0`
- Current readiness: `creator_migration_reputation_partial_needs_migration_enrichment`
- T008 feasible now: `false`

This does not disprove creator migration reputation. It shows that the current first-two-hour lifecycle event set is not enough to observe migrations.

## Label Semantics

Do not collapse these labels into one generic `migrated` field unless the source semantics are recorded.

| Label | Meaning | Required Time Field | Confidence Notes |
|---|---|---|---|
| `pumpfun_migrate_event_observed` | Pump.fun migration instruction/log observed in a hydrated transaction. | transaction block time | Highest confidence when Pump.fun program and migrate instruction/log are both present. |
| `graduated_to_pumpswap` | Token appears to have moved from Pump.fun bonding curve to PumpSwap. | migration/pair creation time | Requires PumpSwap program evidence or reliable pair metadata. |
| `migrated_to_raydium` | Token appears in Raydium pool after launch. | pool creation time | Different semantic than Pump.fun migrate; should stay separate. |
| `dex_pair_detected` | DexScreener or cached DEX source finds a token pair. | pair creation time if available | Useful enrichment, but survivorship-biased and not equal to migration unless source supports it. |
| `liquidity_pool_created_after_launch` | A DEX pool/pair was created after launch. | pool creation time | Broader than migration. |
| `migration_time` | Timestamp used for leakage-safe creator history. | required | Must be strictly before current launch to count as prior migration. |
| `migration_source` | Source of the migration/graduation label. | n/a | Examples: `pumpfun_program_log`, `pumpswap_pool_creation`, `raydium_pool_creation`, `dexscreener_pair`. |
| `migration_confidence` | Source-specific confidence label. | n/a | `high`, `medium`, `low`, or `missing`. |
| `migration_missing_reason` | Why no migration label exists. | n/a | Examples: `not_observed_in_window`, `missing_timestamp`, `source_not_checked`, `ambiguous_pool_source`. |

## Leakage Rule For T008

For creator prior migration count:

- same creator only
- migration timestamp must exist
- migration timestamp must be strictly earlier than the current launch timestamp
- missing migration timestamp is never counted as prior migration
- Dex pair existence without timestamp is not usable for prior migration count

## Local Data Sources Checked

| Source | Current Usefulness | Limitation |
|---|---|---|
| Strict launch census | Creator, mint, launch time, creation signature, bonding curve, associated bonding curve are available. | No migration labels. |
| All-collected launch census | Same as strict, for `3,000` launches. | No migration labels. |
| Normalized lifecycle events | Has deterministic event classification and `2` current `pumpfun_migrate` rows. | First-two-hour window is too narrow; migration is likely undercounted. |
| Lifecycle outcomes | Survival and FDV-proxy outcomes exist. | No migration/graduation label fields. |
| Cached raw lifecycle transactions | Useful for current 2h events and parser QA. | Does not cover longer post-launch migration horizon. |
| DexScreener-derived registry/cache | May provide pair presence and possibly pair timestamp if already cached. | Survivorship-biased and not necessarily a migration timestamp. |
| PumpSwap/Raydium local program markers | Discovery plan exists. | Not yet joined into migration labels. |

Current local-only conclusion: local data can support a parser and report shape, but it cannot complete migration enrichment for the cohort without checking longer post-launch history or additional pair/pool metadata.

## External Sources Considered

### Helius Standard RPC

Candidate endpoints:

- `getSignaturesForAddress`
- `getTransaction`

Likely query addresses:

- Pump.fun bonding curve address
- associated bonding curve address
- token mint address when useful

Use:

1. Query post-launch signatures for the relevant address.
2. Stop at the selected window: `24h`, `72h`, or `7d`.
3. Hydrate only candidate signatures needed to inspect logs/instructions.
4. Detect Pump.fun migrate instructions/logs and DEX pool creation markers.
5. Persist raw transactions for replay.

This is the preferred first source because it can provide migration timestamps directly and fits existing raw transaction patterns.

### Pump.fun / PumpSwap Program Signature Search

Potentially lower-noise if program-specific migration or pool-creation instructions are known.

Use only after a dry-run confirms exact program IDs, instruction discriminators/logs, and address strategy. Program-wide scans must stay bounded.

### DexScreener Pair Discovery By Mint

Potentially cheap as a pair-presence supplement:

- one request per mint if using token lookup
- may find pair creation metadata
- useful to identify possible DEX graduation

Limitations:

- survivorship-biased
- may miss failed or short-lived migrations
- pair timestamp semantics must be verified
- should not be treated as Pump.fun migration unless source supports it

### Raydium / PumpSwap Pool Discovery

Useful for `graduated_to_pumpswap`, `migrated_to_raydium`, and `liquidity_pool_created_after_launch`.

Do not mix these with `pumpfun_migrate_event_observed` unless the report preserves distinct source semantics.

## Proposed Pilot Scope

Recommended pilot:

- `100` mints max
- selected from all-collected cohort, with strict-cohort membership flagged
- include high-priority repeat creators
- include mints with existing `pumpfun_migrate` examples
- include time-distributed singleton creators
- evaluate post-launch windows:
  - `24h`
  - `72h`
  - `7d`
- dry-run first
- no default execute behavior

Alternative creator-centered pilot:

- `50` creators max
- select creators with multiple launches first
- check all their launches inside the all-collected cohort
- useful for migration reputation, but more complex if a creator has many launches

Recommended first planner mode: `100` mints.

Reason: migration labels are mint-level facts first. Creator reputation should aggregate after labels are enriched.

## Estimated Costs

These are request-equivalent estimates, not guaranteed Helius dashboard credit charges. Confirm the current Helius credit multiplier before execution.

### 100-Mint Pilot

| Window | Signature Requests | Hydrated Transactions | Total Request-Equivalent Estimate | Storage Estimate | Runtime Estimate |
|---|---:|---:|---:|---:|---:|
| `24h` | `100-300` | `500-2,500` | `600-2,800` | `100 MB-750 MB` | `20-90 min` |
| `72h` | `200-600` | `1,000-5,000` | `1,200-5,600` | `250 MB-1.5 GB` | `45 min-3 hr` |
| `7d` | `500-1,500` | `2,500-10,000` | `3,000-11,500` | `750 MB-4 GB` | `2-8 hr` |

Recommended first pilot ceiling:

- `100` mints
- `24h` window
- request ceiling: `3,000`
- hard stop: `5,000`
- hydrate cap: `2,500`
- stop immediately on provider, auth, or budget errors

### Strict Cohort 1,500 Launches

| Window | Base Estimate | High Estimate | Notes |
|---|---:|---:|---|
| `24h` | `9,000` | `42,000` | Reasonable after pilot if migration yield is useful. |
| `72h` | `18,000` | `84,000` | Better coverage, higher runtime. |
| `7d` | `45,000` | `172,500` | Expensive; only after 24h/72h prove value. |

### All-Collected 3,000 Launches

| Window | Base Estimate | High Estimate | Notes |
|---|---:|---:|---|
| `24h` | `18,000` | `84,000` | Likely acceptable only after pilot quality passes. |
| `72h` | `36,000` | `168,000` | Needs careful batching and checkpointing. |
| `7d` | `90,000` | `345,000` | Too large for first enrichment rollout. |

### Creator-Deduped Reputation Calculation

The actual creator reputation calculation should not fetch by creator first. It should:

1. enrich migration labels by mint
2. join enriched migration labels to creator/deployer
3. compute leakage-safe creator history

If strict creator count remains around the prior T003 count of `583`, the creator-history aggregation is offline after mint-level enrichment. No additional fetch is required for the reputation calculation itself.

## Fields Required To Make T008 Feasible

T008 becomes feasible only when enriched labels provide:

- `mint`
- `creator`
- `launch_id`
- `launch_time`
- `pumpfun_migrate_event_observed`
- `graduated_to_pumpswap`
- `migrated_to_raydium`
- `dex_pair_detected`
- `liquidity_pool_created_after_launch`
- `migration_time`
- `migration_source`
- `migration_confidence`
- `migration_missing_reason`

And the creator-history layer can compute:

- `creator_prior_migration_count`
- `creator_prior_migration_rate`
- `creator_prior_launch_count`
- `creator_prior_failed_to_migrate_count`
- `creator_prior_last_migration_age_seconds`
- `creator_has_4plus_prior_migrations`

## Proposed Command Shape

Dry-run planner:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_migration_graduation_enrichment_planner \
  --mint-limit 100 \
  --windows 24h 72h 7d \
  --request-ceiling 3000 \
  --hard-stop-projected-requests 5000 \
  --selection deterministic \
  --output-dir /Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/migration_graduation_enrichment_plan \
  --dry-run
```

Future execute command, only after dry-run review:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_migration_graduation_enrichment_collection \
  --mint-limit 100 \
  --window 24h \
  --max-signature-pages-per-mint 3 \
  --max-transactions-per-mint 25 \
  --max-total-transactions 2500 \
  --request-ceiling 3000 \
  --hard-stop-projected-requests 5000 \
  --execute
```

No-argument behavior must be dry-run only. Any real collection must require explicit `--execute`.

## Cache / Checkpoint Design

Required before execute:

- checkpoint by `mint + window + source`
- raw transaction persistence before derived label writing
- skip already-seen signatures
- dedupe by migration signature
- record source used for every label
- preserve missing reasons
- write partial progress safely if interrupted
- stop on provider, auth, or budget errors

Suggested output layout:

```text
/Volumes/ORICO/MemeTraderPro/data/raw/migration_graduation/
  migration_graduation_transactions.jsonl

/Volumes/ORICO/MemeTraderPro/data/backtests/migration_graduation/
  migration_graduation_labels.jsonl
  migration_graduation_labels.parquet

/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/migration_graduation_enrichment/
  migration_graduation_enrichment_audit.json
  migration_graduation_enrichment_audit.md
```

## Stop / Go Gates

Proceed to pilot only if:

- projected `24h` high request estimate is at or below `3,000` for `100` mints, or pilot size is reduced
- hard stop remains below `5,000` request-equivalent calls
- migration time can be determined from the selected source
- label semantics remain separated by source
- raw transaction replay is preserved
- pilot is capped and resumable
- no source requires private keys or wallet execution

Stop if:

- migration timestamp cannot be assigned
- source only provides pair existence without timestamp
- Helius/provider/auth/budget errors appear
- projected calls exceed hard stop
- migration label confidence is ambiguous for most examples
- DexScreener-only labels dominate and cannot be timestamped

## Risks

- Migration may occur after `24h`; a `24h` pilot can undercount.
- A `7d` window can become expensive and noisy.
- Dex/pair detection is survivorship-biased.
- Raydium/PumpSwap pool creation is not identical to Pump.fun migration.
- High-volume bonding-curve addresses may require many hydrated transactions.
- Current parser may need migration-specific layout handling.
- Missing timestamps make labels unusable for leakage-safe creator history.

## Next Recommendation

Build a dry-run migration/graduation enrichment planner first. Do not fetch data yet.

The planner should estimate selected mints, source mix, window costs, storage, runtime, and stop/go classification. If the 100-mint `24h` dry-run stays below the request ceiling, implement the capped execute path next. T008 should remain blocked until enrichment produces a non-empty and meaningful `creator_has_4plus_prior_migrations` cohort.
