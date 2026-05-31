# Evidence Pipeline Runbook

## Purpose

Stage 14 adds the first controlled path for populating evidence-bearing local research datasets. The pipeline keeps Helius usage bounded and separates credit-spending backfill steps from offline rebuild steps.

The intended flow is:

```text
CandidateRegistry
  -> BackfillTarget planning
  -> RawTransactionStore
  -> parser / trade normalizer
  -> FeatureSnapshotStore
  -> OutcomeLabelStore
  -> ResearchDatasetStore
  -> baseline report
  -> rule backtest
  -> walk-forward validation
  -> thesis evaluation
```

## Write Example Candidate Seed File

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_seed_candidates --write-example
```

This writes `data/seeds/candidate_seeds.jsonl` with fake example rows only.

## Seed Candidates

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_seed_candidates --seed-path data/seeds/candidate_seeds.jsonl
```

Seed files are local JSONL. No network calls are made.

## Plan Backfill Targets

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_plan_backfill_targets --candidate-limit 5
```

Target plans are written to `data/backtests/backfill_targets_plan.jsonl`.

## Dry-Run Backfill

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_evidence_backfill --candidate-limit 1 --max-signatures-per-target 10 --max-transactions-per-target 10
```

Dry-run is the default. It plans targets and prints requested work without calling Helius.

## Bounded Real Helius Backfill

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_evidence_backfill --candidate-limit 1 --max-signatures-per-target 10 --max-transactions-per-target 10 --execute
```

Real backfill requires `--execute` and `HELIUS_API_KEY`. It uses bounded targeted JSON-RPC calls only.

## Offline Research Rebuild

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_offline_research_rebuild --max-snapshots 100
```

This rebuilds local derived artifacts from existing stores without spending Helius credits.

## Full Research Cycle

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_full_research_cycle --skip-backfill --max-snapshots 100
```

If backfill is skipped or not executed, results depend only on already-local data.

## Safety Notes

- Dry-run is the default.
- `--execute` is required for Helius calls.
- No live trading is added.
- No private keys are used.
- Monitor Helius credits when executing real backfills.
- Start with tiny candidate limits.
- Backfill and rebuild steps are separated so derived artifacts can be regenerated without spending credits.

## Recommended First Real Run

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_evidence_backfill --candidate-limit 1 --max-signatures-per-target 10 --max-transactions-per-target 10 --role mint --role pool --role creator --execute
```

Early results may still be sparse. Thesis evaluation should remain `needs_more_data` until walk-forward folds have enough clean test rows and selected trades.

## Post-Run Diagnostics

Run these immediately after a tiny real evidence run:

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_inspect_backfill_targets
./trading_env/bin/python -m research.mtp_research.pipeline.run_evidence_audit
./trading_env/bin/python -m research.mtp_research.pipeline.run_post_evidence_diagnostics
```

The audit identifies the first major local bottleneck across candidate rows, target plans, raw transactions, normalized events, feature snapshots, outcome labels, research rows, walk-forward results, and thesis decisions.

Do not scale up backfills until the bottleneck is understood. If targets are mint-only, seed real candidates with `pool_address` and `creator_wallet` before spending more credits. If parser coverage is the bottleneck, inspect raw transaction shape before spending more credits. If insufficient test evidence is the bottleneck, gradually increase bounded runs only after target quality is confirmed.

If the audit shows `mock_candidates_present` or `no_raw_transactions` from mock/manual targets, run `docs/REAL_DISCOVERY_RUNBOOK.md` before more Helius backfills.

Do not scale backfills against mock or `manual_example` candidates.

## Price Coverage and Dataset Sufficiency

After every evidence run, inspect price coverage before scaling backfill:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_price_coverage_report --real-only
./trading_env/bin/python -m research.mtp_research.validation.run_dataset_sufficiency_report --real-only
```

Do not scale Helius if `no_price` dominates due to parser or price inference issues. Diagnose whether missing prices come from missing entry prices, missing future prices, sparse price points, or event types that do not produce usable `price_quote`.

## Entry Price Coverage Diagnostics

Use diagnostic nearest-entry fallback only on separate output paths:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_price_coverage_report --real-only
./trading_env/bin/python -m research.mtp_research.validation.run_build_outcome_labels --allow-nearest-entry-fallback --nearest-entry-max-staleness-sec 300 --max-snapshots 500 --outcomes-path data/backtests/diagnostics/outcome_labels_nearest300.jsonl
./trading_env/bin/python -m research.mtp_research.validation.run_build_research_dataset --outcomes-path data/backtests/diagnostics/outcome_labels_nearest300.jsonl --dataset-path data/backtests/diagnostics/research_dataset_nearest300.jsonl --min-label-quality sparse --require-forward-return
./trading_env/bin/python -m research.mtp_research.validation.run_entry_price_coverage_comparison
./trading_env/bin/python -m research.mtp_research.validation.run_real_only_evidence_quality_report
```

Fallback rows are research diagnostics only. Do not use them for thesis promotion without explicit review.

## Diagnostic Validation Review

Use this after diagnostic nearest-entry fallback labels and the diagnostic dataset are built.

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_diagnostic_validation_review
./trading_env/bin/python -m research.mtp_research.validation.run_diagnostic_validation_smoke
```

The review runs baseline, rule backtest, walk-forward validation, and thesis evaluation on `data/backtests/diagnostics/research_dataset_nearest300.jsonl`, writes outputs under `data/backtests/diagnostics/`, and compares those results against canonical clean stores.

Use the recommended next action to decide whether to scale bounded backfill, improve clean price inference, or inspect rule selection and fold thresholds. Do not use diagnostic fallback results for live trading or thesis promotion without human review.
