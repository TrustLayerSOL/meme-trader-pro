# T007 Bonding-Curve Progress Recorder v1

Status: implemented as a separate broad Pump.fun forward-data recorder scaffold, with a short live-smoke source adapter wired for broad Pump.fun create events.

This is not Mayhem-specific and does not trade, paper trade, tune thresholds, or modify live trading code.

Campaign data contract:

`theses/T007_CAMPAIGN_DATA_CONTRACT.md`

Pipeline audit brief:

`theses/T007_PIPELINE_AUDIT_BRIEF.md`

PDF-backed implementation plan:

`docs/superpowers/plans/2026-06-15-t007-evidence-first-migration-watcher.md`

## T007BE first-swap migration linkage fix

Status: implemented with regression coverage. No live scan was started in this step.

Root cause from the 60-minute tmux run:

- PumpSwap swap decoding worked.
- The run decoded `61,863` PumpSwap swap events.
- Offline inspection found `404` unique PumpSwap swap mints, `371` unique pools, and `7` live-born mints with later PumpSwap swaps.
- `global_migration_events.jsonl` remained empty because only explicit pool-create / migrate / complete signals were promoted to migration events.
- First PumpSwap swap evidence for a live-born mint did not trigger migration coverage or post-migration scheduling.

Fix:

- First decoded PumpSwap swap for a mint already seen by the live birth lane now emits a confirmed migration event.
- The event uses `detection_method=pumpswap_first_swap_after_live_birth`.
- The event records first-swap signature, pool, quote asset, quote mint, and canonical mint source.
- The event is deduped per mint/pool and schedules post-migration observations.

This fixes migration-linkage undercounting. It does not prove exact pool-create timestamp or trading edge.

## T007AG next-scan blocker resolution

Status: implemented and fixture-validated.

T007AG resolves the PDF-audit blockers that had stopped further short collection validation:

- unknown PumpSwap migrated mints now enqueue bounded migration-to-birth replay/backfill jobs;
- successful replay backfill writes `birth_audit.jsonl` rows with `birth_backfilled_from_replay=true`, trigger signature, job id, capture route, capture method, and capture confidence;
- failed replay backfill is counted without blocking live source ingestion;
- migrated mints can classify as `FULL_PATH`, `THIN_PATH`, `SAMPLE_REJECTED_WITH_THIN_PATH`, `SAMPLE_REJECTED_WITH_MIGRATION`, `BACKFILLED_BIRTH_WITH_MIGRATION`, `MIGRATION_ONLY_PREEXISTING`, `MIGRATION_ONLY_SOURCE_MISS`, `MIGRATION_ONLY_REPLAY_UNRESOLVED`, or `POST_ONLY`;
- sampled-out births get real thin curve probe execution in the transaction live-smoke path;
- deep-admitted births retain thin scheduling fields without duplicating deep probe-attempt artifacts;
- thin queue pressure defers/drops thin work before it can delay deep/high-progress tracking;
- migration events escalate thin-tracked tokens;
- valuation ladder remains suppressed under `market_cap_confirmed_only`;
- Mayhem remains untouched.

Post-scan follow-up: the first 10-minute controlled validation showed that unknown migrated mints were enqueued for replay but remained `queued` in the live transaction-smoke path. That live-path blocker is fixed: `GlobalMigrationDedupeWriter` can now receive a bounded replay client or lazy client factory, and `run_transaction_live_smoke` supplies `DirectMintLookupRpcClient` lazily for unknown migrated mints. Audit-style global migration calls remain queue-only unless a client is explicitly supplied.

Validation artifacts:

`outputs/theses/t007ag_migration_backfill_thin_track_validation/`

This allows only a short controlled validation run next. Thesis testing still requires per-trade flow, trade efficiency, buyer breadth, bot/organic share, holder distribution, creator/dev behavior, post-migration depth/quotes, execution-cost diagnostics, and decision-time-safe labels.


## T007AH implementation blockers handled

Status: implemented and focused-test verified. No live scan was started in this step.

T007AH clears the remaining implementation blockers from the PDF/data-contract audit before the next short validation scan:

- `trade_flow_events.jsonl` now has a real writer for per-trade side, wallet, quote/token amounts, buy/sell counts, volume ratios, net quote inflow, buyer/seller breadth, and progress-per-trade efficiency.
- transactionSubscribe Pump.fun buy/sell notifications now decode live trade rows from owner token and quote balance deltas.
- `transaction-live-smoke` now records decoded trade rows into `trade_flow_events.jsonl` and `organic_flow_events.jsonl` for already-seen birth mints.
- `organic_flow_events.jsonl` now records deterministic bot/organic proxy diagnostics from repeated wallet, repeated size, rapid timing, tiny trade share, bot-like trade share, and volume share.
- `holder_distribution_snapshots.jsonl` now records checkpointed holder metrics with status, latency, and error fields.
- `dev_behavior_events.jsonl` now records creator/dev behavior with point-in-time safety fields.
- `post_migration_observations.jsonl` now records diagnostic-only post-migration depth, executable quote, buy/sell imbalance, drawdown, and sell-side dump fields without enabling trading or paper trading.
- `execution_cost_observations.jsonl` now records diagnostic-only priority-fee, failed-transaction, tip, confirmation-latency, and estimated-fee fields.
- Feature rows now carry `decision_time_safe` and `decision_time_safety_status`; summaries count violations.
- `token_path_summary.jsonl`, `collector_summary.json`, `live_status.json`, and the watcher now expose the new feature-family statuses/counters.

The implementation-blocker decision is `T007_IMPLEMENTATION_BLOCKERS_HANDLED_READY_FOR_SHORT_VALIDATION_SCAN`. Live coverage is not proven yet, and edge/profitability claims remain disallowed.

Validation artifact:

`outputs/theses/t007_all_blockers_done/`

Focused verification:

- `research/tests/test_helius_transaction_subscribe_source.py` and `research/tests/test_bonding_curve_progress_recorder_v1.py`: `117 passed`
- Compile check passed for the transactionSubscribe source, recorder, and runner.

## T007AI no-long-scan readiness gate

Status: implemented and test-verified.

Hard rule: no T007 scan longer than 10 minutes may be recommended or run unless the thesis-ready gate allows that scan class.

Scan classes:

- `feature_feed_proof`: maximum `600s`; allowed before thesis-ready gate passes.
- `thesis_schema_validation`: maximum `600s` until all required live/deferred feature-family statuses are explicit.
- `thesis_data_collection`: `3600s+`; allowed only after the thesis-ready gate passes.
- `long_collection`: `2h+`; allowed only after at least one valid `60m` thesis-data collection passes.

Gate artifacts:

- `outputs/theses/t007_readiness_gate/thesis_ready_gate.json`
- `outputs/theses/t007_readiness_gate/summary.md`

The T007AA report scaffold now includes the gate decision in `summary.md`, so report output cannot silently imply longer scans while blockers remain. Valuation ladder bands remain suppressed under `market_cap_confirmed_only` and are not required for true-curve thesis validation.

## T007AJ holder/dev enrichment implementation

Status: implemented and focused-test verified. No live scan was started in this step.

The transaction live-smoke path now writes partial holder/dev enrichment rows from already available live data:

- Pump.fun birth metadata writes `dev_behavior_events.jsonl` rows with `dev_behavior_status=partial_birth_metadata`.
- Pump.fun trade rows write `holder_distribution_snapshots.jsonl` rows with `holder_distribution_status=partial_trade_derived`.
- The holder rows are explicit trade-derived holder proxies, not full token-account holder distribution snapshots.
- Dev rows are creator-identity metadata from the create event, not full creator-wallet behavior analysis.

Focused verification:

- `research/tests/test_helius_transaction_subscribe_source.py` and `research/tests/test_bonding_curve_progress_recorder_v1.py`: `127 passed`
- Compile check passed for the transactionSubscribe source, recorder, runner, and T007AA report scaffold.

Gate implication:

- The long-scan gate remains blocked until a 10-minute feature proof confirms live holder/dev rows.
- No 60-minute or longer scan is allowed from implementation alone.
- Post-migration depth/quotes and execution-cost observations remain implementation blockers after the holder/dev proof.

