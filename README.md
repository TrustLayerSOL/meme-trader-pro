# MemeTraderPro v3 (Research-First)

MemeTraderPro v3 is a research-first Solana meme coin trading intelligence project.

## Structure

- `legacy/v2/` — preserved current v2 prototype
- `legacy/v1/` — placeholder for historical v1 code if found later
- `docs/` — strategy, data, validation, and risk documentation
- `configs/` — strategy, venue, fees, and risk presets
- `research/mtp_research/` — research pipeline modules and backtesting scaffold
- `trader/` — v3 execution surface and adapter scaffolding
- `shared/` — shared schema artifacts
- `data/` — managed datasets for new v3 workflows

## Principles

v3 is not a live trading bot yet.

Initial focus is historical backtesting and step-forward validation under strict research controls.

Primary MVP strategy is post-launch momentum with quality/risk filters.

Secondary future strategies (not started):

- post-flush mean reversion
- migration/graduation event trading

Avoid for MVP:

- pure first-block sniping
- generalized copy trading
- MEV/bundle racing

## Milestone 2: Candidate Registry

Research discovery is now backed by a v3 candidate registry:

- `LaunchCandidate` model in `research/mtp_research/ingestion/models.py`
- JSONL persistence in `data/normalized/candidate_registry.jsonl`
- Upsert-by-mint merge semantics (earliest first-seen + merged metadata)

Run candidate ingestion and registry update:

```bash
./trading_env/bin/python -m research.mtp_research.ingestion.run_candidate_registry
```

Fallback (if virtualenv path differs):

```bash
python3 -m research.mtp_research.ingestion.run_candidate_registry
```

Run the focused registry tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_candidate_registry.py
```

Fallback (if virtualenv path differs):

```bash
python3 -m pytest research/tests/test_candidate_registry.py
```

## Milestone 3: Helius Historical Adapter Foundation

v3 now has a low-cost Helius JSON-RPC adapter foundation for historical signature discovery. The first supported method is `getSignaturesForAddress`; full transaction-body hydration comes later.

Run the focused Helius adapter tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_helius_backfill.py
```

Example real probe command:

```bash
./trading_env/bin/python -m research.mtp_research.ingestion.run_helius_backfill_probe <ADDRESS> --limit 10
```

## Milestone 4: Raw Transaction Store + Backfill Job Ledger

v3 now has the raw historical data layer for replay-safe research: backfill targets, a raw Helius transaction JSONL store, a normalized event JSONL store, and a basic `transaction_observed` normalizer.

Run the focused Milestone 4 tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_raw_transaction_store.py
./trading_env/bin/python -m pytest research/tests/test_backfill_jobs.py
./trading_env/bin/python -m pytest research/tests/test_normalized_event_store.py
./trading_env/bin/python -m pytest research/tests/test_basic_transaction_normalizer.py
```

Example dry run:

```bash
./trading_env/bin/python -m research.mtp_research.ingestion.run_backfill_target <ADDRESS> --role wallet --limit 10 --dry-run
```

Example real run:

```bash
./trading_env/bin/python -m research.mtp_research.ingestion.run_backfill_target <ADDRESS> --role wallet --limit 10
```

## Milestone 5: DEX Event Parser Foundation

v3 now has a conservative raw transaction parser that turns stored Solana `jsonParsed` transaction bodies into observed transaction events with account summaries, program invocations, token balance deltas, and venue classification metadata.

Run the focused Milestone 5 tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_solana_transaction_parser.py
./trading_env/bin/python -m pytest research/tests/test_venue_classifier.py
./trading_env/bin/python -m pytest research/tests/test_parse_raw_transactions_cli.py
```

Example parser run:

```bash
./trading_env/bin/python -m research.mtp_research.ingestion.run_parse_raw_transactions --limit 100
```

## Milestone 6: Trade Event Normalization v0

v3 now has conservative balance-delta trade inference for likely swaps, possible buys, possible sells, token accumulation, and token distribution. These are research candidates, not strategy rules or live trading signals.

