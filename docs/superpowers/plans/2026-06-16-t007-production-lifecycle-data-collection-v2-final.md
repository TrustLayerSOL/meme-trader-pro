# T007 Production Lifecycle Data Collection V2 Final Build Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make T007 a production-grade, event-first Pump.fun/PumpSwap lifecycle data collector that can prove honest decision-time-safe thesis data collection before any scan longer than 10 minutes or any trading/paper-trading work.

**Architecture:** One canonical SQLite event store owns raw source envelopes, normalized domain events, persistent mint identity, persistent pool identity, source watermarks, and materialized lifecycle state. JSONL/CSV/HTML watcher outputs are derived exports only. Campaign folders are report windows, not lifecycle state roots.

**Tech Stack:** Python, SQLite WAL, Helius Developer-tier RPC/WebSocket including Helius `transactionSubscribe` / Enhanced WSS, Solana standard WebSocket methods, Pump.fun public IDL, PumpSwap public IDL, pytest.

---

## 0. Final audit closure

This V2 plan supersedes the earlier plan at:

`/Users/dianeposs/Projects/meme-trader-pro/docs/superpowers/plans/2026-06-16-t007-production-lifecycle-data-collection.md`

Three independent audits found the first plan was directionally right but not implementation-ready. This V2 closes those findings:

- **One SQLite owner:** `t007_event_store.py` becomes the canonical event/identity/source-watermark store. `T007LifecycleStateStore` becomes a reducer/materialized-state layer backed by the same DB or delegates to `T007EventStore`. There must not be two independent SQLite truths.
- **Exact repo root:** all implementation commands use `/Users/dianeposs/Projects/meme-trader-pro`. If a shell starts in `/Users/dianeposs/Desktop/Jordan/meme_trader_pro`, first `cd /Users/dianeposs/Projects/meme-trader-pro`.
- **No ambiguous LaserStream language:** the required path uses Helius Developer-tier WebSocket/RPC, including Helius `transactionSubscribe` if available. It does **not** require LaserStream gRPC/mainnet, Geyser, private validator, shred stream, or paid institutional stream.
- **Exact source hierarchy:** `transactionSubscribe` canonical, `logsSubscribe` sentinel, dynamic `accountSubscribe` tracked state, filtered `programSubscribe` only for account-state discovery.
- **Pinned protocol docs:** Pump public docs commit pinned to `1b822158844a60ca577df6ca122211b595a1a578` for initial codec fixtures and decoder versioning.
- **Fault-injection gates:** restart/resume, lane liveness, canonical-vs-sentinel disagreement, replay starvation, queue overflow, RPC 429, DB writer failure, and exporter reconciliation are required before a production proof can pass.
- **Collector integration split:** no one-shot rewrite of `bonding_curve_progress_recorder_v1.py`; integrate event-first lanes incrementally.
- **Watcher honesty:** no generic `usable` count; only explicit `decision_safe_full_paths` and disjoint coverage buckets.
- **Trading boundary:** read-only decision snapshot only; no order size, action, trade recommendation, wallet, signer, private key, route submission, paper-trading, or send behavior.

---

## 1. Non-negotiable constraints

- Mayhem remains paused; do not restart or modify Mayhem collectors.
- Do not add wallet, private-key, signing, sendTransaction, trading, or paper-trading code.
- Do not run a scan longer than 10 minutes until all implementation tasks and the 10-minute production proof gate pass.
- Helius Developer-tier is the required base architecture.
- Backfill/replay can diagnose but cannot upgrade live decision evidence.
- Campaign output roots are export windows only.
- Execution-cost is low priority for thesis collection and must not block full-path data coverage in this milestone.
- No implementation may make watcher output more optimistic than the canonical event store supports.

---

## 2. Helius Developer-tier operating limits

Plan implementation must assume and expose these limits:

- RPC limit target: `50 req/s` unless measured/account-specific settings prove otherwise.
- Monthly credit budget: `10M` base Developer-tier assumption.
- WebSocket connection budget: `150` active connections maximum assumption.
- WebSocket stream metering: track bytes/messages by lane where practical.
- Keepalive: send WebSocket pings/health checks at least every 30 seconds; Helius documents WebSocket inactivity behavior, so dead/stale lanes must be detected.
- No assumption of mainnet LaserStream gRPC, Geyser, private validator, colocated infra, or shred delivery.

Required `transactionSubscribe` options:

```json
{
  "vote": false,
  "failed": false,
  "accountInclude": [
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
  ]
}
```

```json
{
  "commitment": "processed",
  "encoding": "jsonParsed",
  "transactionDetails": "full",
  "showRewards": false,
  "maxSupportedTransactionVersion": 0
}
```

Policy:

- `processed` is live decision timing evidence.
- Later `confirmed`/`finalized` reconciliation may annotate confidence but cannot change what was live-known at decision time.

---

## 3. Source hierarchy contract

### Canonical transaction lane

`transactionSubscribe` is canonical for:

