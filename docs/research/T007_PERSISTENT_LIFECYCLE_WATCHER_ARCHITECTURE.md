# T007 Persistent Lifecycle Watcher Architecture

Status: required next architecture. No live scan was run by this document.

## Why this exists

The T007 collector can now detect Pump.fun births, verify curve accounts, decode progress/market-cap candidates, detect PumpSwap migrations, and write post-migration pool/quote observations. The remaining blocker is not another isolated decoder or report patch. The blocker is lifecycle continuity.

A bounded scan is a temporary observation window. Most migrations seen in a 10-minute proof were tokens born before the run started, so they cannot have full birth-to-curve-to-migration paths inside that run. A scan-first architecture cannot meet a live-trading standard.

The replacement architecture is persistent lifecycle-first.

## Deprecated workflow

```text
start scan
collect JSONL/CSV artifacts
postprocess artifacts
classify many migrations as missing pre-migration data
run another scan
```

This workflow is useful for plumbing tests but not for live trading readiness.

## Required workflow

```text
always-on source lanes
append every event to an audit ledger
update durable per-mint lifecycle state
serve watcher from current state
export artifacts from state
run readiness gates from state
```

The durable state layer must survive process restarts and ORICO disconnects. Local staging is the write target during live collection; ORICO is the archive target after finalization/sync.

## Source lanes

### Pump.fun birth lane

Purpose: detect new launches quickly enough to start curve tracking.

Input source:

- Helius `transactionSubscribe` filtered to Pump.fun program activity.
- Decoders for direct, inner, wrapped compact, create, and create_v2 layouts.

Birth rows are not thesis-usable until the bonding curve account is resolved and verified.

### Curve state lane

Purpose: track true bonding-curve progress and decision-time-safe features.

Inputs:

- Verified Pump.fun bonding curve account.
- Associated bonding curve account where needed.
- Read-only account probes or subscriptions.

Required outputs:

- `progress_pct`
- `market_cap_quote`
- `market_cap_usd` when quote normalization is confirmed
- velocity windows
- threshold crossings
- decode status and raw reserve fields

### Trade-flow / holder / dev lane

Purpose: explain how a token moves through the curve.

Required feature families:

- buy/sell count and volume imbalance
- unique buyer breadth
- trade efficiency
- holder concentration
- creator/dev activity
- organic/bot-like flow diagnostics

### PumpSwap migration lane

Purpose: detect graduation/pool creation even when the token was not tracked from birth.

Input source:

- PumpSwap `programSubscribe` market account route with SOL and USDC quote filtering.
- Level A account-create evidence where available.
- Level B first-swap evidence only as a diagnostic or secondary migration proof.

Migration events must join to the durable mint state. If no state exists, classify as `preexisting_before_watcher` or `migration_only_untracked`, not as a thesis failure.

### Post-migration pool / quote lane

Purpose: observe pool state after migration without mixing AMM depth with bonding-curve progress.

Required outputs:

- pool address
- quote asset
- base/quote reserves
- liquidity/depth status
- executable quote observation when available
- price impact diagnostics

Execution-cost observations are lowest priority until the execution-readiness milestone.

## Durable storage design

Use both SQLite and append-only JSONL.

### SQLite current-state database

Recommended path:

```text
/Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1/state/t007_lifecycle_state.sqlite
```

During live collection, write to a local staging DB and periodically checkpoint/sync to ORICO.

SQLite settings:

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA busy_timeout=5000;
```

Core tables:

```text
mint_lifecycle_state
lifecycle_events
curve_observations
threshold_crossings
migration_events
post_migration_observations
feature_snapshots
readiness_snapshots
```

### Append-only audit ledger

Every state transition also writes JSONL:

```text
lifecycle_events.jsonl
```

The ledger is the replay/audit source. SQLite is the current-state/read path.

## Per-mint state machine

Canonical states:

```text
BIRTH_SEEN
CURVE_ACCOUNT_RESOLVED
CURVE_ACCOUNT_VERIFIED
PROGRESS_TRACKING
THRESHOLD_CROSSED
MIGRATION_SEEN
POST_MIGRATION_POOL_READY
QUOTE_READY
FULL_PATH_READY
```

Terminal or diagnostic states:

```text
PREEXISTING_BEFORE_WATCHER
MIGRATION_ONLY_UNTRACKED
REPLAY_UNRESOLVED
TRUE_SOURCE_MISS
CURVE_DECODE_FAILED
CURVE_ACCOUNT_NOT_FOUND
```

A mint can have multiple missing-feature flags, but only one primary lifecycle coverage class.

## Coverage classes

Every migrated mint must classify into exactly one of:

```text
tracked_from_birth_full_path
tracked_from_birth_missing_feature
preexisting_before_watcher
migration_only_untracked
replay_unresolved
true_source_miss
```

Definitions:

- `tracked_from_birth_full_path`: live birth was seen, curve verified, progress/trade/holder/dev data recorded before migration, migration seen, and post-migration pool/quote observed.
- `tracked_from_birth_missing_feature`: live birth was seen but one feature family is missing.
- `preexisting_before_watcher`: replay proves the token launched before the watcher window.
- `migration_only_untracked`: migration was seen but no live or replay birth context is available yet.
- `replay_unresolved`: bounded replay failed to recover launch context.
- `true_source_miss`: replay proves launch occurred during active watcher time but no live birth event was recorded.

## Watcher requirements

The browser watcher must read state, not only post-run artifacts.

Required top-line stats:

- active mints
- verified curves
- progress tracking count
- threshold candidates
- migrations seen
- tracked-from-birth migrations
- full-path ready migrations
- preexisting migrations
- replay unresolved migrations
- true source misses
- queue/RPC/429/websocket health

The watcher must show scan/window counts separately from persistent lifetime counts.

## Readiness gates

### 10-minute feature proof gate

Allowed when:

- Mayhem untouched
- trading disabled
- paper trading disabled
- wallet/signing disabled
- valuation ladder suppressed
- source lanes connect
- state DB initializes and writes

### 60-minute thesis gate

Blocked until a 10-minute proof shows:

- state DB survives run/finalization
- no queue drops
- no websocket keepalive failure
- true source miss count is zero or fully explained
- migrations classify cleanly into persistent classes
- watcher displays persistent and window counts correctly

### 2-hour-plus gate

Blocked until a 60-minute persistent run shows:

- tracked-from-birth migrations exist
- full-path or near-full-path mints exist
- persistent state survives restart or controlled reconnect
- ORICO archive sync is complete and auditable

### Trading-readiness gate

Not part of T007 Persistent Lifecycle Watcher v1. Later work must add separate gates for:

- paper/shadow decision replay
- execution isolation
- kill switches
- slippage and fee accounting
- wallet/signing safety
- live canary limits

## What this fixes

This architecture fixes the circular failure mode where a temporary scan sees migrations from tokens born before the scan and reports unusable full-path coverage. Persistent state lets the system remember births and curve paths across time, then link migration when it happens.

It does not by itself prove an edge or authorize trading. It creates the data plane that later thesis testing and live decision systems require.

## Immediate implementation order

1. Create persistent state models and SQLite store.
2. Add lifecycle event ledger writer.
3. Route Pump.fun birth/curve events into state.
4. Route PumpSwap migration/post-migration events into state.
5. Export existing JSONL/CSV artifacts from state.
6. Update watcher to read state-derived live status.
7. Add readiness gates that block long scans until persistent coverage is proven.
8. Run one 10-minute proof only after the above is implemented and tested.