Run the focused Milestone 6 tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_trade_event_normalizer.py
./trading_env/bin/python -m pytest research/tests/test_run_normalize_trade_events.py
```

Example run:

```bash
./trading_env/bin/python -m research.mtp_research.ingestion.run_normalize_trade_events --limit 100
```

## Milestone 7: Feature Snapshot Builder v0

v3 now builds rolling token-level feature snapshots from normalized local events. These snapshots are the first direct inputs for the future event-driven backtester.

Run the focused Milestone 7 tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_feature_snapshot_store.py
./trading_env/bin/python -m pytest research/tests/test_feature_snapshot_builder.py
./trading_env/bin/python -m pytest research/tests/test_run_build_feature_snapshots.py
```

Example run:

```bash
./trading_env/bin/python -m research.mtp_research.features.run_build_feature_snapshots --snapshot-step-sec 60 --max-snapshots 100
```

## Milestone 8: Outcome Labeler v0

v3 now labels future outcomes for feature snapshots using local normalized events and `price_quote` as the v0 price proxy. Outcome labels are separate from features so feature generation remains leakage-free.

Run the focused Milestone 8 tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_outcome_label_store.py
./trading_env/bin/python -m pytest research/tests/test_price_series_builder.py
./trading_env/bin/python -m pytest research/tests/test_outcome_label_builder.py
./trading_env/bin/python -m pytest research/tests/test_run_build_outcome_labels.py
```

Example run:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_build_outcome_labels --max-snapshots 100
```

## Milestone 9: Research Dataset Builder v0

v3 now joins feature snapshots with outcome labels into clean research dataset rows for baseline analysis, rule-based backtests, walk-forward validation, and thesis testing.

Run the focused Milestone 9 tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_research_dataset_store.py
./trading_env/bin/python -m pytest research/tests/test_research_dataset_builder.py
./trading_env/bin/python -m pytest research/tests/test_research_dataset_report.py
./trading_env/bin/python -m pytest research/tests/test_run_build_research_dataset.py
./trading_env/bin/python -m pytest research/tests/test_run_research_dataset_report.py
```

Example build:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_build_research_dataset --min-label-quality sparse --require-forward-return
```

Example report:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_research_dataset_report --min-label-quality sparse --require-forward-return
```

## Stage 23: Fast Offline Rebuild Review

After bounded evidence expansion, refresh derived layers before interpreting fold sufficiency or deciding to spend more Helius credits:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_build_outcome_labels --real-only --max-snapshots 1000 --dry-run-summary --timing
./trading_env/bin/python -m research.mtp_research.pipeline.run_fast_offline_rebuild_review --real-only --max-snapshots 1000 --progress-every 100 --timing
```

This is offline only. It rebuilds outcome labels and research datasets from local evidence, writes timing profiles under `data/backtests/diagnostics/reports/`, and then runs price, dataset, and fold sufficiency diagnostics.

## Stage 24: Diagnostic Walk-Forward Review

Run the full offline diagnostic cycle:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_stage24_diagnostic_cycle
```

Focused tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_diagnostic_walk_forward_review.py
./trading_env/bin/python -m pytest research/tests/test_diagnostic_walk_forward_report.py
./trading_env/bin/python -m pytest research/tests/test_run_diagnostic_walk_forward_review.py
./trading_env/bin/python -m pytest research/tests/test_run_stage24_diagnostic_cycle.py
```

Stage 24 uses the diagnostic nearest-entry dataset and writes reports under `data/backtests/diagnostics/reports/`. Findings are research-only and cannot promote theses or enable live trading.

## Stage 25: Rule Failure Review

Run the offline decision cycle:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_stage25_decision_cycle
```

Inspect the current best-ranked diagnostic rule manually:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_inspect_rule_selected_rows --rule-id buy_imbalance_basic --real-only --limit 20
```

Focused tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_rule_failure_analyzer.py
./trading_env/bin/python -m pytest research/tests/test_rule_failure_report.py
./trading_env/bin/python -m pytest research/tests/test_run_rule_failure_review.py
./trading_env/bin/python -m pytest research/tests/test_run_stage25_decision_cycle.py
./trading_env/bin/python -m pytest research/tests/test_run_inspect_rule_selected_rows.py
```

Stage 25 explains why diagnostic rules failed before any rule definition changes. It does not optimize thresholds, promote theses, or enable live trading.

## Sample Adequacy Gate

Check whether diagnostic evidence is large enough to support thesis status changes:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_sample_adequacy_report --real-only
```

