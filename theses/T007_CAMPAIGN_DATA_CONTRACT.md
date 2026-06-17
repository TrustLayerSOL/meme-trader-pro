# T007 Campaign Data Contract

Status: active contract for future T007 Pump.fun / PumpSwap forward-data campaigns.

This contract is data collection and analysis scaffolding only. It does not enable trading, paper trading, wallet use, signing, execution, or valuation ladder bands.

## PDF compliance gate before any further scan

The PDF-driven architecture requires the T007 collector to treat Pump.fun curve state, PumpSwap migration/pool state, quote-asset segmentation, and replayable raw events as separate first-class lanes. T007AH has now materialized the remaining feature-family schemas and diagnostic writers; the next allowed action is one short validation scan to measure live coverage, not thesis/profitability interpretation:

- PumpSwap global migration events are deduped and integrated into campaign summaries.
- Unknown migrated mints enqueue bounded migration-to-birth replay/backfill jobs.
- Backfilled birth rows preserve launch signature, launch slot/time, creator, bonding curve, quote asset, capture route, capture method, confidence, and trigger provenance.
- Every normalized birth receives a thin minimal curve path independent of deep sampling.
- Sample-rejected births can produce `SAMPLE_REJECTED_WITH_THIN_PATH`.
- Migrated mints receive one completeness grade: `FULL_PATH`, `THIN_PATH`, `SAMPLE_REJECTED_WITH_THIN_PATH`, `SAMPLE_REJECTED_WITH_MIGRATION`, `BACKFILLED_BIRTH_WITH_MIGRATION`, `MIGRATION_ONLY_PREEXISTING`, `MIGRATION_ONLY_SOURCE_MISS`, `MIGRATION_ONLY_REPLAY_UNRESOLVED`, or `POST_ONLY`.
- Campaign quality gates fail on launched-during-campaign `MIGRATION_ONLY_SOURCE_MISS` unless there is an exact unresolved reason.
- SOL and USDC quote handling stays explicit and segmented.
- Valuation ladder emissions stay suppressed unless the value source is confirmed market cap.

Signals from the PDF now have schema-ready diagnostic lanes for per-trade flow, bot/organic share, buyer breadth, holder distribution, creator/dev behavior, post-migration depth/quotes, execution cost, and execution-stress metrics. Live coverage remains a thesis-testing blocker: the campaign summary must report unavailable or partial rows explicitly rather than silently omitting them.

### T007AG implementation status

The next-scan plumbing blockers above were implemented and fixture-validated in `T007AG_Automatic_Migration_Backfill_And_Thin_Track_Validation`.

Validation artifacts:

- `outputs/theses/t007ag_migration_backfill_thin_track_validation/summary.md`
- `outputs/theses/t007ag_migration_backfill_thin_track_validation/migration_backfill_validation.csv`
- `outputs/theses/t007ag_migration_backfill_thin_track_validation/thin_track_validation.csv`
- `outputs/theses/t007ag_migration_backfill_thin_track_validation/campaign_quality_gate_after_t007ag.json`

This clears the blocker for a short controlled validation run only. It does not clear the blockers for thesis testing, profitability analysis, paper trading, live trading, or long thesis collection.

## Purpose

Every T007 campaign must produce one multi-lane event-replay dataset that can later test the thesis stack:

- bonding-curve progress
- curve velocity
- curve acceleration
- trade efficiency
- buyer breadth
- buy/sell pressure
- bot-like versus organic flow
- holder distribution
- creator/dev behavior
- Pump.fun migrate events
- PumpSwap pool creation
- post-migration depth and quote quality
- execution-cost realism
- sell-rule outcome fields

Pump.fun curve completion, Axiom "Migrated", and PumpSwap pool creation are separate events. They must be recorded separately and reconciled later.

## Required campaign manifest

Each run writes `campaign_manifest.json` with:

- `campaign_id`
- `run_id`
- `started_at`
- `ended_at`
- `requested_duration_seconds`
- `actual_duration_seconds`
- `source_duration_seconds`
- `followup_drain_seconds`
- `sample_rate_percent`
- `max_active_tracking`
- `active_lifecycle_policy_version`
- `quote_normalization_version`
- `curve_progress_formula_version`
- `migration_detector_version`
- `valuation_ladder_policy`
- `valuation_ladder_enabled`
- `trading_enabled`
- `paper_trading_enabled`
- `mayhem_touched`
- `local_staging_root`
- `archive_root`
- `archive_status`
- `archive_manifest_path`
- `sol_usd`
- `quote_assets_supported`
- `source_lanes_enabled`
- `tests_checks_run_before_campaign`
- `git_status_summary`

Required fixed safety values:

- `valuation_ladder_policy = market_cap_confirmed_only`
- `valuation_ladder_enabled = false`
- `trading_enabled = false`
- `paper_trading_enabled = false`
- `mayhem_touched = false`