## Goal

Collect forward data needed to test whether T007 bonding-curve progress entries around `60%`, `65%`, `70%`, or `75%` completion can be actionable before Pump.fun migration.

The design intentionally prioritizes timing quality over total launch coverage. A deterministic `55%` default sample is preferred to attempting every launch if that causes delayed tracking.

## Collector surface

- Module: `research/mtp_research/collectors/bonding_curve_progress_recorder_v1.py`
- Runner: `research/mtp_research/validation/run_bonding_curve_progress_recorder_v1.py`
- Tests: `research/tests/test_bonding_curve_progress_recorder_v1.py`

## Live source wiring

The live smoke path uses the existing broad Pump.fun create-log source:

- `PumpFunCreateWebSocketCandidateSource`
- source adapter label: `helius_pumpfun_create_websocket_logs`
- candidate lane: broad Pump.fun birth watch

Mayhem collector behavior is not modified by T007C. The recorder only normalizes broad create candidates into `birth_audit.jsonl`, then probes admitted launches with the read-only bonding-curve account-state helper.

## T007E source-coverage audit

The first 5-minute live smoke saw only `17` broad births, or `3.4 births/minute`. That is low enough to require source-coverage auditing before any longer T007 collection.

Current broad source characteristics:

- websocket/RPC method: `logsSubscribe` with `mentions` on the Pump.fun program, followed by `getTransaction` hydration.
- required logs: create-like log strings such as `Instruction: Create` / `Instruction: CreateV2`.
- decoder path: `PumpFunCreateScanner` direct transaction instruction extraction.
- supported create routes: known top-level create layouts in `PUMPFUN_CREATE_LAYOUTS`.
- likely weak routes: inner/wrapped/compact creates that do not appear as simple direct create rows.
- associated bonding curve: available in the upstream source and now persisted by the T007 adapter.
- bonding curve account: persisted in birth audit and curve observation context.

Added diagnostic mode:

```bash
cd /Users/dianeposs/Projects/meme-trader-pro

RUN_ID="birth_source_audit_$(date +%Y%m%d_%H%M%S)"

PYTHONPATH=/Users/dianeposs/Projects/meme-trader-pro python3 -m research.mtp_research.validation.run_bonding_curve_progress_recorder_v1 \
  --mode birth-source-audit \
  --duration-seconds 300 \
  --output-root "/Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1/${RUN_ID}"
```

The audit writes:

- `raw_birth_source_audit.jsonl`
- `birth_source_audit_summary.json`

The raw audit rows are compact and include decode route, mint, bonding curve, associated bonding curve, and reject reason. Full transaction dumps are intentionally not written.

## T007F transactionSubscribe audit

T007 now has a transactionSubscribe-backed audit mode that reuses the existing transactionSubscribe create decoder without changing Mayhem behavior.

Existing source inspected:

- Class/file: `HeliusTransactionSubscribeCreateSource` in `research/mtp_research/validation/helius_transaction_subscribe_source.py`
- Subscription method: `transactionSubscribe`
- Filter: `accountRequired` includes the Pump.fun program
- Transaction detail mode: full transaction details, `jsonParsed`, `processed`
- Decoder: `decode_pumpfun_transaction_subscribe_notification`
- Instruction walking: top-level and `meta.innerInstructions`
- Wrapped/compact support: existing decoder has wrapped compact Mayhem create route handling
- Emits mint: yes, when decoded
- Emits bonding curve: yes, as `bonding_curve`
- Emits associated bonding curve: not consistently emitted by the existing transactionSubscribe decoder
- Emits creator/dev: yes, when present in decoded accounts
- Emits launch signature/slot: yes

Short audit command:

```bash
cd /Users/dianeposs/Projects/meme-trader-pro

RUN_ID="transaction_birth_source_audit_$(date +%Y%m%d_%H%M%S)"

PYTHONPATH=/Users/dianeposs/Projects/meme-trader-pro python3 -m research.mtp_research.validation.run_bonding_curve_progress_recorder_v1 \
  --mode transaction-birth-source-audit \
  --duration-seconds 300 \
  --output-root "/Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1/${RUN_ID}"
```

Artifacts:

- `transaction_birth_source_audit_summary.json`
- `transaction_raw_birth_source_audit.jsonl`
- `run_config.json`

The transaction audit is diagnostic only. It does not change sampling, strategy rules, progress formula logic, trading, or paper trading.

### 2026-06-12 transactionSubscribe audit result

Output root:

`/Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1/transaction_birth_source_audit_20260612_102102`

Summary:

- Requested duration: `300s`
- Actual duration: `300.081865s`
- Websocket closed early: `false`
- Raw transaction notifications: `17101`
- Pump.fun mentions: `17101`
- Create-like decoded rows: `1381`
- Direct creates decoded: `194`
- Inner creates decoded: `0`
- Wrapped/compact creates decoded: `1187`
- Unique decoded birth mints: `199`
- Duplicate mint rows: `1182`
- Decoded rows per observed minute: `276.12465`
- Bonding curve account present: `1381`
- Associated bonding curve present: `0`
- Creator/dev present: `1381`

Comparison against the prior logsSubscribe audit:

- Prior logsSubscribe audit observed `199` raw Pump.fun notifications over about `42.5s` and decoded `1` unique birth.
- transactionSubscribe observed a full `300s`, decoded `199` unique birth mints, and exposed `1187` wrapped/compact create rows.

Recommendation from this audit: T007 birth detection should move toward transactionSubscribe, while keeping deterministic `55%` deep-tracking sampling after normalization. Before longer T007 collection, fix the transactionSubscribe duplicate-row collapse and associated bonding curve availability.

## T007G normalized transactionSubscribe source

T007 now has a normalized transactionSubscribe source wrapper:

- Class: `TransactionSubscribeNormalizedBirthSource`
- Runner mode: `transaction-live-smoke`
- Pipeline: transactionSubscribe decoded rows -> unique mint-level births -> deterministic sampling -> admitted-birth curve probe
- Deduplication key: `mint`
- First-seen retention order: slot, then received time, then signature

### 2026-06-12 normalized smoke result

Output root:

`/Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1/txsub_normalized_live_smoke_20260612_103500`

Summary:

- Requested duration: `300s`
- Actual transactionSubscribe duration: `300.057688s`
- Websocket closed early: `false`
- Raw transaction notifications: `10374`
- Decoded birth rows: `1700`
- Unique birth mints: `167`
- Duplicate mint rows: `1533`
- Unique birth mints/min: about `33.39`
- Direct decoded rows: `155`
- Inner decoded rows: `2`
- Wrapped/compact decoded rows: `1543`
- First-seen direct births: `155`
- First-seen inner births: `2`
- First-seen wrapped/compact births: `10`
- Admitted births after dedupe: `94`
- Sample rejected after dedupe: `73`
- Capacity rejected after dedupe: `0`
- Curve observation attempts: `94`
- Curve observations written: `94`
- Queue drops: `0`
- Bonding curve account present: `167`
- Associated bonding curve present: `0`
- Exact progress decoded: `0`
- Unresolved progress formula count: `94`

Important timing caveat:

The normalized source deduped correctly, but the smoke currently collects the full `300s` transactionSubscribe source window before probing admitted births. That makes `birth_to_first_curve_observation_latency_ms` batch-delayed rather than true live latency:

- Median: `162332.339 ms`
- p90: `284889.888 ms`

Recommendation from this smoke: source normalization works, but the next T007 step should make transactionSubscribe normalized births stream into the recorder/probe path as they arrive. Do not proceed to progress formula until this batch-delay is fixed or explicitly accepted as a non-latency smoke.

## T007H streaming transactionSubscribe timing fix

T007H changes the `transaction-live-smoke` path from batch collection to callback streaming:

- transactionSubscribe notification received
- decoded create rows normalized immediately
- first-seen mint dedupe applied during the run
- deterministic sampling/admission applied after dedupe
- admitted births probed immediately
- later duplicate rows ignored for probing

The existing batch `fetch_launches()` path remains available for audit-style checks. Mayhem collector behavior was not modified.

### 2026-06-12 streaming live smoke result

Output root:

`/Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1/txsub_streaming_live_smoke_20260612_105233`

Summary:

- Requested duration: `300s`
- Actual transactionSubscribe duration: `300.13558s`
- Websocket closed early: `false`
- Raw transaction notifications: `9416`
- Decoded birth rows: `2307`
- Unique birth mints: `144`
- Duplicate mint rows: `2163`
- Direct decoded rows: `135`
- Inner decoded rows: `0`
- Wrapped/compact decoded rows: `2172`
- First-seen direct births: `135`
- First-seen wrapped/compact births: `9`
- Admitted births after dedupe: `80`
- Sample rejected after dedupe: `64`
- Capacity rejected after dedupe: `0`
- Curve observation attempts: `80`
- Curve observations written: `80`
- Queue drops: `0`
- RPC failures: `0`
- HTTP 429 count: `0`
- Exact progress decoded: `0`
- Unresolved progress formula count: `27`
- Decode failures: `53`
- Associated bonding curve present: `0`

Latency:

- Birth-to-admission median: `15.282 ms`
- Birth-to-admission p90: `25.898 ms`
- Birth-to-first-curve-observation median: `196.823 ms`
- Birth-to-first-curve-observation p90: `223.165 ms`
- Notification-to-birth-normalized median: `14.296 ms`
- Notification-to-birth-normalized p90: `24.611 ms`
- Normalized-birth-to-probe-start median: `1.963 ms`
- Normalized-birth-to-probe-start p90: `4.101 ms`
- Probe duration median: `178.419 ms`
- Probe duration p90: `203.634 ms`
- First curve observation under 1s: `80/80`
- First curve observation over 30s: `0/80`

Conclusion:

The prior `~162s` median first-observation latency was an artificial batch-delay artifact, not a live source or probe-speed limitation. The streaming transactionSubscribe path is now timing-clean for a short smoke. Exact progress remains blocked because the recorder still does not compute Pump.fun curve progress percent in live mode. The smoke preserves decoded curve-state fields when account decode succeeds, including virtual token reserves, virtual SOL reserves, real token reserves, real SOL reserves, token total supply, and complete flag; it does not fake `progress_pct`.

## T007I corrected historical progress and valuation split

T007I split the old historical idea into two separate theses:

- `T007A_true_bonding_curve_progress`: reserve/progress thesis, historically tested only as `fdv_denominator_progress_proxy`.
- `T007B_valuation_confirmation_runner_filter`: raw valuation/FDV band continuation thesis.

Historical correction output:

`outputs/theses/t007i_corrected_historical_progress_and_valuation_split/`

## T007J streaming dual-thesis forward recorder

T007J keeps one normalized transactionSubscribe stream and records both forward theses without changing Mayhem, trading, paper trading, or execution behavior:

- Thesis A: `true_curve_progress`, based on Pump.fun bonding-curve reserve state.
- Thesis B: `valuation_confirmation`, based on live valuation/FDV-style band crossings.

The runner still uses deterministic sampling after mint-level dedupe. The collector now preserves enough per-observation fields to distinguish reserve-progress crossings from valuation-band crossings:

- `crossing_type`
- `progress_pct_status`
- `progress_formula_version`
- `progress_denominator_tokens`
- `reserve_scale_mode`
- `real_token_reserves_scaled`
- `valuation_usd`
- `valuation_source_field`
- `valuation_price_fdv_proxy`

True-curve progress thresholds are tracked separately from valuation bands. Valuation bands are diagnostic only and do not tune the fixed progress thesis.

### 2026-06-12 T007J dual-thesis streaming smoke result

Output root:

`/Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1/t007j_streaming_dual_thesis_smoke_20260612_112229`

Run id:

`bc-progress-20260612-182229`

Command:

```bash
cd /Users/dianeposs/Projects/meme-trader-pro

RUN_ID="t007j_streaming_dual_thesis_smoke_$(date +%Y%m%d_%H%M%S)"

PYTHONPATH=/Users/dianeposs/Projects/meme-trader-pro python3 -m research.mtp_research.validation.run_bonding_curve_progress_recorder_v1 \
  --mode transaction-live-smoke \
  --duration-seconds 300 \
  --followup-drain-seconds 180 \
  --sample-rate-percent 55 \
  --output-root "/Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1/${RUN_ID}"
```

Smoke summary:

- Requested duration: `300s`
- Actual transactionSubscribe duration: `300.096686s`
- Websocket closed early: `false`
- Live source used: `helius_transaction_subscribe_pumpfun_create`
- Source route: `transaction_subscribe`
- Raw transaction notifications: `9865`
- Decoded birth rows: `1373`
- Unique birth mints: `132`
- Duplicate mint rows: `1241`
- Unique birth mints/min: about `26.39`
- Direct decoded rows: `124`
- Inner decoded rows: `0`
- Wrapped/compact decoded rows: `1249`
- Admitted births after dedupe: `68`
- Sample rejected after dedupe: `64`
- Capacity rejected after dedupe: `0`
- Curve observation attempts: `68`
- Curve observations written: `68`
- Queue drops: `0`
- Queue high-water mark: `0`
- RPC failures: `0`
- HTTP 429 count: `0`
- Bonding curve account present: `132`
- Associated bonding curve present: `0`
- Migration events written: `0`

Latency:

- Birth-to-admission median: `13.601 ms`
- Birth-to-admission p90: `24.241 ms`
- Birth-to-first-curve-observation median: `196.838 ms`
- Birth-to-first-curve-observation p90: `220.216 ms`
- Normalized-birth-to-probe-start median: `2.075 ms`
- Normalized-birth-to-probe-start p90: `4.280 ms`
- Probe duration median: `176.815 ms`
- Probe duration p90: `202.723 ms`
- First curve observation under 1s: `68/68`
- First curve observation under 2s: `68/68`
- First curve observation under 5s: `68/68`
- First curve observation over 10s: `0/68`
- First curve observation over 30s: `0/68`

Dual-thesis diagnostics:

- Exact progress decoded: `0`
- Progress decoded exact count: `0`
- Progress decoded candidate count: `20`
- Unresolved progress formula count: `0`
- Decode-error curve observations: `48`
- Reserve scale modes: `raw_integer_units_6_decimals=20`, `unknown=48`
- True-curve threshold crossings written: `0`
- First `60%` true-curve crossings: `0`
- First `65%` true-curve crossings: `0`
- First `70%` true-curve crossings: `0`
- First `75%` true-curve crossings: `0`
- Valuation present count: `20`
- Valuation missing count: `48`
- Valuation band crossings written: `0`
- First `$30k` valuation crossings: `0`
- First `$36k` valuation crossings: `0`
- First `$40k` valuation crossings: `0`
- First `$50k` valuation crossings: `0`
- First `$60k` valuation crossings: `0`

Artifacts:

- `run_config.json`
- `collector_summary.json`
- `birth_audit.jsonl`
- `curve_observations.jsonl`
- `threshold_crossings.jsonl`
- `migration_events.jsonl`

Validation:

- Focused recorder tests: `27 passed`
- Compile check passed for:
  - `research/mtp_research/collectors/bonding_curve_progress_recorder_v1.py`
  - `research/mtp_research/validation/run_bonding_curve_progress_recorder_v1.py`
- ORICO write test: passed
- Mayhem live collector process check: no active Mayhem collector found before the smoke
- Mayhem code modified: `false`

Conclusion:

The streaming transactionSubscribe path remains timing-clean. One normalized stream now feeds both the true-curve progress recorder and the valuation-confirmation recorder. The reserve formula is connected in live mode and produced `20` candidate reserve-progress observations, but the short smoke did not observe an exact completed-curve validation row and did not emit either true-curve progress crossings or valuation band crossings.

T007 remains a data-recorder and thesis-validation pipeline only. There is no trading, no paper trading, no threshold tuning, no buy/sell rule change, and no edge claim from this smoke.

Recommendation: ready for one 30-minute controlled dual-thesis run if continuing T007. Do not run longer until the 30-minute run confirms stable timing, enough decoded reserve rows, and whether true-curve or valuation crossings appear in fresh data.

Dataset and label inventory:

- Snapshot source: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T011_expanded_rerun/combined_expanded_lifecycle_snapshots.jsonl`
- Snapshot rows: `177708`
- Total launch universe: `14809`
- Usable valuation/progress proxy launches: `9210`
- Missing valuation proxy launches: `5599`
- Migration labels joined: `238`
- Baseline joined migration-label rate: `2.5841%`
- Migration label sources: `223` DexScreener pair-created proxy labels, `15` Helius Pump.fun migrate-log labels
- Valuation field used: `valuation_proxy_usd`, with `fdv_usd` fallback during loading

Core caveat:

The old `$69k` denominator was not true Pump.fun curve progress. It used `valuation_proxy_usd / 69000`, which likely selected higher-FDV / already-confirmed runners rather than actual reserve-based `70%`-`75%` completion.

Corrected denominator result:

- `$30k`-`$40k` denominators generated many crossing rows, including `$36k` threshold families, but the available migration label timing is not reliable enough to support a migration-after-crossing claim.
- All denominator/progress rows remain labeled `fdv_denominator_progress_proxy`, not true progress.
- T007A label from this run: `weak_proxy_only`.

Valuation-confirmation result:

- `$30k -> $40k`: `1041` entries, `95.0048%` continuation, validation continuation `95.1318%`.
- `$36k -> $50k`: `1006` entries, `91.6501%` continuation, validation continuation `89.2857%`.
- `$40k -> $60k`: `989` entries, `84.4287%` continuation, validation continuation `83.3689%`.
- `$50k -> $100k`: `922` entries, `68.4382%` continuation, validation continuation `79.7647%`.

Interpretation:

- `$36k` looks meaningful as a valuation-confirmation waypoint into `$50k`, not as proven true curve completion.
- The old T007 result was probably a different signal: valuation confirmation / continuation after a token has already reached meaningful FDV.
- True curve progress still deserves forward testing, but only after reserve-based `true_curve_progress` is computed from live curve state.
- Valuation confirmation should be forward-collected in the same T007 recorder because it uses the same launch stream and curve observations.

T007I output artifacts:

- `summary.md`
- `corrected_denominator_threshold_metrics.csv`
- `valuation_band_metrics.csv`
- `valuation_continuation_metrics.csv`
- `strategy_sanity_checks.csv`
- `validation_split_metrics.csv`
- `forward_dual_thesis_collection_plan.md`

Next engineering step:

Implement reserve-based `true_curve_progress` in the forward T007 recorder while also preserving valuation-band crossings in the same output stream. Do not create a second collector.

## Data outputs

The recorder writes JSONL artifacts under a run-specific output root:

- `birth_audit.jsonl`
- `curve_observations.jsonl`
- `threshold_crossings.jsonl`
- `migration_events.jsonl`
- `collector_summary.json`
- `run_config.json`

The intended external-drive layout is:

`/Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1/<run_id>/`

## Timing quality protections

- Deterministic mint-hash sampling, default `55%`.
- Capacity rejection before deep tracking when active tracking is full.
- Bounded follow-up queue.
- Priority tiers by progress:
  - below `40%`: low
  - `40%`-`50%`: medium
  - `50%`-`60%`: high
  - `60%`-`75%`: very high
  - `75%`-`95%`: critical
  - complete/migrated/dead/timeout: stop tracking
- Queue overload drops or evicts lower-priority work before delaying high-progress tracked tokens.

## Threshold crossings

The first crossing is recorded once and never overwritten for:

`50`, `55`, `60`, `62.5`, `65`, `67.5`, `70`, `72.5`, `75`, `80`, `85`, `90`, `95`.

Each crossing stores the threshold, current and previous progress, source observation id, seconds since launch, and whether migration had already been seen.

## Current blocker

Exact Pump.fun bonding-curve progress formula still needs live/source integration confirmation. The live smoke path does not fake progress. It preserves decoded bonding-curve account state and FDV proxy fields and marks `progress_pct_status=unresolved_formula` when no exact source progress percentage is available.

This means a first live smoke can validate source timing, admission sampling, raw state capture, queue behavior, and output schema before any threshold-profitability analysis exists.

## Safe smoke command

Synthetic smoke only; does not use live network:

```bash
cd /Users/dianeposs/Projects/meme-trader-pro

PYTHONPATH=/Users/dianeposs/Projects/meme-trader-pro python3 -m research.mtp_research.validation.run_bonding_curve_progress_recorder_v1 \
  --mode smoke \
  --data-root /Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1/smoke_YYYYMMDD_HHMMSS \
  --source-duration-seconds 300 \
  --followup-drain-seconds 300 \
  --sample-rate-percent 55 \
  --max-active-tracking 100
```

Short live smoke command, max 5 minutes source duration:

```bash
cd /Users/dianeposs/Projects/meme-trader-pro

PYTHONPATH=/Users/dianeposs/Projects/meme-trader-pro python3 -m research.mtp_research.validation.run_bonding_curve_progress_recorder_v1 \
  --mode live-smoke \
  --duration-seconds 300 \
  --followup-drain-seconds 180 \
  --sample-rate-percent 55 \
  --output-root /Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1/live_smoke_YYYYMMDD_HHMMSS
```

## T007K valuation ladder and wallet/dev forward data

T007K added data collection for later rule discovery without trading, paper trading, threshold tuning, buy/sell execution, or Mayhem changes.

New artifacts:

- `valuation_ladder_events.jsonl`
- `valuation_ladder_paths.jsonl`
- `wallet_dev_checkpoints.jsonl`

New forward-data surfaces:

- Dedicated valuation ladder band-cross events separate from true-curve progress crossings.
- Per-token ladder path rows with first-crossing timestamps, transition timings, retrace/drawdown fields, stall flags, migration flags, and stop reason.
- Wallet/dev checkpoint rows at birth, valuation bands when crossed, migration, and finalization.
- Explicit unavailable/deferred wallet/dev/creator-history status fields instead of silently omitting enrichment.
- Decode coverage summaries by source route, progress decode status, valuation coverage, and missing valuation reason.

### 2026-06-12 T007K 30-minute controlled run

Output root:

`/Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1/t007k_ladder_wallet_30m_20260612_113824`

Run id:

`bc-progress-20260612-183824`

Command:

```bash
cd /Users/dianeposs/Projects/meme-trader-pro

RUN_ID="t007k_ladder_wallet_30m_20260612_113824"

PYTHONPATH=/Users/dianeposs/Projects/meme-trader-pro python3 -m research.mtp_research.validation.run_bonding_curve_progress_recorder_v1 \
  --mode transaction-live-smoke \
  --duration-seconds 1800 \
  --followup-drain-seconds 300 \
  --sample-rate-percent 55 \
  --output-root "/Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1/${RUN_ID}"