Focused tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_sample_adequacy_report.py
./trading_env/bin/python -m pytest research/tests/test_run_sample_adequacy_report.py
./trading_env/bin/python -m pytest research/tests/test_thesis_evaluator.py
```

If the sample is too small, thesis recommendations stay `needs_more_data`. Weak diagnostic reads are stored as metadata, not used to reject, promote, or mark a thesis as a paper candidate.

## Bounded Evidence Expansion Plan

Plan the next evidence expansion without Helius:

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_sample_adequacy_expansion_plan
```

Focused tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_sample_adequacy_expansion_plan.py
./trading_env/bin/python -m pytest research/tests/test_sample_adequacy_expansion_report.py
./trading_env/bin/python -m pytest research/tests/test_run_sample_adequacy_expansion_plan.py
```

The plan is review-only. It does not execute backfills, call Helius, trade, or mutate thesis status.

## Milestone 10: Baseline Edge Report v0

v3 now has an exploratory baseline report layer that buckets clean research dataset rows by feature and summarizes forward outcomes. This is descriptive analysis only, not a trading strategy, signal feed, or live execution path.

Run the focused Milestone 10 tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_baseline_edge_analyzer.py
./trading_env/bin/python -m pytest research/tests/test_baseline_report_writer.py
./trading_env/bin/python -m pytest research/tests/test_run_baseline_edge_report.py
```

Example report:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_baseline_edge_report --min-label-quality sparse --feature age_sec --feature event_count
```

Example smoke report:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_baseline_edge_smoke_report
```

## Milestone 11: Rule-Based Backtester v0

v3 now has a deterministic rule-based backtester that evaluates simple feature hypotheses from local `ResearchDatasetStore` rows. It applies explicit fee/slippage assumptions and reports gross outcomes separately from net outcomes. Results remain exploratory until walk-forward validation exists.

Run the focused Milestone 11 tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_rule_backtester.py
./trading_env/bin/python -m pytest research/tests/test_rule_library.py
./trading_env/bin/python -m pytest research/tests/test_rule_backtest_store.py
./trading_env/bin/python -m pytest research/tests/test_rule_backtest_report.py
./trading_env/bin/python -m pytest research/tests/test_run_rule_backtest.py
```

Example default rule backtest:

```bash
./trading_env/bin/python -m research.mtp_research.backtest.run_rule_backtest --all-default-rules --min-label-quality sparse --horizon-name 5m
```

Example smoke run:

```bash
./trading_env/bin/python -m research.mtp_research.backtest.run_rule_backtest_smoke
```

## Milestone 12: Walk-Forward Validator v0

v3 now has chronological walk-forward validation for fixed rule definitions. Training folds are descriptive only; test fold results are reported separately and rules are not optimized or altered in v0.

Run the focused Milestone 12 tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_walk_forward_splitter.py
./trading_env/bin/python -m pytest research/tests/test_walk_forward_validator.py
./trading_env/bin/python -m pytest research/tests/test_walk_forward_store.py
./trading_env/bin/python -m pytest research/tests/test_walk_forward_report.py
./trading_env/bin/python -m pytest research/tests/test_run_walk_forward_validation.py
```

Example validation:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_walk_forward_validation --all-default-rules --min-label-quality sparse --train-window-seconds 86400 --test-window-seconds 21600 --step-seconds 21600
```

Example smoke run:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_walk_forward_smoke
```

## Milestone 13: Thesis Registry and Evaluation Layer

v3 now has a first-class thesis registry under `theses/`. Thesis evaluation maps walk-forward rule summaries back to named research theses and emits conservative workflow recommendations. These recommendations are not trading instructions and do not mutate thesis Markdown status automatically.

Run the focused Milestone 13 tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_thesis_registry.py
./trading_env/bin/python -m pytest research/tests/test_thesis_decision_store.py
./trading_env/bin/python -m pytest research/tests/test_thesis_evaluator.py
./trading_env/bin/python -m pytest research/tests/test_thesis_report.py
./trading_env/bin/python -m pytest research/tests/test_run_thesis_evaluation.py
./trading_env/bin/python -m pytest research/tests/test_run_thesis_registry_check.py
```

Example registry check:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_thesis_registry_check
```

Example thesis evaluation:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_thesis_evaluation
```

## Milestone 14: Evidence Population Pipeline v0

v3 now has a controlled pipeline for seeding candidates, planning bounded backfill targets, optionally executing small Helius backfills, and rebuilding local research artifacts offline. Backfill is dry-run by default; real Helius calls require `--execute`.

Write example seed file:

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_seed_candidates --write-example
```

