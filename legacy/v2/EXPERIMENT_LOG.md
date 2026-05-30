# Experiment Log

Last updated: 2026-05-15

Use this log for every signal, filter, wallet score, replay assumption, or promotion/demotion change.

## Required Entry Format

```text
Date:
Hypothesis:
Files changed:
Data used:
Sample size:
Baseline result:
New result:
Conclusion:
Next action:
```

## Entries

### 2026-05-15 - Missing Market-Context Targets

Date: 2026-05-15

Hypothesis: Wallet evidence with missing entry market context should be converted into a precise token/time-window target queue before any new market-data backfill is attempted.

Files changed:

- `wallets/wallet_missing_market_context.py`
- `utils/build_wallet_missing_market_context_targets.py`
- `desktop_api.py`
- `obsidian_export/exporter.py`
- `obsidian_export/intelligence_notes.py`
- `tests/test_wallet_missing_market_context.py`
- `tests/test_desktop_api.py`
- `tests/test_obsidian_export.py`
- `EXPERIMENT_LOG.md`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`

Data used: Current local wallet evidence enrichment report.

Sample size: `194` deduped missing-context evidence rows across `36` target token mints and `33` affected wallets after excluding quote mints.

Baseline result: The enrichment report showed missing market context counts, but it did not provide an actionable token/time-window queue for the next data backfill.

New result: `data/wallet_backfills/wallet_missing_market_context_report.json` now identifies target mints, evidence row counts, affected wallets, observed action counts, known-outcome rows, and backfill windows.

Conclusion: The next market-data backfill can now be targeted instead of broad. This still does not prove wallet quality; it only defines the missing data collection queue.

Next action: Build a read-only market-context backfill runner for the top target mints, then rerun wallet evidence enrichment.

### 2026-05-15 - Wallet Evidence Enrichment

Date: 2026-05-15

Hypothesis: Wallet-history evidence becomes reviewable only when each transaction row can be tied to decision-time-safe market context and later outcome labels without allowing future data into the entry fields.

Files changed:

- `wallets/wallet_evidence_enrichment.py`
- `utils/enrich_wallet_history_evidence.py`
- `desktop_api.py`
- `obsidian_export/exporter.py`
- `obsidian_export/intelligence_notes.py`
- `tests/test_wallet_evidence_enrichment.py`
- `tests/test_desktop_api.py`
- `tests/test_obsidian_export.py`
- `EXPERIMENT_LOG.md`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`

Data used: Current local wallet-history evidence rows plus SQLite `token_snapshots`, SQLite `swap_ticks`, and local historical replay events.

Sample size: `520` wallet evidence rows across `44` wallets and `49` token mints.

Baseline result: Wallet-history evidence existed, but most rows had no entry price, market cap, liquidity, or later outcome labels, which made promotion/demotion review weak.

New result: Enrichment added decision-time entry context to `151` rows, known later outcomes to `30` rows, fixed-window labels to `29` rows, and fully enriched `16` rows. `369` rows still lack market context.

Conclusion: The enrichment path works and is leakage-safe, but the current evidence set is still data-thin. Wallet scores should not be trusted until missing market context is reduced.

Next action: Backfill token snapshots/swap ticks around evidence mints with missing context, then rerun enrichment and candidate review.

### 2026-05-15 - Historical Replay Dataset Contract

Date: 2026-05-15

Hypothesis: Historical testing can help refine wallet behavior only if accepted and rejected signals are converted into a single decision-time-safe replay dataset with later outcomes separated from signal context.

Files changed:

- `research/historical_replay_dataset.py`
- `utils/build_historical_replay_dataset.py`
- `tests/test_historical_replay_dataset.py`
- `.gitignore`
- `ROADMAP.md`
- `EXPERIMENT_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`

Data used: Current local unified records from paper trades, rejected signals, and wallet-performance signal observations via `utils.build_wallet_outcome_ledger.build_records()`.

