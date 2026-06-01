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

## Launch-Regime Discovery Source Audit

DexScreener-visible candidates can create survivorship bias. Many Pump.fun launches may fail before DexScreener visibility, boosts, routing, or pool enrichment. Launch-regime studies therefore need a broader launch discovery source before any thesis validation claim is made.

Audit current source concentration:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_discovery_source_bias_audit
```

Review the reports:

```text
data/backtests/diagnostics/reports/discovery_source_bias_audit.md
data/backtests/diagnostics/reports/discovery_source_bias_audit.json
```

Plan program-signature discovery without network calls:

```bash
./trading_env/bin/python -m research.mtp_research.ingestion.run_program_signature_discovery_plan
```

Tiny probe dry-run:

```bash
./trading_env/bin/python -m research.mtp_research.ingestion.run_program_signature_probe --program-id <PROGRAM_ID> --limit 10
```

Execute only a tiny explicit probe after reviewing the plan:

```bash
./trading_env/bin/python -m research.mtp_research.ingestion.run_program_signature_probe --program-id <PROGRAM_ID> --limit 10 --execute
```

Do not hydrate full transactions unless the tiny signature sample looks useful and `--hydrate-sample` is explicitly justified. Future forward self-archive may use Helius webhooks or LaserStream, but this lane is historical research and remains dry-run by default.

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

## Fold Sufficiency Diagnostics

Run this after diagnostic validation review shows zero valid walk-forward folds:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_fold_sufficiency_report --real-only
./trading_env/bin/python -m research.mtp_research.validation.run_best_diagnostic_walk_forward --real-only
```

If no configs produce valid folds, scale bounded backfill. If short configs work, use them only as diagnostic validation until more data exists. Fold window sweeps are evidence sufficiency checks, not strategy optimization.

## Time-Span Expansion Backfill

Stage 20 showed the real-only diagnostic dataset had only `1,140` seconds of usable time span. Walk-forward validation needs enough chronological span for the selected fold configuration, so the next bounded backfills should target more tokens, more pools, and longer per-token time span rather than only adding more rows from the same narrow window.

Start with the plan command before executing:

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_time_span_backfill_plan \
  --candidate-limit 10 \
  --target-time-span-seconds 3600 \
  --recommended-signature-limit 75 \
  --recommended-transaction-limit 75
```

Dry-run the execution wrapper:

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_time_span_backfill_execute \
  --candidate-limit 5 \
  --max-signatures-per-target 75 \
  --max-transactions-per-target 75 \
  --stop-after-targets 10
```

Execute only after reviewing the plan:

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_time_span_backfill_execute \
  --candidate-limit 5 \
  --max-signatures-per-target 75 \
  --max-transactions-per-target 75 \
  --stop-after-targets 10 \
  --transaction-workers 16 \
  --execute
```

Use bounded transaction workers for historical `getTransaction` hydration. This uses concurrent single RPC calls, not large JSON-RPC archival batches. Keep `target_timings` from the command output so slow runs can be separated into signature lookup, transaction hydration, and local store write time.

After a bounded run, rebuild and review offline:

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_post_backfill_rebuild_and_review \
  --max-snapshots 1000 \
  --real-only
```

## Fast Offline Rebuild and Review

Stage 23 adds an observable offline-only refresh path for larger bounded evidence runs. Use it before spending more Helius credits whenever raw/events/features have grown but outcome labels, diagnostic datasets, or fold sufficiency still look stale.

Dry-run the label refresh summary without writing:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_build_outcome_labels \
  --real-only \
  --max-snapshots 1000 \
  --dry-run-summary \
  --timing
```

Run a bounded diagnostic output test:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_build_outcome_labels \
  --real-only \
  --allow-nearest-entry-fallback \
  --nearest-entry-max-staleness-sec 300 \
  --max-snapshots 1000 \
  --stop-after-snapshots 100 \
  --outcomes-path data/backtests/diagnostics/outcome_labels_nearest300_stage23_test.jsonl \
  --progress-every 25 \
  --timing
```

Run the full fast offline rebuild and review:

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_fast_offline_rebuild_review \
  --real-only \
  --max-snapshots 1000 \
  --progress-every 100 \
  --timing