Seed registry:

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_seed_candidates --seed-path data/seeds/candidate_seeds.jsonl
```

Plan targets:

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_plan_backfill_targets --candidate-limit 5
```

Dry-run backfill:

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_evidence_backfill --candidate-limit 1 --max-signatures-per-target 10 --max-transactions-per-target 10
```

Real bounded backfill:

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_evidence_backfill --candidate-limit 1 --max-signatures-per-target 10 --max-transactions-per-target 10 --execute
```

Offline rebuild:

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_offline_research_rebuild --max-snapshots 100
```

Full research cycle:

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_full_research_cycle --skip-backfill --max-snapshots 100
```

Run the focused Milestone 14 tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_candidate_seed_loader.py
./trading_env/bin/python -m pytest research/tests/test_backfill_target_planner.py
./trading_env/bin/python -m pytest research/tests/test_evidence_pipeline.py
./trading_env/bin/python -m pytest research/tests/test_run_seed_candidates.py
./trading_env/bin/python -m pytest research/tests/test_run_plan_backfill_targets.py
./trading_env/bin/python -m pytest research/tests/test_run_evidence_backfill.py
./trading_env/bin/python -m pytest research/tests/test_run_offline_research_rebuild.py
```

## Milestone 15: Evidence Run Audit and Target Quality Diagnostics v0

v3 now has an offline diagnostic layer for explaining where evidence is being lost after a bounded run. It audits local JSONL stores, checks backfill target quality, flags mint-only target plans, infers the first major bottleneck, and writes Markdown/JSON reports. This is diagnostic only and is not a trading signal.

Run the focused Milestone 15 tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_evidence_auditor.py
./trading_env/bin/python -m pytest research/tests/test_evidence_audit_report.py
./trading_env/bin/python -m pytest research/tests/test_run_evidence_audit.py
./trading_env/bin/python -m pytest research/tests/test_run_post_evidence_diagnostics.py
./trading_env/bin/python -m pytest research/tests/test_run_inspect_backfill_targets.py
```

Inspect targets:

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_inspect_backfill_targets
```

Run audit:

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_evidence_audit
```

Run diagnostics:

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_post_evidence_diagnostics
```

## Milestone 16: Real Candidate Discovery Ingestion v0

v3 now has bounded public DexScreener discovery for real Solana candidates. Discovery is dry-run by default; registry writes require `--write`. Target planning and evidence backfill exclude mock candidates by default.

Run the focused Milestone 16 tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_http_client.py
./trading_env/bin/python -m pytest research/tests/test_dexscreener_real_ingest.py
./trading_env/bin/python -m pytest research/tests/test_jupiter_token_enrichment.py
./trading_env/bin/python -m pytest research/tests/test_run_dexscreener_discovery.py
./trading_env/bin/python -m pytest research/tests/test_run_candidate_quality_filter.py
./trading_env/bin/python -m pytest research/tests/test_real_discovery_backfill_filters.py
```

Dry-run real discovery:

```bash
./trading_env/bin/python -m research.mtp_research.ingestion.run_dexscreener_discovery --limit 10 --min-liquidity-usd 10000
```

Write real candidates:

```bash
./trading_env/bin/python -m research.mtp_research.ingestion.run_dexscreener_discovery --limit 10 --min-liquidity-usd 10000 --write
```

Candidate quality:

```bash
./trading_env/bin/python -m research.mtp_research.ingestion.run_candidate_quality_filter --exclude-mock --require-pool-address --min-liquidity-usd 10000
```

Plan real targets:

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_plan_backfill_targets --candidate-limit 3 --require-pool-address --min-liquidity-usd 10000
```

## Milestone 17: Price Coverage and Dataset Sufficiency Diagnostics v0

v3 now has offline diagnostics for price proxy coverage, real-only candidate hygiene, optional nearest-entry research fallback, and dataset sufficiency before scaling Helius backfills.

Run the focused Milestone 17 tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_real_candidate_filter.py
./trading_env/bin/python -m pytest research/tests/test_price_coverage_analyzer.py
./trading_env/bin/python -m pytest research/tests/test_run_price_coverage_report.py
./trading_env/bin/python -m pytest research/tests/test_price_series_nearest_fallback.py
./trading_env/bin/python -m pytest research/tests/test_outcome_label_nearest_fallback.py
./trading_env/bin/python -m pytest research/tests/test_dataset_sufficiency_report.py
./trading_env/bin/python -m pytest research/tests/test_run_dataset_sufficiency_report.py
```

