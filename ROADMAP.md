# MemeTraderPro Roadmap

Last updated: 2026-05-15

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

The first baseline comparison report exists and generates `data/wallet_baseline_comparison.json` from the older wallet quant report plus the newer outcome ledger. It highlights agreement, conflict, unconfirmed quant signals, quant-only wallets, and ledger-only wallets.

The wallet outcome ledger now also backfills wallet-performance signal observations. These rows increase wallet observation coverage without pretending to know later outcomes.

Signal observations can now be linked to later token snapshots inside a bounded evaluation window. The linked outcome stays separated under `later_token_outcome`; decision fields remain signal-time only.

Snapshot-linked promotion/demotion candidates now flow into `data/wallet_candidate_audit.json`, a review-only audit report that explicitly blocks wallet-list apply.

Wallet candidate audit rows now export into Obsidian as generated review notes under `MemeTraderPro/WalletCandidateReviews/`. These notes expose the candidate evidence gates and recommendation reasons for human review while preserving MemeTraderPro data files as the source of truth.

The first historical replay dataset contract now exists. `research/historical_replay_dataset.py` converts unified records into review-only replay events with separated decision context, execution assumptions, and later outcome labels. `utils/build_historical_replay_dataset.py` generated the first local dataset with `6,041` replay events and `0` unsafe/leakage-flagged events.

## Next Milestone

Use the historical replay dataset to compare wallet behavior across accepted trades, failed trades, rejected signals, and wallet observations without hindsight leakage.

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