- Pump.fun create/create_v2
- Pump.fun buy/sell/trade flow
- Pump.fun complete/migrate instruction evidence
- PumpSwap create_pool transaction evidence
- PumpSwap buy/sell/swap events

Every notification is inserted into `raw_source_envelopes` before any artifact write.

### Sentinel log lane

Use two `logsSubscribe` subscriptions because `mentions` supports one address per subscription:

- Pump.fun program mention
- PumpSwap program mention

Sentinel logs are used for:

- signature gap detection
- canonical lane liveness comparison
- bounded hydration/backfill trigger

Sentinel logs are not enough for full lifecycle evidence until hydrated into a raw envelope and normalized domain event.

### State lane

Use `accountSubscribe` for specific active accounts only:

- verified bonding curve PDA
- associated base/quote bonding curve token accounts
- verified PumpSwap pool account
- pool base/quote vault accounts

Use bounded `getMultipleAccounts` for thin polling. Do not use broad global account subscriptions for every Pump account.

### Filtered discovery lane

Filtered `programSubscribe` on PumpSwap may be used only for account-state discovery of pools. It does not provide transaction semantics.

PumpSwap Pool official layout offsets:

- discriminator offset `0`, length `8`
- `pool_bump` offset `8`, length `1`
- `index` offset `9`, length `2`, little-endian u16
- `creator` offset `11`, length `32`
- `base_mint` offset `43`, length `32`
- `quote_mint` offset `75`, length `32`
- `lp_mint` offset `107`, length `32`
- `pool_base_token_account` offset `139`, length `32`
- `pool_quote_token_account` offset `171`, length `32`
- `lp_supply` offset `203`, length `8`
- `coin_creator` offset `211`, length `32`
- `is_mayhem_mode` offset `243`, length `1`
- `is_cashback_coin` offset `244`, length `1`
- official public IDL data size: `245`

Default filter policy:

- `dataSize = 245`
- `memcmp offset 0 = Pool discriminator`
- optional `memcmp offset 75 = quote_mint` for WSOL/USDC if separate filtered subscriptions are used

Do not accept 301-byte Pool layouts unless a real captured fixture or pinned public source is added. If existing legacy code decodes 301 bytes, classify it as `legacy_observed_layout_pending_fixture` until proven.

---

## 4. Protocol codec contract

Pinned Pump public docs commit:

`1b822158844a60ca577df6ca122211b595a1a578`

Decoder versions must include this commit, for example:

`pump-public-docs@1b822158844a60ca577df6ca122211b595a1a578:pump.json`

Program IDs:

- Pump: `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P`
- PumpSwap: `pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA`
- Fee program: `pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ`
- Associated Token Program: `ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL`
- SPL Token: `TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA`
- Token-2022: `TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb`
- WSOL mint: `So11111111111111111111111111111111111111112`
- USDC mint: `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v`

Pump discriminators:

- `create`: `[24, 30, 200, 40, 5, 28, 7, 119]`
- `create_v2`: `[214, 144, 76, 236, 95, 139, 49, 180]`
- `buy`: `[102, 6, 61, 18, 1, 218, 235, 234]`
- `buy_v2`: `[184, 23, 238, 97, 103, 197, 211, 61]`
- `buy_exact_quote_in_v2`: `[194, 171, 28, 70, 104, 77, 91, 47]`
- `sell`: `[51, 230, 133, 164, 1, 127, 131, 173]`
- `sell_v2`: `[93, 246, 130, 60, 231, 233, 64, 178]`
- `migrate`: `[155, 234, 231, 146, 236, 158, 162, 30]`

Pump bonding curve PDA:

```text
PDA([b"bonding-curve", mint], Pump program)
```

Associated token account formula:

```text
PDA([owner, token_program, mint], Associated Token Program)
```

For bonding-curve token accounts, owner is the bonding curve PDA.

Pump `BondingCurve` account layout:

- discriminator offset `0`, length `8`, value `[23, 183, 248, 55, 96, 216, 172, 96]`
- `virtual_token_reserves` offset `8`, u64
- `virtual_quote_reserves` offset `16`, u64
- `real_token_reserves` offset `24`, u64
- `real_quote_reserves` offset `32`, u64
- `token_total_supply` offset `40`, u64
- `complete` offset `48`, bool
- `creator` offset `49`, pubkey
- `is_mayhem_mode` offset `81`, bool
- `is_cashback_coin` offset `82`, bool
- `quote_mint` offset `83`, pubkey
- minimum official decoded length: `115`

Quote policy:

- Use `virtual_quote_reserves` / `real_quote_reserves` as canonical names.
- Treat legacy `*_sol_reserves` as aliases only.
- SOL-paired v2 paths may use WSOL mint in instruction accounts while native SOL is transferred.
- USDC-paired paths use USDC mint and SPL Token quote program.
- Market cap, liquidity/depth, FDV proxy, and executable quote are separate fields.

PumpSwap canonical pool:

```text
pool = pump_amm::pool(0, pump::pool_authority(base_mint), base_mint, quote_mint)
```

Canonical pools are pools created by Pump `migrate` for completed bonding curves. Do not infer canonical status from token pair alone.

