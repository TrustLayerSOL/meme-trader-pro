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