Sample size: First local generated dataset contains `6,041` replay events: `36` accepted trades, `5` failed trades, and `6,000` rejected signals.

Baseline result: The wallet outcome ledger could aggregate wallet outcomes, but there was no separate replay event dataset contract with explicit leakage checks and separated execution assumptions.

New result: `data/historical_replay/replay_events.jsonl` and `data/historical_replay/summary.json` are generated locally with `0` unsafe/leakage-flagged events. Generated replay data is ignored by git and remains review-only.

Conclusion: The project now has the first clean bridge between forward paper data and historical replay analysis. This is not proof of edge yet; it is the dataset contract needed to test edge honestly.

Next action: Add fixed evaluation windows and richer slippage/latency/failed-fill assumptions before using historical replay results for wallet promotion or filter changes.

### 2026-05-15 - Replay Realism Assumptions

Date: 2026-05-15

Hypothesis: Replay records are more useful when every event declares the same evaluation windows and explicit execution realism assumptions before any historical result is interpreted as edge.

Files changed:

- `research/historical_replay_dataset.py`
- `tests/test_historical_replay_dataset.py`
- `ROADMAP.md`
- `EXPERIMENT_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`

Data used: Current local historical replay dataset generated from unified records.

Sample size: `6,041` replay events.

Baseline result: Replay events separated decision context from later outcome, but did not declare common evaluation windows or classify whether the event was fillable under basic liquidity assumptions.

New result: Replay events now declare `30s`, `2m`, `5m`, and `15m` evaluation windows and include latency, slippage, entry liquidity, liquidity floor, fill status, failed-fill assumptions, and max position liquidity percent. The local summary currently reports `207` fillable-with-assumptions, `153` failed-liquidity-floor, and `5,681` unknown-liquidity events.

Conclusion: Replay structure is better, but decision-time liquidity coverage is still too incomplete for strong strategy conclusions.

Next action: Improve decision-time market context coverage, then compute windowed later outcomes for each fixed replay window.

### 2026-05-15 - Decision-Time Market Context Enrichment

Date: 2026-05-15

Hypothesis: Wallet signal replay quality improves when missing decision-time market context is filled from snapshots at or before the signal timestamp, without using future data.

Files changed:

- `utils/build_wallet_outcome_ledger.py`
- `tests/test_wallet_signal_backfill.py`
- `ROADMAP.md`
- `EXPERIMENT_LOG.md`
- `research/BUILD_PLAN.md`
- `WORK_LOG.md`

Data used: Current local wallet-performance signals and SQLite `token_snapshots`.

Sample size: `6,041` replay events; `6,041` wallet outcome ledger records across `366` wallets.

Baseline result: Historical replay summary had `207` fillable-with-assumptions events, `153` liquidity-floor failures, and `5,681` unknown-liquidity events.

New result: Prior-snapshot enrichment reduced unknown-liquidity events to `4,697`, increased fillable-with-assumptions events to `691`, and increased liquidity-floor failures to `653`.

Conclusion: Decision-time context coverage improved materially, and the remaining unknown-liquidity bucket is now a clear data-capture target.

Next action: Add windowed outcome labels for `30s`, `2m`, `5m`, and `15m` so each replay event can show whether the wallet signal survived across fixed horizons.

### 2026-05-15 - Fixed-Window Replay Outcome Labels

Date: 2026-05-15

Hypothesis: Wallet signal replay becomes more useful when later outcomes are labeled at fixed horizons instead of only as one broad post-signal outcome.

Files changed:

- `research/outcome_linker.py`
- `research/historical_replay_dataset.py`
- `utils/build_wallet_outcome_ledger.py`
- `tests/test_outcome_linker.py`
- `tests/test_historical_replay_dataset.py`
- `tests/test_wallet_signal_backfill.py`
- `ROADMAP.md`
- `EXPERIMENT_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`

Data used: Current local wallet-performance signals and SQLite `token_snapshots`.