---

## 5. Required files

New files:

- `research/mtp_research/validation/t007_protocol_codecs.py`
- `research/mtp_research/validation/t007_event_store.py`
- `research/mtp_research/validation/t007_source_health.py`
- `research/mtp_research/validation/t007_decision_snapshot.py`
- `research/tests/test_t007_protocol_codecs.py`
- `research/tests/test_t007_event_store.py`
- `research/tests/test_t007_source_health.py`
- `research/tests/test_t007_readiness_semantics.py`
- `research/tests/test_t007_decision_snapshot.py`
- `research/tests/fixtures/t007_protocol/README.md`

Modified files:

- `research/mtp_research/collectors/bonding_curve_progress_recorder_v1.py`
- `research/mtp_research/validation/t007_lifecycle_events.py`
- `research/mtp_research/validation/t007_lifecycle_state_store.py`
- `research/mtp_research/validation/t007_lifecycle_collector_adapter.py`
- `research/mtp_research/validation/t007_lifecycle_reducer.py`
- `research/mtp_research/validation/t007_lifecycle_exporter.py`
- `research/mtp_research/validation/t007_full_path_lifecycle_tracker.py`
- `research/mtp_research/validation/t007_thesis_ready_gate.py`
- `research/tests/test_bonding_curve_progress_recorder_v1.py`
- `theses/T007_BONDING_CURVE_PROGRESS_RECORDER_V1.md`

---

## 6. Canonical database ownership

`T007EventStore` owns these canonical tables:

- `raw_source_envelopes`
- `domain_events`
- `mint_identity`
- `pool_identity`
- `source_watermarks`
- `source_health_snapshots`

`T007LifecycleStateStore` must not create an independent competing truth. It must become one of:

- a reducer/materialized-state layer using the same SQLite connection/database, or
- a compatibility facade delegating writes to `T007EventStore` and reading materialized lifecycle state from DB.

Implementation rule:

- One DB file.
- One writer thread.
- WAL mode.
- DB-derived JSONL ledger.
- No artifact-to-state reverse path after migration is complete.

---

## 7. Event and identity schema

### `raw_source_envelopes`

- `envelope_id TEXT PRIMARY KEY`
- `source_route TEXT NOT NULL`
- `program_id TEXT`
- `signature TEXT`
- `slot INTEGER`
- `block_time REAL`
- `source_received_at REAL NOT NULL`
- `commitment TEXT NOT NULL`
- `payload_json TEXT NOT NULL`
- `payload_sha256 TEXT NOT NULL`
- `inserted_at REAL NOT NULL`

Unique when signature exists:

`UNIQUE(source_route, signature, slot, payload_sha256)`

### `domain_events`

- `event_id TEXT PRIMARY KEY`
- `event_type TEXT NOT NULL`
- `mint TEXT`
- `pool_address TEXT`
- `signature TEXT`
- `instruction_index INTEGER`
- `inner_instruction_index INTEGER`
- `slot INTEGER`
- `block_time REAL`
- `source_received_at REAL NOT NULL`
- `normalized_at REAL NOT NULL`
- `feature_observed_at REAL`
- `decision_cutoff_time REAL`
- `decision_time_safe INTEGER NOT NULL`
- `source_route TEXT NOT NULL`
- `decoder_version TEXT NOT NULL`
- `raw_envelope_id TEXT`
- `payload_json TEXT NOT NULL`
- `inserted_at REAL NOT NULL`

Unique when signature exists:

`UNIQUE(event_type, mint, signature, instruction_index, inner_instruction_index, source_route)`

### `mint_identity`

- `mint TEXT PRIMARY KEY`
- `first_birth_seen_live_at REAL`
- `first_birth_signature TEXT`
- `first_birth_slot INTEGER`
- `creator TEXT`
- `bonding_curve_pda TEXT`
- `associated_base_bonding_curve TEXT`
- `associated_quote_bonding_curve TEXT`
- `quote_mint TEXT`
- `quote_asset TEXT`
- `base_token_program TEXT`
- `quote_token_program TEXT`
- `birth_verified INTEGER NOT NULL DEFAULT 0`
- `curve_pda_verified INTEGER NOT NULL DEFAULT 0`
- `curve_state_verified INTEGER NOT NULL DEFAULT 0`
- `last_live_seen_at REAL`
- `last_event_id TEXT`

### `pool_identity`

- `pool_address TEXT PRIMARY KEY`
- `mint TEXT NOT NULL`
- `quote_mint TEXT`
- `quote_asset TEXT`
- `creator TEXT`
- `index_value INTEGER`
- `is_canonical_pumpswap_pool INTEGER NOT NULL DEFAULT 0`
- `first_pool_seen_at REAL`
- `first_pool_signature TEXT`
- `pool_layout_version TEXT`
- `pool_verified INTEGER NOT NULL DEFAULT 0`
- `base_vault TEXT`
- `quote_vault TEXT`
- `last_event_id TEXT`

### `source_watermarks`

