# T007 Pump.fun / PumpSwap Forward-Data Pipeline Audit Brief

Status: T007 collector is research-only. No trading, paper trading, wallet signing, private keys, or order execution are enabled. Mayhem remains paused and untouched.

Purpose: provide an external audit package for getting the broad Pump.fun bonding-curve and PumpSwap migration/post-migration pipeline to production-grade data coverage before any longer thesis scans or live-money decisions.

## Current objective

Build a live, decision-time-safe dataset for Solana meme launches that can support thesis testing across two protocol phases:

- Bonding-curve phase: Pump.fun birth, curve progress, progress velocity, trade efficiency, buyer breadth, bot/organic diagnostics, holder/dev behavior.
- Post-migration AMM phase: PumpSwap migration/pool evidence, real pool depth, executable quote/price-impact diagnostics, buy/sell imbalance, dump detection, and execution-cost context.

The collector must prove it can capture the full lifecycle in real time before longer scans:

```text
birth -> admission -> curve observations -> thresholds/velocity -> trade flow -> holder/dev diagnostics -> migration evidence -> post-migration pool/depth -> executable quote/execution-cost context
```

## Hard safety boundaries

- No trading.
- No paper trading.
- No wallet/private-key/signing/sendTransaction code paths.
- Valuation ladder remains suppressed until market-cap formula is independently confirmed.
- Mayhem collector logic is not part of T007 and must remain paused.
- No scan longer than 10 minutes unless the readiness gate allows the next class.
- 2h+ scans remain blocked until a valid 60-minute thesis scan proves full-path lifecycle coverage.

## Source lanes

### 1. Pump.fun birth lane

Current implementation:

- Source: Helius `transactionSubscribe`.
- Filter: Pump.fun program account route.
- Decoder: broad Pump.fun create transaction decoder.
- Output: `birth_audit.jsonl`.
- Important fields: mint, launch signature, slot, received_at, bonding curve PDA, associated bonding curve when available, creator/dev wallet, source decode route, admission status.

Known status:

- Birth detection is working at high volume.
- Latest 60-minute run detected `496` unique live births.
- Source duration completed cleanly.

Audit questions:

- Are all Pump.fun create variants covered: direct, inner, compact/wrapped, Mayhem-wrapped, CreateV2, and any current Pump.fun router variants?
- Should Helius filters include additional accounts besides the Pump.fun program to reduce source misses?
- Are commitment level and transaction detail settings correct for low-latency birth detection?

### 2. Admission / sampling lane

Current implementation:

- Default thesis proof runs use 100 percent sample rate.
- Earlier design supported deterministic sampling to protect latency.
- Outputs are carried in `birth_audit.jsonl`.

Known status:

- Latest 60-minute run admitted all `496` births.
- Sample rejection and capacity rejection were zero.

Audit questions:

- What is the correct production policy: 100 percent deep tracking, tiered tracking, or deterministic sampling with thin fallback?
- What queue limits/backpressure protect timing quality under high-volume launch bursts?

### 3. Curve observation lane

Current implementation:

- Probes bonding-curve account state for admitted births.
- Writes `curve_observations.jsonl`.
- Computes true/candidate progress fields when account decode succeeds.
- Writes `true_curve_threshold_crossings.jsonl`, `curve_velocity_events.jsonl`, and `curve_acceleration_events.jsonl`.

Known status:

- Latest 60-minute run wrote `502` curve observations from `496` admitted births.
- Progress decoding previously matched Axiom B.Curve on at least one manual Mayhem example, but market-cap/valuation did not.

Audit questions:

- Is the Pump.fun bonding curve account layout current?
- Are virtual/real reserves, complete flag, token supply, and remaining supply decoded correctly?
- Is progress percent formula correct for standard Pump.fun and separately handled for Mayhem?
- Are observation timestamps decision-time safe?

### 4. Trade-flow / organic-flow lane

Current implementation:

- Decodes Pump.fun trade rows from transaction balance deltas and event data where available.
- Writes `trade_flow_events.jsonl` and `organic_flow_events.jsonl`.
- Tracks buy/sell counts, quote volume, net quote inflow, unique buyers/sellers, progress-per-trade, repeated-wallet/size/timing proxies.

Known status:

- Latest 60-minute run wrote `1,054` trade-flow events.
- Organic/bot share remains heuristic and should not be treated as production-grade without audit.

Audit questions:

- Is trade side inference correct for all Pump.fun trade variants?
- Are SOL and USDC quote amounts normalized correctly?
- Are buyer breadth and bot-share features robust enough for thesis testing?

### 5. Holder/dev diagnostics lane

Current implementation:

- Writes partial holder snapshots to `holder_distribution_snapshots.jsonl`.
- Writes partial creator/dev metadata to `dev_behavior_events.jsonl`.
- These are not full token-account holder-distribution crawls yet.

Known status:

- Latest 60-minute run wrote `1,054` holder snapshots and `496` dev behavior rows.
- Current holder/dev data is partial and should be labeled as such.

Audit questions:

- What minimum holder/dev features are required before thesis testing?
- Should token account snapshots be added for top-holder concentration at key thresholds?
- How should creator-linked sell behavior be detected in real time?

### 6. PumpSwap global route

Current implementation:

- Source: Helius `transactionSubscribe`.
- Filter: PumpSwap program account route, with SOL and USDC normalization support.
- Writes route diagnostics to `pumpswap_transaction_route_audit.jsonl`.
- Decodes swaps to `pumpswap_swap_events.jsonl`.

Known status from latest 60-minute run:

- PumpSwap route candidate transactions: `14,296`.
- PumpSwap swap events decoded: `61,863`.
- Unique PumpSwap swap mints observed offline in the run: `404`.
- Unique PumpSwap pools observed offline in the run: `371`.
- Live birth mints that later had PumpSwap swaps: `7`.

Root problem found:

- The collector decoded PumpSwap swaps but emitted zero `global_migration_events.jsonl` rows because it only promoted explicit pool-create / migrate / complete signals.
- A first PumpSwap swap for a live-born mint is valid post-migration evidence and must be promoted into migration coverage.

Implemented fix:

- First decoded PumpSwap swap for a mint already seen in the live birth lane now emits a confirmed migration event with:
  - `detection_method=pumpswap_first_swap_after_live_birth`
  - `source_route=pumpswap_first_swap_after_live_birth`
  - `canonical_mint_source=first_pumpswap_swap_event_for_live_birth`
  - `pool_or_pair_address`
  - quote asset and quote mint normalization
  - original swap signature as first-swap evidence
- The event is deduped per mint/pool and schedules post-migration observations.

Audit questions:

- Is first PumpSwap swap after live Pump.fun birth sufficient migration evidence for thesis coverage?
- Should explicit pool-create always supersede first-swap evidence when both exist?
- Which PumpSwap instructions/logs reliably indicate pool creation now?
- Are pool addresses and quote mints extracted from the right accounts for SOL and USDC pools?

### 7. Migration event lane

Current implementation:

- Canonical migration file: `global_migration_events.jsonl`.
- Candidate file: `global_migration_candidates.jsonl`.
- Duplicate file: `global_migration_event_duplicates.jsonl`.
- Explicit pool-create evidence and first-swap-implied evidence should both feed this lane.

Known status:

- Before the latest fix, explicit migration detection undercounted badly.
- Latest 60-minute run produced zero migration events despite many PumpSwap swaps.
- After the fix, future live runs should emit first-swap-implied migration events for live-born mints.

Audit questions:

- What is the correct hierarchy of migration evidence?
- Should pool creation, Pump.fun complete flag, first PumpSwap swap, and first PumpSwap liquidity/depth observation be separate evidence levels?
- What fields are required to avoid false positives from old/preexisting pools?

### 8. Post-migration pool/depth lane

Current implementation:

- Triggered by global migration events.
- Writes `post_migration_observations.jsonl`.
- Intended to capture pool reserves, quote asset, liquidity/depth, buy/sell imbalance, drawdown/dump diagnostics.

Known status:

- Latest 60-minute run wrote `0` post-migration observations because migration events were never emitted.
- This lane cannot be considered live-proven until a post-fix run shows migration events trigger depth observations.

Audit questions:

- What PumpSwap account state should be decoded for real depth?
- Are reserves read atomically enough for decision-time safety?
- Should this lane use Helius account reads, websocket account subscriptions, Jupiter quotes, or a combination?

### 9. Executable quote / execution-cost lane

Current implementation:

- Writes `executable_quote_observations.jsonl`.
- Writes `execution_cost_observations.jsonl`.
- Intended to preserve price impact, estimated execution cost, priority fee, failure/latency context.

Known status:

- Latest 60-minute run wrote zero executable quote observations because no migration event scheduled them.
- PumpSwap swap fee replay work improved fee understanding, but full live quote confidence still needs a successful post-migration path.

Audit questions:

- Should executable quotes come from Jupiter, direct PumpSwap math, or both?
- What quote size should be used for scalp thesis testing?
- How should stale quotes, slippage, priority fee, and failed transaction risk be represented?

### 10. Lifecycle coverage and readiness gate

Current implementation:

- Lifecycle tracker joins artifacts into `lifecycle_coverage_matrix.csv`.
- Summary: `lifecycle_coverage_summary.json`.
- Gate blocks longer scans unless full-path rates, source health, queue health, and safety constraints pass.

Current gate philosophy:

- A migrated mint only counts as full path if live birth, admitted curve observation, trade flow, migration evidence, post-migration quote/depth, and execution-cost linkage are present.
- Migration-only mints are useful but do not prove full thesis readiness.

Known status:

- 10-minute proof before the 60-minute run produced one full-path migrated mint and passed for 60-minute setup.
- 60-minute run failed thesis coverage because migration linkage missed first-swap evidence.
- Post-fix, the next proof should be a 10-minute validation, not another long scan.

Audit questions:

- Are the full-path requirements too strict, too loose, or correctly production-grade?
- What minimum sample size should be required before 60m, 2h, and longer scans?
- Which fields are mandatory for live-money readiness versus offline thesis testing?

## Latest failure and fix summary

Failure:

```text
PumpSwap swaps decoded -> first swaps for live-born mints observed -> no global migration event emitted -> no post-migration depth/quote scheduled -> lifecycle reports zero migrated mints
```

Root cause:

```text
PUMPSWAP_FIRST_SWAP_NOT_PROMOTED_TO_MIGRATION_EVENT
```

Fix:

```text
First decoded PumpSwap swap for a mint that was seen live in birth_audit.jsonl is now confirmed migration evidence and feeds global_migration_events.jsonl.
```

What this fixes:

- Live-born mints that reach PumpSwap by first observed swap will no longer be invisible to lifecycle coverage.
- Post-migration depth/quote scheduling can trigger even when explicit pool-create detection misses.

What this does not prove yet:

- It does not prove exact pool-create timestamp.
- It does not prove full post-migration quote/depth quality until a post-fix live proof observes migrated mints.
- It does not prove any trading edge.

## Required next validation, after code tests

Run exactly one 10-minute proof, not a 60-minute or 2h scan.

Pass criteria:

- Source duration complete.
- Queue drops zero.
- PumpSwap swaps decode.
- Any live-born mint with PumpSwap swap emits `global_migration_events.jsonl`.
- First-swap-implied migration events schedule post-migration observations.
- Lifecycle matrix reports migrated mints with no source-miss for live-born first-swap cases.

If no live-born mint migrates in 10 minutes, do not promote. Either wait for a manual Axiom mint during the window or run another short proof only if explicitly approved.

## PDF audit plan adopted 2026-06-15

Source reviewed:

`/Users/dianeposs/Downloads/Auditing a Solana Meme-Coin Migration Watcher for Pump.fun Forensics and Trading Readiness.pdf`

Implementation plan:

`docs/superpowers/plans/2026-06-15-t007-evidence-first-migration-watcher.md`

Adopted decisions:

- Helius Developer enhanced WebSocket `transactionSubscribe` remains the primary hot path for Pump.fun and PumpSwap.
- Mainnet LaserStream gRPC is not assumed available on Developer; do not design around it for this stage.
- Webhooks are fallback/reconciliation support, not the global PumpSwap primary route.
- DAS is delayed metadata hydration, not a birth or migration trigger.
- Raw transaction and account-state evidence is the source of truth; enhanced payloads are convenience views.
- JSONL lane artifacts alone are not considered sufficient for 100 percent readiness.
- The watcher must become evidence-first: append-only raw evidence, account snapshots, lifecycle state projection, then dashboard/gate summaries.
- Migration evidence is tiered:
  - `LEVEL_A`: explicit pool-create, explicit migrate/complete, or confirmed PumpSwap pool account creation tied to canonical mint and pool.
  - `LEVEL_B`: first successful PumpSwap swap after a known live birth, with canonical mint/pool and temporal ordering.
  - `LEVEL_C`: pool-state observation without swap; watch-only candidate, not a buy trigger and not full-path thesis evidence.
- First-swap Level B should count for lifecycle coverage and schedule post-migration observation, but it does not prove exact pool-create time.
- No scan longer than 10 minutes is allowed until evidence-first Level A/B/C tracking and the 10-minute proof gate pass.

Additional audit gates:

- Migration recall on labeled fixtures should be at least `99%`.
- Reviewed live migration precision should be at least `95%`.
- Evidence completeness for migrated mints should be at least `99%`.
- Birth and migration p95 detection latency should be measured before any live-money discussion.
- Valuation ladder remains suppressed until the market-cap formula is independently validated.

## Advice requested from external audit

Please audit the design for:

- Correct Helius subscription filters for Pump.fun birth, Pump.fun trades, PumpSwap pool creation, PumpSwap swaps, and PumpSwap pool state.
- Correct Pump.fun curve state layout and progress formula.
- Correct PumpSwap pool/market account layout for SOL and USDC quotes.
- Correct hierarchy for migration evidence: explicit pool create, Pump.fun complete/migrate, first PumpSwap swap, first pool-state observation.
- Whether first-swap-implied migration is safe enough for real-time decision systems or should be considered fallback evidence only.
- The minimum fields needed for live-money readiness, separately from offline thesis testing.
- Any simpler architecture used by working open-source Solana/Pump.fun/PumpSwap bots or indexers.
- Whether the watcher should be event-sourced from artifact files, an internal status bus, or a database.
