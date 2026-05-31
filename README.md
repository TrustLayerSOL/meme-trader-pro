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