- `source_route TEXT PRIMARY KEY`
- `last_seen_slot INTEGER`
- `last_seen_signature TEXT`
- `last_seen_at REAL`
- `last_subscription_ack_at REAL`
- `last_message_at REAL`
- `last_reconnect_at REAL`
- `gap_detected_count INTEGER NOT NULL DEFAULT 0`
- `bounded_backfill_count INTEGER NOT NULL DEFAULT 0`

---

## 8. Domain event taxonomy

Required canonical event names:

- `raw_transaction_seen`
- `sentinel_log_seen`
- `canonical_sentinel_gap_detected`
- `pump_create_candidate_seen`
- `pump_birth_verified`
- `pump_birth_rejected`
- `curve_account_resolved`
- `curve_account_verified`
- `curve_state_decoded`
- `curve_state_decode_failed`
- `curve_account_not_found_retry`
- `curve_account_not_found_final`
- `pump_trade_seen`
- `trade_flow_window_updated`
- `holder_dev_snapshot_seen`
- `progress_threshold_evaluated`
- `progress_threshold_crossed`
- `pump_complete_seen`
- `pump_migrate_seen`
- `pumpswap_pool_seen`
- `pumpswap_pool_verified`
- `pumpswap_swap_seen`
- `post_migration_depth_seen`
- `quote_observation_seen`
- `replay_birth_context_seen`
- `replay_context_unresolved`
- `source_gap_detected`
- `source_gap_backfilled`
- `lane_stall_detected`
- `bounded_replay_started`
- `bounded_replay_finished`
- `bounded_replay_failed`

Legacy artifact event names may remain in compatibility code, but canonical event-store writes use the names above.

---

## 9. Coverage bucket taxonomy

Every migrated mint must fall into exactly one primary bucket:

- `decision_safe_full_path`
- `tracked_from_birth_missing_feature`
- `birth_seen_sample_or_capacity_rejected`
- `preexisting_before_window`
- `true_source_miss`
- `restart_gap`
- `schema_error`
- `unsupported_layout`
- `replay_unresolved`
- `migration_only_untracked`

Rules:

- `preexisting_before_window`: bounded replay proves launch time before campaign start.
- `true_source_miss`: bounded replay proves launch time inside campaign window but canonical live birth lane did not see it.
- `restart_gap`: event falls inside a known source downtime/reconnect/watermark gap.
- `replay_unresolved`: bounded replay was attempted and failed/null/timeout.
- `migration_only_untracked`: only allowed after no persistent link and no replay classification.
- `decision_safe_full_path`: live, pre-cutoff evidence only.

---

## 10. Feature availability versus outcome

Availability fields:

- `progress_stream_available`
- `market_cap_stream_available`
- `velocity_stream_available`
- `trade_flow_stream_available`
- `holder_dev_stream_available`
- `migration_event_available`
- `pool_state_available`
- `post_migration_depth_available`
- `quote_observation_available`

Outcome fields:

- `thresholds_crossed`
- `highest_progress_pct`
- `max_market_cap_usd`
- `migration_happened`
- `quote_price_impact_pct`

A mint must not fail full-path coverage solely because no threshold was crossed.

---

## 11. Strict readiness semantics

### `post_migration_pool_ready`

True only if all exist:

- verified PumpSwap pool account
- pool base mint
- pool quote mint
- base vault address
- quote vault address
- nonzero decoded reserve/depth observation
- observation timestamp
- source route

### `quote_ready`

True only if all exist:

- quote source
- input size or route size
- expected output
- price impact or slippage metric
- quote timestamp
- pool/route identity
- status `ok`

Partial rows produce `partial`, not ready.

### `decision_safe_full_path`

True only if all required feature availability fields are live and decision-time safe. Execution-cost is reported separately as `execution_cost_status` and does not block this milestone.

---

## 12. Watcher required fields

The live watcher/status payload must expose:

- `raw_transaction_notifications`
- `pump_create_candidates`
- `verified_births`
- `birth_rejected_false_candidate`
- `curve_account_verified`
- `curve_state_decoded`
- `curve_account_not_found_retrying`
- `curve_account_not_found_final`
- `curve_decode_failed_by_reason`
- `trade_flow_mints`
- `holder_dev_mints`
- `global_migration_mints_seen`
- `linked_to_any_persistent_birth`
- `linked_to_live_birth_in_window`
- `preexisting_before_window`
- `true_source_miss`
- `restart_gap`
- `replay_unresolved`
- `migration_only_untracked`
- `decision_safe_full_paths`
- `source_gap_count_by_lane`
- `queue_depth_by_lane`
- `queue_high_water_by_lane`
- `queue_drops_by_lane`
- `rpc_failures_by_lane`
- `http_429_by_lane`
- `websocket_reconnects_by_lane`
- `subscription_ack_at_by_lane`
- `last_message_at_by_lane`
- `lane_stale_age_seconds_by_lane`
- `canonical_sentinel_gap_count`
- `bounded_replay_queue_depth`
- `bounded_replay_failures_by_reason`
- `db_writer_alive`
- `db_ledger_consistent`