## Required artifacts

Each campaign must create these artifacts, even when a data family is not live yet:

- `campaign_manifest.json`
- `birth_audit.jsonl`
- `curve_observations.jsonl`
- `true_curve_threshold_crossings.jsonl`
- `curve_velocity_events.jsonl`
- `curve_acceleration_events.jsonl`
- `trade_flow_events.jsonl`
- `organic_flow_events.jsonl`
- `holder_distribution_snapshots.jsonl`
- `dev_behavior_events.jsonl`
- `global_migration_events.jsonl`
- `global_migration_event_duplicates.jsonl`
- `global_migration_candidates.jsonl`
- `post_migration_observations.jsonl`
- `execution_cost_observations.jsonl`
- `token_path_summary.jsonl`
- `valuation_formula_audit.jsonl`
- `wallet_dev_checkpoints.jsonl`
- `probe_attempts.jsonl`
- `live_status.json`
- `collector_summary.json`

Unavailable families must be explicit. Use status values:

- `available`
- `partial`
- `deferred`
- `not_available`
- `not_implemented`
- `error`

Silent omission is not allowed.

## Quote-asset handling

Supported quote assets:

- `SOL`
- `USDC`

Required quote fields where available:

- `quote_mint`
- `quote_asset`
- `quote_asset_status`
- `quote_to_usd_rate`
- `quote_to_usd_source`
- `quote_to_usd_warning`
- `valuation_quote_units`

SOL policy:

- Use CLI/manual `sol_usd` when supplied.
- Set `quote_to_usd_source = manual_cli_sol_usd`.

USDC policy:

- Set `quote_to_usd_rate = 1.0`.
- Set `quote_to_usd_source = usdc_assumed_1`.
- Record warning `usdc_depeg_handling_not_implemented`.

Unknown or unsupported quote policy:

- Do not emit confirmed USD valuation fields.
- Do not emit valuation ladder bands.
- Preserve the raw quote mint and mark status.

Future analysis must segment by quote asset and must not pool SOL and USDC blindly.

## Birth lane fields

Each `birth_audit.jsonl` row should include:

- `campaign_id`
- `run_id`
- `mint`
- `launch_signature`
- `slot`
- `block_time`
- `received_at`
- `source_route_type`
- `source_decode_route`
- `creator`
- `bonding_curve_account`
- `associated_bonding_curve`
- `quote_mint`
- `quote_asset`
- `quote_asset_status`
- `token_program`
- `token_decimals`
- `token_total_supply`
- `metadata_uri`
- `token_name`
- `token_symbol`
- `is_mayhem_mode`
- `is_cashback_coin`
- `launch_venue_program`
- `admitted`
- `admission_reason`
- `sample_decision_hash`
- `capacity_rejection_reason`

## Curve observation fields

Each `curve_observations.jsonl` row should include:

- `campaign_id`
- `run_id`
- `mint`
- `observation_id`
- `slot`
- `block_time`
- `received_at`
- `seconds_since_launch`
- `bonding_curve_account`
- `associated_bonding_curve`
- `quote_mint`
- `quote_asset`
- `real_token_reserves_raw`
- `real_token_reserves_scaled`
- `virtual_token_reserves_raw`
- `virtual_sol_or_quote_reserves_raw`
- `real_sol_or_quote_reserves_raw`
- `token_total_supply_raw`
- `token_total_supply_scaled`
- `complete`
- `progress_pct`
- `progress_pct_status`
- `reserve_scale_mode`
- `progress_formula_version`
- `decode_status`
- `error_reason`
- `probe_attempt_index`
- `probe_delay_ms`
- `account_source`

Progress status enum:

- `decoded_exact`
- `decoded_candidate`
- `decode_error`
- `unresolved_formula`
- `unavailable`

## Threshold crossings

`true_curve_threshold_crossings.jsonl` records first crossings only for:

- `10%`
- `20%`
- `30%`
- `40%`
- `50%`
- `55%`
- `60%`
- `62.5%`
- `65%`
- `67.5%`
- `70%`
- `72.5%`
- `75%`
- `80%`
- `85%`
- `90%`
- `95%`
- `100%`

Required fields:

- `campaign_id`
- `run_id`
- `mint`
- `threshold_pct`
- `crossing_received_at`
- `crossing_slot`
- `seconds_since_launch`
- `previous_progress_pct`
- `crossing_progress_pct`
- `previous_threshold_pct`
- `seconds_since_previous_threshold`
- `progress_pct_status`
- `migration_seen_before_crossing`
- `complete_seen_before_crossing`
- `quote_asset`
- `source_observation_id`

## Velocity, acceleration, and trade efficiency

Velocity windows:

- last `5s`
- last `10s`
- last `30s`
- last `60s`
- since launch

Segment windows:

- `20 -> 40`
- `40 -> 50`
- `50 -> 60`
- `60 -> 65`
- `65 -> 70`
- `70 -> 75`
- `75 -> 80`
- `80 -> 90`
- `90 -> 100`

