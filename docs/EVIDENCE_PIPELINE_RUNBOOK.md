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