No generic `usable` count is allowed unless exactly equal to and named `decision_safe_full_paths`.

---

## 13. Bounded replay/backfill policy

Replay/backfill limits:

- Live lane priority always beats replay.
- Replay queue isolated from live source queues.
- Max concurrent transaction hydrations: `5`.
- Max replay signatures per migrated unknown mint: `100`.
- Max replay lookback window for 10-minute proof: campaign start minus `20 minutes`.
- Max replay wall time per mint: `30 seconds`.
- RPC 429 triggers exponential backoff and lane health degradation.
- Replay timeout produces `replay_unresolved`, not live evidence.

Replay cannot set:

- `birth_seen_live`
- `decision_time_safe = true` for live decision evidence
- `decision_safe_full_path`

Replay can set diagnostic classification only.

---

## 14. Implementation tasks

### Task 1: Lock event schema and protocol codecs

Files:

- Create: `research/mtp_research/validation/t007_protocol_codecs.py`
- Modify: `research/mtp_research/validation/t007_lifecycle_events.py`
- Create: `research/tests/test_t007_protocol_codecs.py`
- Create: `research/tests/fixtures/t007_protocol/README.md`

Steps:

- [ ] Add program IDs, quote mints, token program IDs, pinned Pump docs commit, and decoder-version helpers.
- [ ] Add Pump/PumpSwap discriminator constants.
- [ ] Add Pump bonding curve PDA helper signature.
- [ ] Add ATA helper signature for owner/token-program/mint.
- [ ] Add Pump BondingCurve prefix decoder with minimum length 115 and wrong-discriminator rejection.
- [ ] Add PumpSwap Pool decoder for official 245-byte layout only.
- [ ] Add optional placeholder for `legacy_observed_layout_pending_fixture` without treating it as verified.
- [ ] Add canonical event names to `t007_lifecycle_events.py` while preserving legacy compatibility names.
- [ ] Add tests for discriminators, wrong/short data, SOL/USDC quote detection, official Pool offsets, and unsupported extension rejection.

Verification:

```bash
cd /Users/dianeposs/Projects/meme-trader-pro
PYTHONPATH=/Users/dianeposs/Projects/meme-trader-pro python3 -m pytest -q research/tests/test_t007_protocol_codecs.py
```

### Task 2: Add source health and liveness primitives

Files:

- Create: `research/mtp_research/validation/t007_source_health.py`
- Create: `research/tests/test_t007_source_health.py`

Steps:

- [ ] Add lane health dataclass/store for queue depth, drops, high-water, reconnects, 429s, RPC failures, subscription ack time, last message time, stale age, canonical/sentinel gaps.
- [ ] Add liveness states: `not_started`, `subscribed_no_messages_yet`, `live`, `quiet_market`, `stalled`, `failed`.
- [ ] Add stale-lane rule: canonical lane cannot be considered healthy if sentinel is active and canonical has no messages past threshold.
- [ ] Add bounded replay queue counters and starvation guard.
- [ ] Test lane-stall classification.
- [ ] Test canonical-sentinel gap detection.
- [ ] Test queue drop hard-fail signal.

Verification:

```bash
cd /Users/dianeposs/Projects/meme-trader-pro
PYTHONPATH=/Users/dianeposs/Projects/meme-trader-pro python3 -m pytest -q research/tests/test_t007_source_health.py
```

### Task 3: Add canonical event store and define one SQLite owner

Files:

- Create: `research/mtp_research/validation/t007_event_store.py`
- Modify: `research/mtp_research/validation/t007_lifecycle_state_store.py`
- Create: `research/tests/test_t007_event_store.py`

Steps:

- [ ] Implement tables from sections 7 and 13.
- [ ] Keep one writer thread and WAL mode.
- [ ] Add idempotent raw envelope insert.
- [ ] Add idempotent domain event insert.
- [ ] Add identity upserts.
- [ ] Add source watermark update.
- [ ] Refactor `T007LifecycleStateStore` to delegate canonical writes to `T007EventStore` or use the same DB without duplicate truth.
- [ ] Test duplicate event idempotency.
- [ ] Test DB reopen preserves identity.
- [ ] Test replay event cannot set live birth fields.
- [ ] Test no competing DB truth is created.

Verification:

```bash
cd /Users/dianeposs/Projects/meme-trader-pro
PYTHONPATH=/Users/dianeposs/Projects/meme-trader-pro python3 -m pytest -q research/tests/test_t007_event_store.py
```

### Task 4: Add persistent identity and reducer classification

Files:

- Modify: `research/mtp_research/validation/t007_lifecycle_reducer.py`
- Modify: `research/mtp_research/validation/t007_event_store.py`
- Create: `research/tests/test_t007_readiness_semantics.py`

Steps:

- [ ] On `pump_birth_verified`, upsert `mint_identity`.
- [ ] On `curve_account_verified`, update curve identity.
- [ ] On `pumpswap_pool_verified`, upsert `pool_identity`.
- [ ] On migration, join against persistent identity first.
- [ ] Implement all coverage buckets from section 9.
- [ ] Ensure buckets are mutually exclusive and exhaustive for migrated mints.
- [ ] Test cross-window birth-to-migration linkage after DB close/reopen.
- [ ] Test every coverage bucket.