Sample size: `6,041` replay events.

Baseline result: Replay events declared fixed windows, but later outcome labels were not summarized by window.

New result: Replay events now carry per-window labels under `later_token_outcome.windows`, and replay summaries expose `window_outcome_counts`. Current `15m` window counts are `76` runner, `14` rug, `149` dead, `275` loser, and `5,527` unknown.

Conclusion: The system can now compare wallet signal outcomes by horizon. Unknown coverage remains high, so future scoring must separate coverage from performance.

Next action: Build a wallet replay scorecard that ranks wallets using known/fillable window outcomes while making coverage and unknown-rate explicit.

### 2026-05-15 - Wallet Replay Scorecard

Date: 2026-05-15

Hypothesis: Wallet replay results are more trustworthy when coverage, fillability, fixed-window performance, market regime, and repeated co-entry behavior are reviewed together instead of scoring wallets only by raw outcomes.

Files changed:

- `wallets/wallet_replay_scorecard.py`
- `utils/build_wallet_replay_scorecard.py`
- `tests/test_wallet_replay_scorecard.py`
- `EXPERIMENT_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`

Data used: Current local `data/historical_replay/replay_events.jsonl`.

Sample size: `6,041` replay events across `366` wallets.

Baseline result: Replay data had per-event fixed-window outcomes, but there was no wallet-level scorecard that separated coverage from outcome quality or exposed repeated co-entry partners.

New result: `data/wallet_replay_scorecard.json` now reports wallet-level coverage/performance by fixed window, fillability counts, market-regime exposure, co-entry partners, and top repeated co-entry pairs. Current generated report includes `50` top co-entry pairs.

Conclusion: The system can now inspect wallet ecosystems instead of isolated wallets. This is still review-only and should not automatically promote or demote wallets.

Next action: Build a candidate review layer from the scorecard that only considers wallets and co-entry pairs with sufficient known/fillable replay coverage.

### 2026-05-14 - Wallet Candidate Audit Report

Date: 2026-05-14

Hypothesis: Snapshot-linked promotion/demotion candidates should be audited in a separate review-only artifact before any wallet-list action can consume them.

Files changed:

- `wallets/wallet_candidate_audit.py`
- `utils/build_wallet_candidate_audit.py`
- `tests/test_wallet_candidate_audit.py`
- `ROADMAP.md`
- `EXPERIMENT_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`
- `handoff.md`

Data used: Current local `data/wallet_outcome_ledger.json` and `data/wallet_baseline_comparison.json`.

Sample size: Current audit report has `14` candidates: `1` promotion-review and `13` demotion-review.

Baseline result: Promotion/demotion candidates were visible in the outcome ledger, but there was no separate audit packet that blocked wallet-list apply.

New result: `data/wallet_candidate_audit.json` now summarizes each candidate's sample gate, known outcomes, source coverage, runner/rug/dead counts, average PnL, confidence, recommendation reasons, and baseline comparison status.

Conclusion: Review candidates are now easier to inspect and remain explicitly disconnected from wallet-list apply. All current candidates are marked `HUMAN_REVIEW_REQUIRED`; none are auto-applied.

Next action: Add a human-readable export/review workflow for these candidates before any wallet-list action consumes them.

### 2026-05-14 - Snapshot-Linked Signal Outcomes

Date: 2026-05-14

Hypothesis: Wallet signal observations become more useful when they are linked to later token snapshots as separated evaluation labels, while preserving the original decision-time context.

Files changed:

- `research/outcome_linker.py`
- `utils/build_wallet_outcome_ledger.py`
- `tests/test_outcome_linker.py`
- `tests/test_wallet_signal_backfill.py`
- `ROADMAP.md`
- `EXPERIMENT_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`
- `handoff.md`

Data used: Current local `data/wallet_performance.json` signal rows and SQLite `token_snapshots`.