Price coverage:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_price_coverage_report --real-only
```

Dataset sufficiency:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_dataset_sufficiency_report --real-only
```

Research fallback outcome labels:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_build_outcome_labels --allow-nearest-entry-fallback --nearest-entry-max-staleness-sec 300 --max-snapshots 500
```

## Milestone 18: Price Inference and Entry Coverage Improvement v0

v3 now compares clean outcome labels against diagnostic nearest-entry fallback labels and reports real-only evidence quality. Fallback rows remain research-only and are written to diagnostic paths.

Run the focused Milestone 18 tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_entry_price_coverage_report.py
./trading_env/bin/python -m pytest research/tests/test_run_entry_price_coverage_comparison.py
./trading_env/bin/python -m pytest research/tests/test_real_only_evidence_quality_report.py
./trading_env/bin/python -m pytest research/tests/test_trade_event_price_inference.py
```

Diagnostic fallback labels:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_build_outcome_labels --allow-nearest-entry-fallback --nearest-entry-max-staleness-sec 300 --max-snapshots 500 --outcomes-path data/backtests/diagnostics/outcome_labels_nearest300.jsonl
```

Diagnostic fallback dataset:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_build_research_dataset --outcomes-path data/backtests/diagnostics/outcome_labels_nearest300.jsonl --dataset-path data/backtests/diagnostics/research_dataset_nearest300.jsonl --min-label-quality sparse --require-forward-return
```

Entry price comparison:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_entry_price_coverage_comparison
```

Real-only evidence quality:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_real_only_evidence_quality_report
```

## Milestone 19: Diagnostic Validation Review v0

v3 can now run baseline, rule, walk-forward, and thesis evaluation against the diagnostic nearest-entry fallback dataset without overwriting canonical clean validation stores. Every fallback report is marked research-only.

Run the focused Milestone 19 tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_diagnostic_validation_review.py
./trading_env/bin/python -m pytest research/tests/test_diagnostic_validation_report.py
./trading_env/bin/python -m pytest research/tests/test_run_diagnostic_validation_review.py
```

Run the diagnostic review:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_diagnostic_validation_review
```

Smoke run:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_diagnostic_validation_smoke
```

## Milestone 20: Walk-Forward Fold Sufficiency Diagnostics v0

v3 can now diagnose why walk-forward validation has zero valid folds by sweeping chronological fold settings for evidence sufficiency only. This does not tune rules for returns and does not promote theses.

Run the focused Milestone 20 tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_fold_sufficiency_analyzer.py
./trading_env/bin/python -m pytest research/tests/test_fold_sufficiency_report.py
./trading_env/bin/python -m pytest research/tests/test_run_fold_sufficiency_report.py
./trading_env/bin/python -m pytest research/tests/test_run_best_diagnostic_walk_forward.py
```

Run fold sufficiency:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_fold_sufficiency_report --real-only
```

Run best diagnostic walk-forward:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_best_diagnostic_walk_forward --real-only
```

## Milestone 21: Time-Span Expansion Backfill Plan v0

v3 can now plan bounded Helius backfills around chronological evidence coverage. Dry-run remains the default; real calls require `--execute`.

Run the focused Milestone 21 tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_time_span_backfill_planner.py
./trading_env/bin/python -m pytest research/tests/test_time_span_backfill_report.py
./trading_env/bin/python -m pytest research/tests/test_run_time_span_backfill_plan.py
./trading_env/bin/python -m pytest research/tests/test_run_time_span_backfill_execute.py
./trading_env/bin/python -m pytest research/tests/test_run_post_backfill_rebuild_and_review.py
```

Plan:

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_time_span_backfill_plan --candidate-limit 10
```

Dry-run execute:

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_time_span_backfill_execute --candidate-limit 5 --max-signatures-per-target 75 --max-transactions-per-target 75 --stop-after-targets 10
```

Execute:

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_time_span_backfill_execute --candidate-limit 5 --max-signatures-per-target 75 --max-transactions-per-target 75 --stop-after-targets 10 --execute
```