Verification:

```bash
cd /Users/dianeposs/Projects/meme-trader-pro
PYTHONPATH=/Users/dianeposs/Projects/meme-trader-pro python3 -m pytest -q research/tests/test_t007_readiness_semantics.py research/tests/test_t007_event_store.py
```

### Task 5: Add bounded replay classification

Files:

- Modify: `research/mtp_research/collectors/bonding_curve_progress_recorder_v1.py`
- Modify: `research/mtp_research/validation/t007_lifecycle_events.py`
- Modify: `research/mtp_research/validation/t007_lifecycle_reducer.py`
- Modify: `research/mtp_research/validation/t007_lifecycle_collector_adapter.py`
- Test: `research/tests/test_t007_readiness_semantics.py`

Steps:

- [ ] Add campaign window metadata to migration backfill jobs.
- [ ] Add bounded replay limits from section 13.
- [ ] Classify pre-window replay birth as `preexisting_before_window`.
- [ ] Classify in-window missed live birth as `true_source_miss`.
- [ ] Classify replay timeout/null as `replay_unresolved`.
- [ ] Ensure replay cannot mark evidence live or decision safe.
- [ ] Test replay queue isolation from live lanes.
- [ ] Test replay cannot starve live ingestion.

Verification:

```bash
cd /Users/dianeposs/Projects/meme-trader-pro
PYTHONPATH=/Users/dianeposs/Projects/meme-trader-pro python3 -m pytest -q research/tests/test_t007_readiness_semantics.py
```

### Task 6: Add compatibility mirror without changing collector behavior

Files:

- Modify: `research/mtp_research/validation/t007_lifecycle_collector_adapter.py`
- Modify: `research/mtp_research/validation/t007_lifecycle_exporter.py`
- Test: `research/tests/test_bonding_curve_progress_recorder_v1.py`

Steps:

- [ ] Mirror existing artifact rows into canonical events through compatibility adapter.
- [ ] Do not change live source behavior in this task.
- [ ] Generate DB-derived JSONL export and compare counts with existing artifact rows.
- [ ] Test legacy artifact compatibility.
- [ ] Test DB-derived export reconciles exactly to canonical event counts.

Verification:

```bash
cd /Users/dianeposs/Projects/meme-trader-pro
PYTHONPATH=/Users/dianeposs/Projects/meme-trader-pro python3 -m pytest -q research/tests/test_bonding_curve_progress_recorder_v1.py research/tests/test_t007_event_store.py
```

### Task 7: Route live collector lanes event-first, one lane at a time

Files:

- Modify: `research/mtp_research/collectors/bonding_curve_progress_recorder_v1.py`
- Modify: `research/tests/test_bonding_curve_progress_recorder_v1.py`

Steps:

- [ ] Route raw transaction notifications to `raw_source_envelopes` before artifact append.
- [ ] Route Pump birth events to canonical domain events.
- [ ] Route Pump trade-flow events to canonical domain events.
- [ ] Route curve observation events to canonical domain events.
- [ ] Route Pump/PumpSwap migration events to canonical domain events.
- [ ] Route post-migration pool/depth/quote events to canonical domain events.
- [ ] After each lane, run focused tests before moving to the next lane.
- [ ] Preserve artifact filenames as DB-derived/mirrored exports.
- [ ] Test no Mayhem files are imported or modified.

Verification:

```bash
cd /Users/dianeposs/Projects/meme-trader-pro
PYTHONPATH=/Users/dianeposs/Projects/meme-trader-pro python3 -m pytest -q research/tests/test_bonding_curve_progress_recorder_v1.py
```

### Task 8: Tighten readiness semantics

Files:

- Modify: `research/mtp_research/validation/t007_lifecycle_events.py`
- Modify: `research/mtp_research/validation/t007_lifecycle_reducer.py`
- Modify: `research/mtp_research/validation/t007_full_path_lifecycle_tracker.py`
- Test: `research/tests/test_t007_readiness_semantics.py`

Steps:

- [ ] Replace loose readiness booleans with `missing`, `partial`, `verified`, `decision_safe` statuses.
- [ ] Make `post_migration_pool_ready` require strict fields from section 11.
- [ ] Make `quote_ready` require strict fields from section 11.
- [ ] Remove threshold crossing as a full-path coverage requirement.
- [ ] Keep threshold crossing as an outcome field.
- [ ] Keep execution-cost separate and non-blocking for this milestone.
- [ ] Test partial pool rows do not become ready.
- [ ] Test partial quote rows do not become ready.
- [ ] Test no-threshold-crossed mints can still satisfy data coverage.
- [ ] Test execution-cost missing does not block data collection readiness.

Verification:

```bash
cd /Users/dianeposs/Projects/meme-trader-pro
PYTHONPATH=/Users/dianeposs/Projects/meme-trader-pro python3 -m pytest -q research/tests/test_t007_readiness_semantics.py
```