Sample size: Local builder generated `5,766` unified records across `251` wallets. Snapshot linking produced `1,617` known outcomes: `269` runner labels, `54` rug labels, and `441` dead labels.

Baseline result: Wallet-performance signal rows increased observation coverage, but later outcomes stayed unknown.

New result: `research.outcome_linker` links signal mints to later token snapshots inside a bounded evaluation window and stores the result only in `later_token_outcome`.

Conclusion: The system now has a measurable bridge from wallet signal observation to later token behavior. Recommendations remain review-only. The current generated ledger shows `13` demotion-review wallets and `1` promotion-review wallet, all requiring human/audit review before any wallet-list action.

Next action: Build an audit report for snapshot-linked promotion/demotion candidates before allowing wallet-list apply logic to consume them.

### 2026-05-14 - Wallet Performance Signal Backfill

Date: 2026-05-14

Hypothesis: The unified outcome ledger should include wallet signal observations even when later token outcomes are unknown, so coverage gaps are visible instead of hidden.

Files changed:

- `research/signal_schema.py`
- `utils/build_wallet_outcome_ledger.py`
- `tests/test_research_signal_schema.py`
- `tests/test_wallet_signal_backfill.py`
- `ROADMAP.md`
- `EXPERIMENT_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`
- `handoff.md`

Data used: Current local `data/wallet_performance.json` signal rows, plus existing paper trades and rejected-signal rows.

Sample size: Local builder generated `5,762` unified records across `251` wallets after adding wallet-performance signal observations.

Baseline result: The wallet outcome ledger had `4,747` records across `28` wallets. The baseline comparison had only `28` overlapping wallets and `7,827` quant-only wallets.

New result: The wallet outcome ledger has `5,762` records across `251` wallets. The baseline comparison now has `231` overlapping wallets, `7,624` quant-only wallets, and `20` ledger-only wallets.

Conclusion: Observation coverage improved substantially, but known-outcome coverage did not. Added wallet-performance signal rows are intentionally labeled with unknown later outcomes until a real outcome source is attached.

Next action: Link signal observations to later token outcomes by mint/time where the data exists, while preserving the decision-time boundary.

### 2026-05-14 - Wallet Quant Baseline Comparison

Date: 2026-05-14

Hypothesis: Older wallet quant recommendations should be checked against the unified outcome ledger before they are trusted for promotion or demotion decisions.

Files changed:

- `wallets/wallet_baseline_comparison.py`
- `utils/build_wallet_baseline_comparison.py`
- `tests/test_wallet_baseline_comparison.py`
- `ROADMAP.md`
- `EXPERIMENT_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`
- `handoff.md`

Data used: Current local `data/wallet_quant_report.json` and `data/wallet_outcome_ledger.json`.

Sample size: `7,855` wallet quant rows, `28` wallet outcome ledger rows, `28` overlapping wallets.

Baseline result: The older wallet quant report could recommend review actions without showing whether the newer unified outcome ledger agreed, disagreed, or lacked evidence.

New result: `data/wallet_baseline_comparison.json` now classifies each wallet as agreement, conflict, unconfirmed quant signal, quant-only, ledger-only, ledger-stronger signal, or hold-more-data.

Conclusion: Current coverage is thin. The generated comparison found `7,827` quant-only wallets, `28` overlapping wallets, `27` hold-more-data overlaps, and `1` unconfirmed quant demotion signal. That means the next work should expand unified outcome coverage, not promote/demote from the old quant report alone.

Next action: Backfill or wire more accepted/rejected wallet signals into the unified outcome ledger so the comparison can cover the broader wallet universe.

### 2026-05-14 - Outcome Labels And Review-Only Wallet Recommendations

Date: 2026-05-14

Hypothesis: Wallet promotion/demotion evidence is more trustworthy when later token outcomes are labeled consistently and recommendation policy is isolated from raw ledger aggregation.

Files changed:

- `research/outcome_labeler.py`
- `research/signal_schema.py`
- `wallets/wallet_promotion_engine.py`
- `wallets/wallet_outcome_ledger.py`
- `tests/test_outcome_labeler.py`
- `tests/test_wallet_promotion_engine.py`
- `tests/test_wallet_outcome_ledger.py`
- `ROADMAP.md`
- `EXPERIMENT_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`
- `handoff.md`

Data used: Synthetic unit-test records plus current local paper trades and rejected-signal rows normalized through `research.signal_schema`.

Sample size: Local builder generated `4,747` unified records across `28` wallets at the time of this run. This is still a research ledger, not proof of edge.

Baseline result: Later token outcomes were copied mostly as raw status/PnL fields. Promotion/demotion recommendation logic lived inside the ledger module and used looser score thresholds.

New result: Later outcomes are labeled as `runner`, `rug`, `dead`, `loser`, `open`, or `unknown` with classification reasons. Wallet recommendation policy now lives in `wallets.wallet_promotion_engine`, remains review-only, and requires at least `20` known outcomes before promotion review.

Conclusion: Wallet evidence is now easier to audit and less likely to promote a wallet from one-off or thin evidence. Current generated recommendations are `28` hold-more-data, `0` promotion-review, and `0` demotion-review.

Next action: Build a baseline comparison report between `data/wallet_quant_report.json` and `data/wallet_outcome_ledger.json` to identify agreement, conflict, and missing evidence by wallet.

### 2026-05-14 - Research Governance And Unified Signal Outcome Schema

Date: 2026-05-14

Hypothesis: Accepted trades and rejected signals must share one comparable schema before wallet scores can be trusted.

Files changed:

- `ROADMAP.md`
- `RESEARCH_RULES.md`
- `SIGNAL_REGISTRY.md`
- `EXPERIMENT_LOG.md`
- `research/signal_schema.py`
- `tests/test_research_signal_schema.py`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`
- `handoff.md`

Data used: Synthetic unit-test records covering accepted paper trades, rejected scanner signals, and later token outcomes.

Sample size: 3 unit-test scenarios. This is a schema-validation test only, not strategy evidence.

Baseline result: Accepted trades and rejected signals had related context, but no single comparable outcome record shape.

New result: `research.signal_schema` can produce a unified record shape for accepted trades and rejected signals:

```text
wallet(s) -> signal context -> trade/skip decision -> later token outcome
```

Conclusion: The project now has a governance gate and the first comparable schema layer. This does not prove wallet edge.

Next action: Build a persistent wallet-outcome ledger from unified signal outcome records and backfill accepted/rejected examples without using future information in decision fields.

### 2026-05-14 - Wallet Outcome Ledger V1

Date: 2026-05-14

Hypothesis: Wallet quality should be measured from unified accepted/rejected outcome records instead of one-off PnL or raw signal counts.

Files changed:

- `wallets/wallet_outcome_ledger.py`
- `utils/build_wallet_outcome_ledger.py`
- `tests/test_wallet_outcome_ledger.py`
- `ROADMAP.md`
- `EXPERIMENT_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`
- `handoff.md`

Data used: Current local paper trades plus recent rejected-signal JSONL rows, normalized through `research.signal_schema`.

Sample size: Local builder generated `4,084` unified records across `28` wallets. This is a research-ledger sample, not proof of edge.

Baseline result: Wallet reports existed, but accepted trades and rejected signals were not aggregated into one comparable per-wallet ledger.

New result: `data/wallet_outcome_ledger.json` now aggregates total signals, accepted signals, rejected signals, known outcomes, runner/rug/dead participation, average PnL after signal, liquidity, token age, cluster duration, market-regime breakdown, promotion score, demotion score, confidence, and review-only recommendation.

Conclusion: The project now has the first measurable wallet-outcome ledger. The data is useful for review, but confidence remains limited by known-outcome coverage and sample quality.

Next action: Harden outcome labeling and make promotion/demotion engine consume this ledger as review-only evidence.
