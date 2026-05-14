# MemeTraderPro Roadmap

Last updated: 2026-05-14

## Current Product Direction

MemeTraderPro is now a behavioral wallet-intelligence research system.

The product is not a broad meme-coin prediction cockpit. The current edge hypothesis is:

> Historically profitable wallet behavior may contain repeatable informational structure.

All near-term work should improve the system's ability to measure wallet behavior honestly.

## Active Phase: Quant Wallet Tracker V2

The active phase is research hardening.

Priority order:

1. Unified signal outcome schema.
2. Wallet-outcome ledger.
3. Wallet promotion/demotion engine.
4. Replay realism improvements.
5. Signal quality measurement.
6. Historical replay expansion.
7. Controlled signal experimentation.

## What Is Frozen

Do not add new work in these areas unless it directly improves wallet evaluation:

- dashboard expansion,
- live execution,
- social scraping,
- broad narrative prediction,
- giant AI systems,
- unrelated chart polish,
- random technical indicators,
- high-frequency execution work.

## Current Milestone

Create comparable records for:

- accepted paper trades,
- failed paper trades,
- rejected signals,
- skipped signals,
- future replay evaluations.

Every record should follow:

```text
wallet(s) -> signal context -> trade/skip decision -> later token outcome
```

## Current Milestone Status

The first wallet-outcome ledger builder exists and generates `data/wallet_outcome_ledger.json` from unified accepted-trade and rejected-signal records.

This is still review-only. It does not promote wallets into trading logic.

Later token outcomes now receive review labels such as `runner`, `rug`, `dead`, `loser`, `open`, or `unknown`. Wallet promotion/demotion recommendations now come from a separate review-only engine with a minimum known-outcome sample threshold.

## Next Milestone

Compare the wallet-outcome ledger against the previous wallet quant report baseline and begin a controlled baseline report.

That ledger should measure:

- total signals,
- runner participation,
- rug participation,
- average outcome after signal,
- entry timing quality,
- liquidity quality,
- cluster behavior,
- market-regime performance,
- promotion/demotion confidence.

## Release Gates

Live execution remains frozen until:

- accepted and rejected signals share one schema,
- paper outcomes are linked to wallet context,
- replay assumptions include slippage, latency, liquidity, and failed fills,
- wallet scores show reliability across enough samples,
- every model/filter change is compared against a previous baseline.