### Task 9: Update watcher/exporter/gate honesty

Files:

- Modify: `research/mtp_research/validation/t007_lifecycle_exporter.py`
- Modify: `research/mtp_research/validation/t007_full_path_lifecycle_tracker.py`
- Modify: `research/mtp_research/validation/t007_thesis_ready_gate.py`
- Test: `research/tests/test_t007_readiness_semantics.py`

Steps:

- [ ] Export all watcher fields from section 12.
- [ ] Remove misleading generic completeness fields or rename them to precise meanings.
- [ ] Gate fails if required watcher fields are missing.
- [ ] Gate fails on nonzero queue drops.
- [ ] Gate fails on DB/ledger inconsistency.
- [ ] Gate fails on canonical lane stall while sentinel lane is active.
- [ ] Low/no migration volume does not fail 10-minute correctness proof if source health is clean.
- [ ] Test every watcher contract field is present.
- [ ] Test migrated mints sum exactly across one primary bucket.

Verification:

```bash
cd /Users/dianeposs/Projects/meme-trader-pro
PYTHONPATH=/Users/dianeposs/Projects/meme-trader-pro python3 -m pytest -q research/tests/test_t007_readiness_semantics.py
```

### Task 10: Add read-only decision snapshot boundary

Files:

- Create: `research/mtp_research/validation/t007_decision_snapshot.py`
- Create: `research/tests/test_t007_decision_snapshot.py`

Steps:

- [ ] Add `DecisionSnapshot` dataclass.
- [ ] Include mint, pool, cutoff time, feature map, evidence event ids, freshness, and kill-switch reasons.
- [ ] Query only `decision_time_safe = 1` events where `feature_observed_at <= cutoff_time`.
- [ ] Reject replay-only evidence as live decision evidence.
- [ ] Explicitly prohibit order size, trade recommendation, buy/sell action, route submission, wallet, signer, and transaction fields.
- [ ] Test post-cutoff enrichment is excluded.
- [ ] Test missing required feature produces kill-switch reason.
- [ ] Test snapshot has no execution-intent fields.

Verification:

```bash
cd /Users/dianeposs/Projects/meme-trader-pro
PYTHONPATH=/Users/dianeposs/Projects/meme-trader-pro python3 -m pytest -q research/tests/test_t007_decision_snapshot.py
```

### Task 11: Fault-injection and production proof tests

Files:

- Create/Modify: `research/tests/test_t007_source_health.py`
- Create/Modify: `research/tests/test_t007_event_store.py`
- Create/Modify: `research/tests/test_bonding_curve_progress_recorder_v1.py`

Steps:

- [ ] Simulate DB writer failure and require hard gate failure.
- [ ] Simulate queue overflow and require hard gate failure.
- [ ] Simulate RPC 429 and verify backoff plus degraded lane health.
- [ ] Simulate websocket reconnect and verify watermarks survive.
- [ ] Simulate canonical lane silence while sentinel logs are active and require hard gate failure.
- [ ] Simulate bounded replay timeout and verify `replay_unresolved`.
- [ ] Simulate collector restart by closing/reopening DB and proving persistent identity linkage survives.
- [ ] Simulate exporter lag and verify DB-derived exports reconcile before final readiness.
- [ ] Add golden fixture placeholder tests that skip with explicit reason until real mainnet fixture bytes are added; do not treat missing fixtures as production-proof pass.

Verification:

```bash
cd /Users/dianeposs/Projects/meme-trader-pro
PYTHONPATH=/Users/dianeposs/Projects/meme-trader-pro python3 -m pytest -q \
  research/tests/test_t007_source_health.py \
  research/tests/test_t007_event_store.py \
  research/tests/test_bonding_curve_progress_recorder_v1.py
```

### Task 12: Documentation and focused verification

Files:

- Modify: `theses/T007_BONDING_CURVE_PROGRESS_RECORDER_V1.md`

Steps:

- [ ] Document why prior scans failed: storage was clean, lifecycle linkage and source ownership were not.
- [ ] Document event-first architecture.
- [ ] Document Helius Developer-tier limits and no mainnet LaserStream gRPC/Geyser/private validator dependency.
- [ ] Document source hierarchy.
- [ ] Document exact 10-minute proof gate.
- [ ] Document no wallet/signing/trading/paper-trading boundary.
- [ ] Document execution-cost as non-blocking for thesis data collection.
- [ ] Run focused tests.
- [ ] Run compile.

Verification:

```bash
cd /Users/dianeposs/Projects/meme-trader-pro
PYTHONPATH=/Users/dianeposs/Projects/meme-trader-pro python3 -m pytest -q \
  research/tests/test_t007_protocol_codecs.py \
  research/tests/test_t007_event_store.py \
  research/tests/test_t007_source_health.py \
  research/tests/test_t007_readiness_semantics.py \
  research/tests/test_t007_decision_snapshot.py \
  research/tests/test_bonding_curve_progress_recorder_v1.py

PYTHONPATH=/Users/dianeposs/Projects/meme-trader-pro python3 -m py_compile \
  research/mtp_research/validation/t007_protocol_codecs.py \
  research/mtp_research/validation/t007_event_store.py \
  research/mtp_research/validation/t007_source_health.py \
  research/mtp_research/validation/t007_decision_snapshot.py \
  research/mtp_research/validation/t007_lifecycle_events.py \
  research/mtp_research/validation/t007_lifecycle_state_store.py \
  research/mtp_research/validation/t007_lifecycle_collector_adapter.py \
  research/mtp_research/validation/t007_lifecycle_reducer.py \
  research/mtp_research/validation/t007_lifecycle_exporter.py \
  research/mtp_research/validation/t007_full_path_lifecycle_tracker.py \
  research/mtp_research/validation/t007_thesis_ready_gate.py \
  research/mtp_research/collectors/bonding_curve_progress_recorder_v1.py
```

---

## 15. 10-minute production proof gate

Do not run until Tasks 1-12 pass.

Pass requires:

- source duration quality complete
- no queue drops in any lane
- DB writer alive throughout run
- DB/ledger/export consistency true
- raw source envelopes present
- normalized domain events present
- persistent `mint_identity` rows present if births occur
- persistent `pool_identity` rows present if migrations occur
- watcher exposes every required field in section 12
- source liveness fields populated for every lane
- replay classifications include campaign window context
- migration coverage buckets sum exactly to migrated mints
- low/no migration volume does not fail if source health is clean
- sentinel/canonical disagreement produces gap counters or hard failure
- no generic `usable` or misleading completeness field overstates readiness
- no Mayhem files modified
- no wallet/private-key/signing/trading/paper-trading code added

A 10-minute proof proves correctness and honesty, not thesis profitability.

---

## 16. Data-collection ready definition

T007 becomes ready for longer data collection only when:

- all focused tests pass
- compile passes
- 10-minute production proof gate passes
- watcher truthfully reports disjoint lifecycle counts
- persistent identity survives restart/open-close proof
- replay/backfill classifications are meaningful and disjoint
- full-path counts exclude replay-only evidence
- Helius Developer-tier constraints are respected

This is still not live-trading readiness.

---

## 17. Future trading-readiness boundary

Allowed now:

- read-only decision snapshot interface
- evidence ids
- freshness and kill-switch reasons
- fee/depth/quote observations as data

Forbidden now:

- order size
- trade recommendation
- buy/sell action field
- route submission
- wallet access
- private key access
- signing
- sendTransaction
- live trading
- paper trading

Future execution code, if ever approved, must consume the read-only snapshot and reject missing/stale/replay-only evidence.

## Implementation closure addendum - event-first production gap

The audit after the V2 push correctly identified that the event-store structure
existed but live collector writes were still artifact-first. The closure pass
requires and implements:

1. `T007ProductionEventFirstWriter` as the collector boundary writer.
2. Synchronous SQLite raw-envelope/domain-event insert before JSONL artifact writes.
3. Strict `verify_birth_candidate()` filtering for usable Pump.fun births.
4. Explicit curve-probe retry/final failure classification.
5. Campaign-window enrichment for migration backfill jobs.
6. Strict watcher contract fields that prevent overstating migration/full-path readiness.
7. Production gate behavior that blocks controlled windows where migrations do not link to decision-safe full lifecycle evidence.

Remaining proof requirement: one focused compile/test pass, then exactly one 10-minute proof scan. No longer scan is allowed until that proof shows event-first DB consistency and watcher contract correctness.

## Proof hardening V4 addendum

The final production specification now requires formal proof levels and invariant enforcement before longer scans:

- L0: compile/import/schema proof.
- L1: deterministic protocol and watcher fixtures.
- L2: 10-minute live no-migration proof.
- L3: controlled migration proof with decision-safe full-path linkage.

Additional implementation requirements:

- Commitment-level tracking for processed/confirmed/finalized observations.
- Lane watermarks with missed slot ranges and repair state.
- Run manifest table.
- Protocol layout registry table.
- Lifecycle invariant violation table.
- Payload hashes and SQLite idempotency indexes.
- Latency histogram watcher fields.
- Null-reason fields for missing feature families.
- Hashable persisted DecisionSnapshot records.

No strategy logic, wallet logic, signing, sendTransaction, valuation ladder, paper trading, or live trading is part of this phase.

## Canonical single-writer repair addendum

The next proof cannot run until the proof DB has exactly one writer:

- All live rows pass through `T007SqliteWriter`.
- Legacy `T007LifecycleStateStore` writes are disabled for live proof runs.
- SQLite is initialized on internal local disk, with ORICO used for artifacts/archive after commit.
- `run_manifest` and `protocol_layout_versions` are written before accepting source evidence.
- JSONL/CSV rows are emitted only after the DB commit returns IDs.
- Fatal SQLite corruption stops the run as `T007_DB_FATAL`.
- Readiness reports source/artifact/canonical SQLite counts and uses canonical counts for the decision.