```

The fast runner stays offline, overwrites derived outcome/dataset stores from local evidence, writes profile reports under `data/backtests/diagnostics/reports/`, and then runs price coverage, dataset sufficiency, and fold sufficiency diagnostics.

Use `--stop-after-snapshots` for bounded refresh tests and skip flags such as `--skip-clean-outcomes` or `--skip-diagnostic-dataset` when isolating a slow step.

## Stage 24 Diagnostic Walk-Forward Review

Run this after fold sufficiency finds valid diagnostic folds:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_best_diagnostic_walk_forward --real-only
./trading_env/bin/python -m research.mtp_research.validation.run_diagnostic_walk_forward_review --real-only
./trading_env/bin/python -m research.mtp_research.validation.run_stage24_diagnostic_cycle
```

This stage is offline and diagnostic-only. It reviews the best diagnostic walk-forward store at `data/backtests/diagnostics/walk_forward_best_diagnostic.jsonl`, reports whether default rules have valid test folds, and flags whether selected rows depend heavily on nearest-entry fallback labels.

Use the recommended next action to choose between more bounded evidence expansion, clean price inference work, or manual rule inspection. Do not treat Stage 24 findings as canonical validation, live trading approval, or thesis promotion.

## Stage 25 Rule Failure Review

Run this after diagnostic walk-forward produces valid folds but weak positive fold rates:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_rule_failure_review --real-only
./trading_env/bin/python -m research.mtp_research.validation.run_stage25_decision_cycle
./trading_env/bin/python -m research.mtp_research.validation.run_inspect_rule_selected_rows --rule-id buy_imbalance_basic --real-only
```

Use Stage 25 to decide whether weak diagnostic folds are caused by low token diversity, short time span, small selected samples, fallback dependency, cost drag, or overly broad/default exploratory rules.

If token diversity or time span is low, scale bounded evidence. If fallback dependency is high, improve clean price inference. If a specific rule looks promising, inspect selected rows manually before changing rule definitions. Do not run a parameter grid or optimize thresholds from the diagnostic fallback dataset.

## Sample Adequacy Gate

Run the sample adequacy report before interpreting diagnostic thesis decisions:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_sample_adequacy_report --real-only
```

Default adequacy thresholds are:

- `min_real_token_count=10`
- `min_time_span_seconds=43200`
- `min_valid_test_folds=10`
- `min_total_test_selected_count=100`
- `min_independent_batches=1`

When these thresholds are not met, thesis evaluation must return `needs_more_data` and preserve the weak or negative diagnostic read in metadata. Do not reject, promote, or move a thesis to watchlist from a tiny diagnostic sample.

The expected current data expansion recommendation is to add more real candidates and expand per-pool time span with bounded backfills. Do not run Helius until the bounded expansion plan is reviewed.

## Sample Adequacy Expansion Plan

Build the dry-run expansion plan before any Helius execution:

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_sample_adequacy_expansion_plan
```

This combines sample adequacy thresholds with the bounded time-span backfill planner. It reports token and time-span shortfalls, target pools, estimated request counts, and the exact bounded command to review. The command does not call Helius and does not trade.

If the plan still shows fewer than 10 real tokens, prioritize candidate discovery or adding more real candidate pools before spending credits on already-covered pools.

## Full-Span Offline Rebuild

After broad raw evidence expansion, a simple `--max-snapshots` cap can select an early-only slice of feature snapshots. That makes derived labels, datasets, and fold sufficiency look narrower than the raw evidence actually is.

Check artifact coverage before interpreting fold sufficiency:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_artifact_span_report --real-only
```

Run the representative full-span offline rebuild:

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_fast_offline_rebuild_review \
  --real-only \
  --snapshot-selection-strategy per_token_even \
  --max-snapshots-per-token 1000 \
  --min-time-gap-seconds 60 \
  --timing
```

Use `per_token_even` when raw evidence covers many tokens or a wide time range. It keeps the validation slice distributed by token and timestamp instead of silently truncating to the earliest snapshots. This remains offline-only and does not call Helius.

## Token-Active Feature Rebuild

If feature snapshots span the global evidence clock for every token, validation can create artificial `no_price` labels before or after an individual token's observed activity window. Rebuild features with token-active windows before interpreting clean price coverage:

```bash
./trading_env/bin/python -m research.mtp_research.features.run_build_feature_snapshots \
  --per-token-active-window \
  --overwrite
```

Then rerun the full-span offline rebuild:

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_fast_offline_rebuild_review \
  --real-only \
  --snapshot-selection-strategy per_token_even \
  --max-snapshots-per-token 1000 \
  --min-time-gap-seconds 60 \
  --timing
```

This is still a local rebuild only. It does not call Helius and does not change rules or thesis statuses.