```

Collector summary:

- Requested duration: `1800s`
- Actual transactionSubscribe duration: `1800.057205s`
- Websocket closed early: `false`
- Raw transaction notifications: `70692`
- Decoded birth rows: `11448`
- Unique birth mints: `722`
- Unique birth mints/min: about `24.07`
- Duplicate mint rows: `10726`
- Direct decoded rows: `697`
- Inner decoded rows: `13`
- Wrapped/compact decoded rows: `10738`
- Admitted births after dedupe: `100`
- Sample rejected after dedupe: `341`
- Capacity rejected after dedupe: `281`
- Active tracking max count: `100`
- Curve observation attempts: `100`
- Curve observations written: `100`
- Queue drops: `0`
- RPC failures: `0`
- HTTP 429 count: `0`
- Mayhem code modified: `false`

Latency:

- Birth-to-admission median: `13.363 ms`
- Birth-to-admission p90: `24.806 ms`
- Birth-to-first-curve-observation median: `194.375 ms`
- Birth-to-first-curve-observation p90: `215.413 ms`
- Normalized-birth-to-probe-start median: `3.976 ms`
- Probe duration median: `174.023 ms`
- First curve observation under 1s: `100/100`
- First curve observation under 2s: `100/100`
- First curve observation under 5s: `100/100`
- First curve observation over 10s: `0/100`
- First curve observation over 30s: `0/100`

Decode and valuation coverage:

- Decoded candidate progress: `34/100`
- Exact progress: `0/100`
- Decode errors: `66/100`
- Valuation present: `34/100`
- Valuation missing: `66/100`
- Missing valuation reasons: `curve_decode_failed=66`
- Error reasons: `account_not_found=66`
- Reserve scale modes: `raw_integer_units_6_decimals=34`, `unknown=66`

Coverage by source route:

- `transaction_subscribe:direct`: `31 decoded`, `63 decode_failed`
- `transaction_subscribe:inner`: `2 decoded`, `1 decode_failed`
- `transaction_subscribe:wrapped_compact`: `1 decoded`, `2 decode_failed`

Progress/valuation observations:

- Progress range among decoded rows: `0.0` to `58.402201`
- Valuation field source among present rows: `fdv_proxy`
- Valuation range among present rows: `4.0` to `86.562309`
- True-curve crossings emitted: `4`
- Valuation ladder events emitted: `0`
- Valuation ladder paths emitted: `100`
- Valuation band crossings emitted: `0`
- Tokens crossing `$30k`: `0`
- Tokens crossing `$35k`: `0`
- Tokens crossing `$36k`: `0`
- Tokens crossing `$40k`: `0`
- Tokens crossing `$50k`: `0`
- Tokens crossing `$60k`: `0`
- Tokens crossing `$100k`: `0`

Wallet/dev checkpoints:

- Wallet/dev checkpoints written: `200`
- Wallet metrics available: `0`
- Wallet metrics not available: `200`
- Dev metrics available: `0`
- Dev metrics not available: `200`
- Creator history available: `0`
- Creator history deferred: `200`
- Wallet enrichment errors counted: `66`

Artifact row counts:

- `birth_audit.jsonl`: `722`
- `curve_observations.jsonl`: `100`
- `threshold_crossings.jsonl`: `4`
- `valuation_ladder_events.jsonl`: `0`
- `valuation_ladder_paths.jsonl`: `100`
- `wallet_dev_checkpoints.jsonl`: `200`
- `migration_events.jsonl`: `0`

Conclusion:

The T007K schema and artifact wiring work, and streaming latency remains clean. The 30-minute run should not promote to a 2-hour collection yet because decoded progress and valuation coverage remained low at `34/100`, with `66/100` missing due to `account_not_found` curve decode failures. The ladder artifacts are structurally valid, but no valuation bands crossed and no ladder events were emitted in this sample.

The next blocker is valuation/progress coverage, not source latency. Before a longer collection, inspect why many immediate bonding-curve account probes return `account_not_found`, and verify whether the current `fdv_proxy` values are USD-scaled valuation or raw SOL/reserve-derived values. Capacity also capped the run at `100` active tracked births, causing `281` capacity rejections; raise `max_active_tracking` only after the valuation/progress decode path is fixed or explicitly accepted.

Recommendation: need valuation field fix and progress decode coverage fix before any 2-hour controlled run.

## T007L curve probe reliability and valuation units audit

T007L addressed the T007K research-data blocker without touching Mayhem, trading, paper trading, or execution code.

Changes:

- Added probe-attempt provenance in `probe_attempts.jsonl`.
- Added non-strategy retry diagnostics for `account_not_found` probes using configured retry delay labels.
- Added decoded-vs-derived bonding-curve PDA provenance using the existing Pump.fun PDA helper.
- Added explicit valuation unit fields: `fdv_proxy_raw`, `fdv_proxy_sol`, `fdv_proxy_usd`, `valuation_usd`, `valuation_source_field`, and `valuation_units_status`.
- Added reserve-derived FDV fields: `reserve_price_sol`, `reserve_fdv_sol`, `reserve_fdv_usd`, `reserve_fdv_status`, and proxy agreement fields.
- Added capacity rejection summaries by minute and source route.
- Added Axiom/manual reconciliation mode that writes `axiom_reconciliation.csv` and `axiom_reconciliation.jsonl` for user-provided migrated/new-pair mint lists.

Axiom reconciliation mode:

```bash
cd /Users/dianeposs/Projects/meme-trader-pro

PYTHONPATH=/Users/dianeposs/Projects/meme-trader-pro python3 -m research.mtp_research.validation.run_bonding_curve_progress_recorder_v1 \
  --mode axiom-reconcile \
  --output-root /path/to/t007/run/root \
  --axiom-mints "mint1,mint2,mint3"
```

or:

```bash
PYTHONPATH=/Users/dianeposs/Projects/meme-trader-pro python3 -m research.mtp_research.validation.run_bonding_curve_progress_recorder_v1 \
  --mode axiom-reconcile \
  --output-root /path/to/t007/run/root \
  --axiom-mints-path /path/to/axiom_mints.txt
```

For each mint, reconciliation reports whether it was seen by transactionSubscribe, normalized as a unique birth, admitted, sample rejected, capacity rejected, curve-probed, decoded, failed with `account_not_found`, assigned valuation/FDV, emitted valuation ladder crossings, and emitted migration events.

### T007K artifact diagnosis

T007K output root:

`/Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1/t007k_ladder_wallet_30m_20260612_113824`

Account-not-found concentration:

- `transaction_subscribe:direct`: `63 account_not_found`, `31 decoded`
- `transaction_subscribe:inner`: `1 account_not_found`, `2 decoded`
- `transaction_subscribe:wrapped_compact`: `2 account_not_found`, `1 decoded`
- Failed address pattern: `66/66` had a distinct bonding-curve account present.
- The failures were not concentrated only in wrapped/compact rows; most were direct rows because most admitted births were direct.

T007K conclusion: the immediate probe was too early for many accounts, or the RPC/account availability path was racing account creation. The stored bonding-curve account was present and distinct; T007L added PDA verification and retries to distinguish wrong-account from timing/indexing.

### 2026-06-12 T007L 5-minute probe/units smoke

Output root:

`/Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1/t007l_probe_units_smoke_20260612_122310`

Run id:

`bc-progress-20260612-192310`

Command:

```bash
cd /Users/dianeposs/Projects/meme-trader-pro

RUN_ID="t007l_probe_units_smoke_20260612_122310"

PYTHONPATH=/Users/dianeposs/Projects/meme-trader-pro python3 -m research.mtp_research.validation.run_bonding_curve_progress_recorder_v1 \
  --mode transaction-live-smoke \
  --duration-seconds 300 \
  --followup-drain-seconds 180 \
  --sample-rate-percent 55 \
  --sol-usd 135 \
  --output-root "/Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1/${RUN_ID}"