Required velocity fields:

- `campaign_id`
- `run_id`
- `mint`
- `as_of_received_at`
- `as_of_seconds_since_launch`
- `from_progress_pct`
- `to_progress_pct`
- `window_seconds`
- `progress_delta`
- `progress_per_second`
- `progress_per_minute`
- `trade_count_in_window`
- `progress_per_trade`
- `quote_asset`
- `enough_data`
- `feature_status`

Acceleration fields:

- `recent_window_seconds`
- `prior_window_seconds`
- `recent_velocity`
- `prior_velocity`
- `acceleration_ratio`
- `zero_prior_velocity`
- `capped_acceleration_ratio`
- `segment_recent`
- `segment_prior`
- `enough_data`

All velocity and acceleration rows must be decision-time safe.

## Trade flow and organic-flow fields

Trade-flow rows must eventually include:

- side
- trader wallet
- fee payer
- token amount
- quote amount
- quote asset
- buy/sell counts
- buy/sell volumes
- net quote inflow
- unique buyers/sellers
- buy/sell ratios
- consecutive buys/sells
- `trade_flow_status`

Organic-flow rows must eventually include:

- repeated wallets
- repeated trade sizes
- timing regularity
- tiny trade share
- same funding cluster if available
- bot-like trade share
- non-bot trade share
- bot-like volume share
- non-bot volume share
- `organic_share_status`

Until live data is supplied, rows must use schema-ready markers or explicit `not_available`, `partial`, or `error` statuses.

## Holder and dev behavior fields

Holder snapshots must be checkpoint based and must not block birth-to-first-curve-observation.

Required holder checkpoints:

- birth / first observation
- `40%`
- `50%`
- `60%`
- `65%`
- `70%`
- `75%`
- `80%`
- migration
- `30s` after migration
- `60s` after migration
- `120s` after migration
- `300s` after migration

Required holder fields include holder count, top holder percentages, exclusion flags, sniper/early-wallet percentage, status, latency, and error reason.

Dev behavior must be point-in-time safe. For a token launched at time `T`, creator history may only use events before `T`.

Required dev fields include creator wallet, prior launches, prior migrations, prior max progress, creator sells before key thresholds, creator retained balance, authority status, Token-2022 extension status, and `dev_behavior_status`.

## Migration and post-migration lanes

Global migration detection is independent of admission and sampling.

Migration rows must include:

- Pump.fun migrate detection
- PumpSwap pool creation detection
- source route
- confidence
- pool/pair address
- base mint
- quote mint
- quote asset
- seen/admitted/sample/capacity/pruned match fields
- progress before migration
- threshold-to-migration timing

Post-migration observations should be collected at:

- `0s`
- `5s`
- `15s`
- `30s`
- `60s`
- `120s`
- `300s`
- `600s`

If market cap or price is not confirmed, keep related fields null and status unresolved.

## Execution-cost lane

Execution-cost rows should collect:

- recent prioritization fee percentiles
- account-specific fee sample if available
- failed transaction share
- Jito tip context if available
- estimated total fee
- `execution_cost_status`

This remains diagnostic-only and does not enable trading.

## Token path summary

`token_path_summary.jsonl` must contain one final row per token with:

- quote asset
- admission status
- finalization reason
- highest/final progress
- threshold booleans
- first crossing time by threshold
- seconds to threshold
- seconds between thresholds
- migration status
- seconds to migration
- threshold-to-migration seconds
- post-migration observation count
- feature-family statuses
- missing-data flags
- data-quality flags

## Decision-time safety

Naming convention:

- `feature_*` means available at or before decision time.
- `outcome_*` means future result or label.
- `diagnostic_*` means debug/audit data.

Examples:

- `feature_velocity_10s_at_70pct`
- `feature_unique_buyers_at_70pct`
- `feature_creator_sold_before_70pct`
- `outcome_migrated_after_70pct`
- `outcome_seconds_70pct_to_migration`
- `diagnostic_decode_status`

Post-migration data must never be used as a pre-migration entry feature.

## Analysis scaffold

`research/mtp_research/validation/t007aa_forward_thesis_dataset_report.py` reads one or more campaign folders and writes:

- `summary.md`
- `curve_progress_threshold_outcomes.csv`
- `curve_velocity_outcomes.csv`
- `curve_acceleration_outcomes.csv`
- `trade_efficiency_outcomes.csv`
- `buyer_growth_outcomes.csv`
- `bot_share_outcomes.csv`
- `holder_distribution_outcomes.csv`
- `dev_behavior_outcomes.csv`
- `migration_timing_outcomes.csv`
- `post_migration_exit_outcomes.csv`
- `execution_cost_quality.csv`
- `data_quality_report.csv`

The initial report computes availability and missing-data rates only. It must not optimize trading rules.