## Stage 30: Selected Row + Price Outlier Audit

Run selected-row diagnostics before changing rule definitions or scaling around a rule with outlier-driven averages:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_selected_row_audit --real-only
```

Run price outlier diagnostics:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_price_outlier_audit --real-only
```

Run the full offline Stage 30 cycle:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_stage30_price_rule_audit_cycle --real-only
```

Stage 30 is diagnostic-only. It does not call Helius, does not change thesis status, does not tune thresholds, and does not create trading instructions. Use it to decide whether the next bottleneck is clean price inference, manual outlier inspection, candidate diversity, bounded evidence expansion, or conservative rule review.

## Stage 31: Outlier Price-Path Review

Review the local price paths behind extreme selected rows:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_outlier_price_path_review --real-only
```

Compare average returns with robust return metrics:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_rule_robust_return_report --real-only
```

Run the full offline Stage 31 cycle:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_stage31_outlier_review_cycle --real-only
```

Stage 31 is offline-only. It does not call Helius, does not mutate canonical stores, and does not mark theses validated. Use it to decide whether to improve clean price inference, tighten price-quality filters, separate outlier metrics, expand bounded evidence, or require manual review.

## Stage 32: Outlier-Adjusted Diagnostic Metrics

Build outlier-adjusted rule metrics from the latest outlier price-path report:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_outlier_adjusted_rule_report --real-only
```

Run the full offline Stage 32 cycle:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_stage32_outlier_adjusted_cycle --real-only
```

Stage 32 keeps raw averages, capped averages, robust metrics, and outlier-excluded metrics separate. It does not delete rows, alter labels, tune rules, promote theses, or call Helius. Use it to decide whether the next action is clean price-quality tightening, explicit outlier separation, manual review, or bounded evidence expansion.

## Stage 33: Evidence Expansion Decision

Build the expansion decision report after outlier-adjusted diagnostics:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_evidence_expansion_decision --real-only
```

Run the full offline Stage 33 cycle:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_stage33_expansion_decision_cycle --real-only
```

The output suggests the next bounded Helius command but does not execute it. Review the plan before running any Helius. If the recommendation is `improve_price_coverage_before_scaling`, avoid spending more Helius until price quality improves. If the recommendation is `run_bounded_evidence_expansion`, run only the bounded command after review.

## Stage 35: Price Quality Gate + Outlier-Adjusted Validation

Run the strict diagnostic price-quality gate before interpreting outlier-sensitive rules:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_price_quality_gate --real-only
```

Run the full offline gated validation cycle:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_price_quality_validation_cycle
```

Compare gated and ungated diagnostic artifacts:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_price_quality_validation_comparison
```

When the gate removes a large share of rows, rank the failure causes before spending more Helius:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_price_quality_failure_analysis --real-only
```

Use the fast offline rebuild before interpreting price-quality changes. Its diagnostic path accepts a wider prior-entry window so prior prices allowed by the strict gate are not mislabeled as nearest fallback rows:

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_fast_offline_rebuild_review --real-only --snapshot-selection-strategy per_token_even --max-snapshots-per-token 1000 --min-time-gap-seconds 60 --diagnostic-entry-max-staleness-sec 120 --timing
```

Native SOL balance-delta price proxies are local heuristic anchors for swaps where the quote leg appears as lamport movement instead of a WSOL/USDC/USDT token balance delta. Treat any coverage improvement from this parser path as diagnostic until outlier reports confirm the price path is usable.

Stage 35 writes gated diagnostic artifacts under `data/backtests/diagnostics/`. It does not call Helius, does not mutate canonical stores, does not optimize thresholds, and does not promote theses. Use it to decide whether the next bottleneck is clean price inference, candidate diversity, explicit outlier separation, or conservative rule rework.

## Stage 38: Native SOL Proxy Hardening

Run the native SOL proxy quality gate before interpreting proxy-backed rows:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_native_sol_proxy_quality_gate --real-only
```

Run the proxy-separated rule report:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_proxy_separated_rule_report --real-only
```

Run the full offline hardening cycle:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_stage38_proxy_hardening_cycle
```

Native SOL proxy hardening is diagnostic-only. It does not call Helius, tune rules, promote theses, enable paper trading, or enable live trading. Use the outputs to compare all rows, proxy-only rows, non-proxy rows, and proxy-quality-gated rows before deciding whether the next bottleneck is proxy price inference or bounded evidence expansion.