```

Core summary:

- Actual duration: `300.142066s`
- Raw transaction notifications: `10310`
- Decoded birth rows: `1781`
- Unique birth mints: `88`
- Admitted births after dedupe: `51`
- Sample rejected after dedupe: `37`
- Capacity rejected after dedupe: `0`
- Curve observation attempts: `90`
- Curve observations written: `117`
- Queue drops: `0`
- RPC failures: `0`
- HTTP 429 count: `0`
- Mayhem code modified: `false`

Probe reliability:

- First-attempt success count: `24`
- Retry success count: `27`
- Final account-not-found count: `0`
- Median attempts until success: `2`
- p90 attempts until success: `3`
- Median time to first success: `369.758 ms`
- p90 time to first success: `576.690 ms`
- Retry queue high-water mark: `5`
- Retry queue drops: `0`
- Account source used: `decoded_bonding_curve`
- Sampled account-not-found rows had `decoded_bonding_curve_account == derived_bonding_curve_account`.

Interpretation: account-not-found was timing/RPC account availability, not a wrong decoded bonding-curve address, in this smoke. The decoded account matched the derived Pump.fun bonding-curve PDA and retries recovered all initially missing accounts.

Valuation units and reserve FDV:

- `valuation_units_status_counts`: `usd_confirmed=78`, `missing_due_to_decode_error=39`
- `fdv_proxy_raw_range`: count `78`, min `541.105994`, max `267492.602341`
- `fdv_proxy_sol_range`: count `78`, min `4.008193`, max `1981.426684`
- `fdv_proxy_usd_range`: count `78`, min `541.105994`, max `267492.602341`
- `reserve_fdv_sol_range`: count `78`, min `4.008193`, max `1981.426684`
- `reserve_fdv_usd_range`: count `78`, min `541.105994`, max `267492.602341`
- Proxy agreement: sampled rows matched reserve-derived FDV.

Interpretation: previous T007K `fdv_proxy` values around `4.0` to `86.56` were SOL-denominated because no SOL/USD conversion was provided. With `--sol-usd 135`, valuation bands are USD-confirmed and can be emitted safely.

Crossings and migration:

- Threshold crossings written: `35`
- Valuation ladder events written: `18`
- Valuation ladder paths written: `51`
- Migration events written: `0`
- Tokens crossing `$30k`: `1`
- Tokens crossing `$36k`: `1`
- Tokens crossing `$40k`: `1`
- Tokens crossing `$50k`: `1`
- Tokens crossing `$60k`: `1`
- Valuation bands crossed: `$15k=2`, `$20k=2`, `$25k=1`, `$30k=1`, `$35k=1`, `$36k=1`, `$40k=1`, `$45k=1`, `$50k=1`, `$55k=1`, `$60k=1`, `$69k=1`, `$75k=1`, `$100k=1`, `$150k=1`, `$250k=1`.

Conclusion:

T007L resolves the two main T007K blockers for a short smoke: immediate `account_not_found` is recoverable with retry, and valuation units are now explicit and USD-confirmed when `--sol-usd` is supplied. Migration visibility remains unresolved because the smoke emitted no migration events; use the new Axiom reconciliation mode with user-provided migrated/new-pair mints to determine whether migrated tokens were missed at source, sampled out, capacity rejected, not decoded, or simply not marked as migrated by current artifacts.

Recommendation: ready for one 30-minute retry-enabled run with `--sol-usd` after Axiom reconciliation mints are provided or if the goal is only retry-enabled valuation ladder coverage. Do not promote to a 2-hour run until Axiom reconciliation explains visible migrated tokens and migration-event coverage.

## T007M retry-enabled 30-minute migration visibility and valuation guardrail run

Run timestamp: `2026-06-12 12:47:36 PDT`

Output root:

`/Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1/t007m_retry_valuation_migration_30m_20260612_124736`

Run id:

`bc-progress-20260612-194736`

### Pre-run guardrails

- Mayhem remains paused.
- No Mayhem collector process was active before the run.
- Mayhem collector behavior was not modified.
- ORICO output root was mounted and writable.
- This was one `30m` transaction-live smoke only.
- No trading, paper trading, threshold tuning, or buy/sell logic changes were made.
- `max_active_tracking` was raised to `500` for this smoke.
- `sol_usd` was set to `135`.

### Axiom valuation mismatch finding

A manually inspected Mayhem token showed:

- Axiom B.Curve: `8.44%`
- Collector progress decode: `8.441831%`
- Axiom market cap: about `$133k`
- Axiom liquidity: about `$267k`
- Collector reserve/FDV proxy: about `$267k`

Interpretation:

- True curve progress appears promising; the collector matched Axiom B.Curve on the inspected Mayhem example.
- The valuation ladder was not trusted; the collector value matched Axiom liquidity, not Axiom market cap.
- Mayhem valuation formula remains unresolved.
- Standard Pump.fun valuation formula is not proven broken, but it must be audited before ladder rules are used.

Guardrail implemented before this run:

- `valuation_ladder_emission_policy`: `market_cap_confirmed_only`
- Reserve-derived or generic FDV/USD values are still recorded for audit.
- Unconfirmed valuation values no longer emit valuation ladder crossings.
- Unconfirmed high-FDV values no longer create high-FDV migration candidates.
- New artifact: `valuation_formula_audit.jsonl`
- Axiom/manual reconciliation README is written even when no manual Axiom list is supplied.

### Collector result

- Requested duration: `1800s`
- Actual duration: `1800.0593919754028s`
- Websocket closed early: `false`
- Live source used: `helius_transaction_subscribe_pumpfun_create`
- Subscription/connect status: `available`
- Raw transaction notifications: `65472`
- Decoded birth rows: `9774`
- Unique birth mints: `654`
- Duplicate mint rows: `9120`
- Direct decoded rows: `634`
- Inner decoded rows: `13`
- Wrapped/compact decoded rows: `9127`
- Admitted after dedupe: `361`
- Sample rejected after dedupe: `293`
- Capacity rejected after dedupe: `0`
- Curve observation attempts: `631`
- Curve observations written: `837`
- Queue drops: `0`
- RPC failures: `0`
- HTTP 429 count: `0`
- Active tracking max count: `360`

Latency:

- Birth-to-admission median: `12.124 ms`
- Birth-to-admission p90: `21.381 ms`
- Birth-to-first-curve-observation median: `200.917 ms`
- Birth-to-first-curve-observation p90: `228.616 ms`

### Progress decode and migration visibility

- Exact progress decoded: `1`
- Candidate progress decoded: `566`
- Unresolved progress formula count: `0`
- Decode failures: `270`
- Threshold crossings written: `72`
- Migration events written: `1`
- Migration candidates written: `0`
- Stop reasons: `collector_finalized=360`, `migration_complete=1`

Progress threshold crossings:

- `40%`: `14`
- `50%`: `10`
- `55%`: `7`
- `60%`: `6`
- `62.5%`: `6`
- `65%`: `6`
- `67.5%`: `4`
- `70%`: `3`
- `72.5%`: `3`
- `75%`: `3`
- `80%`: `3`
- `85%`: `3`
- `90%`: `2`
- `95%`: `1`
- `100%`: `1`

Highest progress observations included one completed token at `100%` and several non-complete tokens above `60%`. This supports continuing to treat curve progress as the active T007 signal surface.

### Decode and valuation coverage

Decode coverage by route:

- `transaction_subscribe:direct`: `548 decoded`, `259 decode_failed`
- `transaction_subscribe:inner`: `9 decoded`, `3 decode_failed`
- `transaction_subscribe:wrapped_compact`: `10 decoded`, `8 decode_failed`

Valuation coverage by route:

- `transaction_subscribe:direct`: `548 present`, `259 missing`
- `transaction_subscribe:inner`: `9 present`, `3 missing`
- `transaction_subscribe:wrapped_compact`: `10 present`, `8 missing`

Valuation missing reason:

- `curve_decode_failed`: `270`

Valuation trust status:

- `untrusted_not_market_cap_confirmed`: `567`
- `missing_due_to_decode_error`: `270`

Valuation formula classifications:

- `standard_curve_needs_axiom_audit`: `566`
- `post_migration_unresolved`: `1`
- `valuation_missing`: `270`

Valuation ladder:

- Market-cap-confirmed valuation observations: `0`
- Untrusted valuation observations suppressed from ladder: `567`
- Valuation ladder events written: `0`
- Valuation band crossings: `0`

This is the correct guarded behavior. The run proves the collector can keep curve-progress telemetry active while preventing liquidity-like or unconfirmed FDV proxies from polluting valuation ladder artifacts.

### Artifacts

- Collector summary: `/Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1/t007m_retry_valuation_migration_30m_20260612_124736/collector_summary.json`
- Birth audit: `/Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1/t007m_retry_valuation_migration_30m_20260612_124736/birth_audit.jsonl`
- Curve observations: `/Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1/t007m_retry_valuation_migration_30m_20260612_124736/curve_observations.jsonl`
- Progress/threshold crossings: `/Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1/t007m_retry_valuation_migration_30m_20260612_124736/threshold_crossings.jsonl`
- Migration events: `/Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1/t007m_retry_valuation_migration_30m_20260612_124736/migration_events.jsonl`
- Migration candidates: `/Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1/t007m_retry_valuation_migration_30m_20260612_124736/migration_candidates.jsonl`
- Valuation formula audit: `/Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1/t007m_retry_valuation_migration_30m_20260612_124736/valuation_formula_audit.jsonl`
- Valuation ladder events: `/Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1/t007m_retry_valuation_migration_30m_20260612_124736/valuation_ladder_events.jsonl`
- Valuation ladder paths: `/Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1/t007m_retry_valuation_migration_30m_20260612_124736/valuation_ladder_paths.jsonl`
- Axiom reconciliation README: `/Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1/t007m_retry_valuation_migration_30m_20260612_124736/axiom_reconciliation_README.md`

### Decision

Decision label: `T007M_PROGRESS_PIPELINE_OK_VALUATION_LADDER_BLOCKED`

Recommendation:

Do not promote valuation ladder rules or run valuation-ladder strategy research yet. First reconcile market-cap formula with manual Axiom examples across standard Pump.fun, Mayhem, migrated, and non-migrated curve tokens. Progress-only collection can continue if the next milestone is true curve-progress behavior, but any next live run should have the watcher open and verified with full stats before start.

## External stack notes from Solana meme-launch edge-signal PDF

Source reviewed:

`/Users/dianeposs/Downloads/Most Likely Edge Signals for Automated Scalp Trading of Solana Meme Launches.pdf`

These notes are design input only. They are not an edge claim, not a trading rule, and not permission to re-enable valuation ladder bands.

### Stack implications for T007

The PDF supports keeping T007 focused on a thesis-ready forward dataset rather than a single progress threshold. The strongest forward-data stack should separate:

- bonding-curve phase features: true curve progress, curve velocity, trade efficiency, buyer breadth, bot/organic-share proxy, holder concentration, creator/dev behavior, and creator-linked distribution
- migration detection features: canonical Pump.fun completion, PumpSwap market-account creation, migrated pool address, migration timing, and whether the mint was admitted, sampled out, or unseen by the birth source
- post-migration AMM features: real liquidity, executable quote depth, price impact, route quality, buy/sell flow, slippage deterioration, and dump/concentration signals
- execution-stress diagnostics: priority-fee pressure, failed transaction share, quote-to-send latency, and route disappearance

### Source hierarchy to preserve

The PDF recommends raw on-chain state as source of truth, with venue APIs used for enrichment, routing, quotes, and debugging. For T007 this maps to:

- raw launch and trade stream: Helius `transactionSubscribe` or LaserStream-style stream where available
- curve state: Pump.fun bonding-curve PDA account state and reserve fields
- migration state: PumpSwap `programSubscribe` market-account listener with account-size, discriminator, and quote-mint filters
- holder and creator features: Solana token account ownership, token-account deltas, mint authority/freeze authority, Token-2022 extension state when relevant
- post-migration depth: Jupiter/Raydium quotes and pool state, kept separate from bonding-curve progress
- manual/debug overlays: Axiom, Solscan, SolanaFM, Helius Orb, Bitquery, Birdeye, and DexScreener as reconciliation or enrichment sources, not primary ground truth

### Feature families T007AA should materialize

The PDF reinforces the planned T007AA event model. Future schema work should make these fields explicit, even when unavailable:

- `feature_curve_progress_pct`
- `feature_curve_velocity_5s`, `feature_curve_velocity_10s`, `feature_curve_velocity_30s`, `feature_curve_velocity_60s`
- `feature_trade_efficiency_progress_per_trade`
- `feature_trade_efficiency_seconds_to_next_5pct`
- `feature_unique_buyers_since_launch`
- `feature_unique_buyers_since_prior_checkpoint`
- `feature_buy_sell_count_ratio`
- `feature_buy_sell_volume_ratio`
- `feature_non_bot_share_status`
- `feature_holder_concentration_top_1_3_5_10_20_pct`
- `feature_creator_prior_launch_count`
- `feature_creator_prior_migration_count`
- `feature_creator_sold_before_40_60_70_migration`
- `feature_creator_retained_balance_status`
- `diagnostic_priority_fee_pressure`
- `diagnostic_failed_tx_share`
- `diagnostic_execution_cost_pressure_status`
- `outcome_migration_seen`
- `outcome_launch_to_migration_seconds`
- `outcome_post_migration_depth_status`
- `outcome_post_migration_max_high`
- `outcome_post_migration_drawdown`

Missing or deferred fields should be explicit with status values such as `available`, `partial`, `deferred`, `not_available`, or `error`.

### Guardrails from the PDF

- Do not treat "above 60% curve progress" as a standalone edge. The PDF frames the incremental edge as how the token reached that state: velocity, trade efficiency, breadth, and low bot-like flow.
- Do not combine pre-migration and post-migration strategies too early. A curve-progress continuation setup and a migration-confirmation setup have different data, execution, and drawdown profiles.
- Do not trust valuation or market-cap bands until the market-cap formula is confirmed. The PDF separates true curve state from executable AMM depth and quote quality.
- Segment future research by venue, quote asset, and protocol era. Pump.fun SOL launches, Pump.fun USDC launches, PumpSwap migration, and Raydium LaunchLab should not be pooled blindly.
- Use decision-time-safe feature naming. Entry features must use only observations available at or before the decision point; post-migration highs, drawdowns, and returns must stay as outcomes.
- Treat fee drag, priority fees, tips, slippage, and failed-fill risk as first-class diagnostics before any later paper or live execution work.

### Current T007 interpretation

The PDF strengthens the current decision to keep true curve progress collection active while suppressing unconfirmed valuation ladders. It also supports the PumpSwap `programSubscribe` migration lane fix: canonical pool creation is the right global migration signal for post-curve labeling, while noisy PumpSwap transaction subscriptions should remain audit/debug only.

Next technical priority after PumpSwap migration visibility passes is T007AA schema expansion for curve velocity, trade efficiency, buyer breadth, holder concentration, creator behavior, execution-stress diagnostics, and post-migration depth outcomes. This remains data collection and analysis scaffolding only: no trading, no paper trading, no threshold tuning, and no edge claim.

## T007AB quote-asset normalization

T007AB adds quote-aware collection before any long T007AA thesis-ready run.

Guardrails:

- No Mayhem collector changes.
- No trading or paper trading changes.
- No execution-code changes.
- No valuation ladder re-enable.
- Valuation ladder policy remains `market_cap_confirmed_only`.

Canonical constants now include:

- `PUMP_FUN_PROGRAM_ID`
- `PUMPSWAP_PROGRAM_ID`
- `SOL_MINT`
- `USDC_MINT`

USDC mainnet mint used:

`EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v`

Quote identity fields are now carried where available:

- `quote_mint`
- `quote_asset`
- `quote_asset_status`
- `quote_to_usd_rate`
- `quote_to_usd_source`
- `valuation_quote_units`

Quote policy:

- SOL quote uses CLI `--sol-usd` when supplied.
- USDC quote uses `quote_to_usd_rate=1.0` and `quote_to_usd_source=usdc_assumed_1`.
- Unknown or unsupported quote assets do not become USD-confirmed valuation ladder sources.
- USDC depeg handling is not implemented; rows include an explicit warning where applicable.

PumpSwap migration-lane change:

- Before T007AB, the PumpSwap `programSubscribe` route filtered market accounts to SOL quote mint only.
- A no-quote-filter audit proved too noisy: unsupported quote candidates dominated the stream.
- Final T007AB default uses separate quote-filtered PumpSwap `programSubscribe` requests for SOL and USDC on the same route.
- The route still decodes and classifies `quote_mint` as SOL, USDC, unknown, or unsupported for audit and fixture coverage.
- SOL and USDC PumpSwap pools can produce confirmed global migration events.
- Unsupported quote assets are written as candidates rather than silently excluded.

Summary/reporting fields now include quote segmentation:

- births by quote asset
- admitted/sample/capacity rejected births by quote asset
- curve observations by quote asset
- progress crossings by quote asset
- migration events by quote asset
- PumpSwap raw/confirmed/global migration events by quote asset
- missing quote mint count
- unsupported quote asset count

This makes future T007 research quote-aware and prevents SOL and USDC launches from being pooled blindly.

## 2026-06-16 persistent lifecycle architecture decision

Status: campaign-first scan workflow is deprecated for thesis/later-trading readiness. No live scan is authorized by this section.

The latest bounded proofs showed that transport, birth decoding, curve verification, PumpSwap migration detection, and post-migration observation can all work as components. The remaining blocker is architectural: a temporary scan cannot create full-path lifecycle data for tokens that were born before that scan began.

Corrected interpretation of recent source-coverage audits:

- Many PumpSwap migrations are valid migrations, but their launches replay before the campaign window.
- These are `preexisting_before_watcher`, not live birth-source misses.
- A 10-minute campaign can prove plumbing, but it cannot prove full birth-to-migration lifecycle coverage unless a token both launches and migrates during that same window.

Required next milestone:

```text
T007 Persistent Lifecycle Watcher v1
```

This milestone must build durable per-mint state before more thesis scans. The source of truth must become:

```text
always-on lanes -> persistent lifecycle state -> watcher/readiness gates -> exported artifacts
```

The old source of truth is no longer acceptable for live-trading-grade collection:

```text
start scan -> collect artifacts -> postprocess artifacts -> discover preexisting migrations
```

Persistent lifecycle requirements:

- SQLite WAL current-state store.
- Append-only JSONL audit ledger.
- Pump.fun birth lane and PumpSwap migration lane write to the same mint lifecycle record.
- Watcher displays persistent lifecycle classes and current-window counts separately.
- Existing CSV/JSON artifacts become exports from state, not the control plane.
- Long scans remain blocked until the persistent watcher passes a bounded 10-minute proof.

Required migrated-mint classes:

```text
tracked_from_birth_full_path
tracked_from_birth_missing_feature
preexisting_before_watcher
migration_only_untracked
replay_unresolved
true_source_miss
```

Trading status remains blocked. The persistent lifecycle watcher is a data-plane prerequisite, not an execution system. Paper/shadow/live trading work requires later explicit milestones and safety gates.

Authoritative docs:

- `AGENTS.md`
- `docs/research/T007_PERSISTENT_LIFECYCLE_WATCHER_ARCHITECTURE.md`
- `docs/superpowers/specs/2026-06-16-t007-persistent-lifecycle-watcher-design.md`
- `docs/superpowers/plans/2026-06-16-t007-persistent-lifecycle-watcher-v1.md`

## 2026-06-16 Persistent Lifecycle Watcher v1 Status

The collector now has a persistent lifecycle state path for thesis-readiness evaluation. Existing artifact rows are mirrored into a normalized SQLite state store during collection, including global PumpSwap migration rows that previously bypassed the main recorder JSONL hook.

Readiness implication: the next validation step is one bounded 10-minute proof scan. Longer scans remain blocked until that proof confirms persistent lifecycle artifacts, migration linkage, source duration quality, queue/RPC health, and zero safety regressions.

Safety status: no trading, paper trading, wallet, private-key, signing, send-transaction, Mayhem, or valuation-ladder behavior was enabled by this change.

## T007 Production Lifecycle Data Collection V2 Finalized

Status: implemented as the production readiness target before any scan longer than 10 minutes.

Core architecture now required by the collector/readiness layer:

- Canonical lifecycle truth is the SQLite event ledger in `t007_lifecycle_state.sqlite`, with `domain_events`, `raw_source_envelopes`, mint identity, pool identity, watermarks, and source-health snapshots.
- Legacy JSONL/CSV artifacts remain compatibility exports. They are no longer allowed to be interpreted as the only source of truth for readiness.
- Helius Developer-tier source hierarchy is explicit: Pump.fun `transactionSubscribe` for canonical births/trades, `logsSubscribe` as a sentinel, dynamic curve account observation after birth, filtered PumpSwap pool-state discovery for SOL/USDC migrations, and bounded read-only replay only for archive repair.
- Bounded replay is not decision-time evidence. It cannot create live-trade-safe thesis rows.
- Execution-cost fields are non-blocking for thesis data collection. They remain later trading-friction diagnostics only.
- Valuation ladder emissions remain suppressed until market-cap source and quote normalization are confirmed by protocol-specific evidence.
- PumpSwap 245-byte pool accounts are the verified default. The observed 301-byte layout is classified as pending fixture/IDL proof and must not be counted as a verified production layout without that proof.
- The watcher/readiness contract must expose raw candidates, verified births, candidate exclusions, curve-account verification, decode failures, market-cap availability, trade-flow/holder-dev availability, migrations, full-path linkage, source gaps, queue drops, and DB ledger consistency.
- A 10-minute proof may pass with zero migrations if source health and pre-migration evidence are clean. A controlled run with migrations fails if those migrations do not link to decision-safe full paths.

Production blocker definition:

A migrated mint is thesis-usable only when it has live, decision-time-safe birth, verified curve decode, market-cap/progress, trade-flow, holder/dev, PumpSwap pool verification, post-migration depth, and quote observation. Replay/backfill can repair archive visibility but cannot be counted as live decision-safe evidence.

## T007 Event-First Production Gap Closure

This pass closes the specific audit gap between having production structures and
using them as the live source of truth.

New hard rules:

- Every lifecycle artifact row is synchronously normalized into the canonical SQLite store before JSONL compatibility output is written.
- Weak Pump.fun create-like rows are `pump_birth_rejected`, not usable births, unless mint, creator, bonding curve, associated bonding curve, quote identity, and source signature are present and PDA/ATA checks do not contradict the parsed accounts.
- `account_not_found` is first classified as a bounded visibility retry, then only becomes `curve_account_not_found_final` after retry budget exhaustion.
- Unknown/unsupported layouts are separate from generic decode failure.
- Migration backfill jobs carry campaign window fields: campaign start, campaign end, source duration, watcher window id, and originating run id.
- Replay/backfill rows are explicitly non-decision-safe.
- Watcher status must show global migrations, persistent-birth linkage, live-window linkage, decision-safe full paths, true source misses, preexisting rows, replay-unresolved rows, and restart gaps separately.
- Threshold crossing is an outcome feature, not a full-path evidence requirement.
- Execution-cost evidence remains non-blocking for thesis data collection.

This does not enable trading, paper trading, wallet access, private keys,
signing, sendTransaction, or valuation ladder emissions.

## T007 Proof Hardening V4

This pass adds the formal proof and production-invariant layer around the event-first architecture.

New requirements before any long scan:

- L0 compile proof must pass before runtime proof.
- L1 deterministic fixtures must cover verified birth, rejected birth, curve decode, PumpSwap pool decode, and quote/depth fixtures.
- L2 10-minute proof must show event-first SQLite, DB consistency, verified births, curve decode, market-cap/progress availability, no queue drops, and complete watcher contract fields.
- L3 controlled migration proof must show at least one migration linked to a decision-safe full lifecycle path including strict quote/depth evidence.

New production metadata:

- Every raw/domain event carries observed commitment, first-seen slot/time, confirmed/finalized slot/time when available, reorg/drop flag, and payload hash.
- Source gaps are represented by lane, subscription, connection, provider region, commitment, missed slot range, reason, and repair status.
- Runs have manifests with git/schema/codec/program/quote/subscription/rate-limit/timing identity.
- Protocol layouts have registry rows for codec version, discriminator, account length, validation fixture, parser git SHA, and decode confidence.
- Lifecycle invariant violations are persisted as first-class proof blockers.
- Decision snapshots are hashable and persist exact input evidence hashes.

Readiness change:

A run is not production-ready merely because it writes artifacts. It must prove DB ledger consistency, no impossible states, complete watcher contract fields, manifest/layout registry presence, latency histogram presence, and correct live/replay separation.

## T007 Canonical Single Writer Repair

The failed L2 proof was a source-health pass and canonical-evidence fail. The repair target is now explicit:

- `T007SqliteWriter` is the only production writer allowed to execute SQLite writes for proof evidence.
- The legacy lifecycle collector adapter is disabled for runtime writes and remains compatibility-only.
- The canonical DB is created on internal local disk; the ORICO run root receives a pointer file and compatibility artifacts after DB commit.
- Artifact rows are exported only after SQLite commits and carry `raw_envelope_id`, `domain_event_id`, `canonical_db_path`, `exported_after_db_commit`, and DB commit sequence metadata.
- `run_manifest` and `protocol_layout_versions` are bootstrapped before source evidence is accepted by the event bus.
- Malformed/corrupt SQLite errors are fatal and write `t007_db_fatal_status.json` instead of allowing thousands of repeated DB errors.
- Readiness must compare source/artifact counts against canonical SQLite counts and fail if capture ratios are below proof thresholds.

No scanner/RPC/WebSocket tuning is part of this repair. The source layer already produced enough data; the proof blocker is canonical durability and materialization.
