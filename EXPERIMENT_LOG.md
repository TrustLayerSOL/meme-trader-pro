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

