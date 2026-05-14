# Research Rules

Last updated: 2026-05-14

These rules govern Quant Wallet Tracker V2.

## Core Rule

Every development step must answer:

> Does this improve our ability to measure wallet behavior honestly?

If the answer is no, defer it.

## Required Rules

1. No feature gets promoted to trading logic without evidence.
2. Every signal must have a clear hypothesis.
3. Every signal must be measurable at decision time.
4. No future information may be used in replay decisions.
5. Every accepted trade and rejected signal must share the same context schema.
6. Every model/filter change must be compared against the previous baseline.
7. Live execution stays frozen until wallet intelligence proves reliable.
8. Historical replay must include slippage, latency, liquidity, and failed-fill assumptions.
9. Avoid overfitting small sample sizes.
10. Prefer boring, repeatable wallet behavior over exciting one-off runners.

## Evidence Standard

A signal can move from experimental to validated only when it has:

- a written hypothesis,
- a decision-time-safe data source,
- enough sample size to review,
- baseline comparison,
- clear accepted/rejected outcome records,
- repeatability across more than one token or market regime.

## Replay Safety

Replay can use later data only as an outcome label.

Replay cannot use later data to reconstruct the entry decision. Future candles, future liquidity, future wallet activity, and later social activity must not influence the simulated decision state.

## Promotion Rules

Wallet scores, filters, and signal weights must stay review-only until the system can show:

- what changed,
- which baseline it was compared against,
- sample size,
- market-regime breakdown,
- impact on accepted trades,
- impact on rejected signals,
- whether the improvement survives realistic slippage/latency/liquidity assumptions.

## Live Execution Boundary

Live execution remains frozen. No governance document, signal registry entry, or experiment result authorizes live trading by itself.

