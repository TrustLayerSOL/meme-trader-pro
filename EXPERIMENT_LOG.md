# Experiment Log

Last updated: 2026-05-14

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