Post-run review:

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_post_backfill_rebuild_and_review --max-snapshots 1000 --real-only
```

## Milestone 27: Full-Span Snapshot Selection

v3 can now rebuild validation artifacts with explicit snapshot selection strategies so broad raw evidence is not reduced to an early-only slice by a simple snapshot cap. Use artifact span reports to confirm derived labels and datasets cover the intended raw evidence span.

Run artifact span review:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_artifact_span_report --real-only
```

Run the full-span offline rebuild:

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_fast_offline_rebuild_review \
  --real-only \
  --snapshot-selection-strategy per_token_even \
  --max-snapshots-per-token 1000 \
  --min-time-gap-seconds 60 \
  --timing
```

Run the focused tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_snapshot_selector.py research/tests/test_artifact_span_report.py research/tests/test_run_artifact_span_report.py
```

## Milestone 28: Token-Active Feature Windows

v3 can rebuild feature snapshots on each token's own observed activity window. This prevents broad global time grids from creating artificial validation rows before or after a token has local evidence.

Run the token-active feature rebuild:

```bash
./trading_env/bin/python -m research.mtp_research.features.run_build_feature_snapshots \
  --per-token-active-window \
  --overwrite
```

Then run the offline validation rebuild:

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_fast_offline_rebuild_review \
  --real-only \
  --snapshot-selection-strategy per_token_even \
  --max-snapshots-per-token 1000 \
  --min-time-gap-seconds 60 \
  --timing
```

Focused tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_feature_snapshot_builder.py research/tests/test_feature_snapshot_store.py research/tests/test_run_build_feature_snapshots.py
```

## Milestone 30: Selected Row + Price Outlier Audit

Stage 30 audits the exact rows selected by diagnostic rules and separately reviews extreme return/runup rows. This is an offline research trust check only; it does not call Helius, change rule thresholds, promote theses, or create trading instructions.

Run selected-row audit:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_selected_row_audit --real-only
```

Run price outlier audit:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_price_outlier_audit --real-only
```

Run full Stage 30 cycle:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_stage30_price_rule_audit_cycle --real-only
```

Focused tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_selected_row_auditor.py research/tests/test_selected_row_audit_report.py research/tests/test_run_selected_row_audit.py research/tests/test_price_outlier_auditor.py research/tests/test_run_price_outlier_audit.py research/tests/test_run_stage30_price_rule_audit_cycle.py
```

## Milestone 31: Outlier Price-Path Review

Stage 31 reconstructs local price paths around extreme selected rows and adds robust return summaries so diagnostic averages are not interpreted without outlier context. This remains offline-only and does not call Helius, tune rules, promote theses, or create trading instructions.

Run outlier price-path review:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_outlier_price_path_review --real-only
```

Run robust rule return report:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_rule_robust_return_report --real-only
```

Run full Stage 31 cycle:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_stage31_outlier_review_cycle --real-only
```

Focused tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_outlier_price_path_reviewer.py research/tests/test_outlier_price_path_report.py research/tests/test_run_outlier_price_path_review.py research/tests/test_robust_return_metrics.py research/tests/test_run_rule_robust_return_report.py research/tests/test_run_stage31_outlier_review_cycle.py
```

## Milestone 32: Outlier-Adjusted Diagnostics

Stage 32 separates raw averages from capped, robust, and outlier-excluded rule metrics. It is report-only: no Helius calls, no rule tuning, no thesis promotion, and no dataset mutation.

Run outlier-adjusted rule report:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_outlier_adjusted_rule_report --real-only
```

Run full Stage 32 cycle:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_stage32_outlier_adjusted_cycle --real-only
```

Focused tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_outlier_adjusted_rule_metrics.py research/tests/test_run_outlier_adjusted_rule_report.py research/tests/test_run_stage32_outlier_adjusted_cycle.py
```

## Milestone 33: Evidence Expansion Decision

Stage 33 uses robust and outlier-separated diagnostics to decide the next bounded evidence expansion plan. It is report-only: it may suggest a bounded Helius command, but it does not execute it.

Run decision report:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_evidence_expansion_decision --real-only
```

Run full Stage 33 cycle:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_stage33_expansion_decision_cycle --real-only
```

Focused tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_evidence_expansion_decision.py research/tests/test_evidence_expansion_decision_report.py research/tests/test_run_evidence_expansion_decision.py research/tests/test_run_stage33_expansion_decision_cycle.py
```
