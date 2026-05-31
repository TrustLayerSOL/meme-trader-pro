# Data Sources

## Intended providers

- Helius for filtered historical backfills, live transaction monitoring, priority fee estimation, and sending.
- DexScreener for token/pair metadata, boosts, profiles, and attention proxies.
- Jupiter recent/token APIs for recent pool/token discovery and organic quality signals.
- Raydium APIs/SDK for LaunchLab and Raydium pool lifecycle data.
- Pump/PumpSwap SDKs later for venue-specific execution.

Helius Enhanced Transactions and Wallet APIs should not be used as the backbone because they can be expensive.

## Helius historical usage

Use standard Helius JSON-RPC historical methods first.

The first v3 adapter method is `getSignaturesForAddress`, used for cheap pagination and discovery around candidate token, pool, creator, and early-wallet addresses.

Later milestones can add `getTransaction` or batch transaction-body retrieval for full normalized event creation after signature discovery has narrowed the search space.

Do not use Helius Enhanced Transactions or Wallet API as the default historical backbone.

Keep Helius calls filtered by candidate token, pool, creator, or wallet addresses. Broad chain scans are outside the v3 research-first scope.

## Local replay cache

The raw transaction store is the local replay cache for Helius/Solana transaction bodies. Historical backtests should read from local raw and normalized JSONL data instead of repeatedly calling Helius.

Use `getSignaturesForAddress` for discovery and pagination. Use `getTransaction` for full transaction bodies after signatures are scoped to candidate token, pool, creator, or wallet addresses.

Later optimization may add batching or `getTransactionsForAddress` where it is cost-effective and still compatible with the research-first pipeline.

## Local parser

Raw transaction JSON is parsed locally from stored `getTransaction` `jsonParsed` results. Parser logic should prefer deterministic fields from those raw transaction bodies and avoid live RPC dependencies.

DEX-specific parsing should be added incrementally after generic account, program, and token balance-delta extraction is stable.

Venue classification should remain conservative and confidence-scored. Unknown venues with token balance deltas should be treated as observed swap candidates, not confirmed trades.

Backtests should depend on normalized event stores instead of direct RPC calls.

## Balance-delta trade inference

Balance-delta trade inference uses local raw transaction JSON from the replay cache. v0 treats WSOL, USDC, and USDT as known quote assets.

DEX-specific parsing is a later milestone. Heuristic trade events should be treated as candidates, not perfect fills.

## Feature snapshots

Feature snapshots are derived local artifacts that should be reproducible from NormalizedEventStore.

Helius should not be called during feature building. Snapshot outputs live under `data/features/`.

v0 rolling windows are 1m, 5m, and 15m.

## Outcome labels

Outcome labels are derived local artifacts stored under `data/backtests/`.

Outcome labeling uses NormalizedEventStore `price_quote` as the v0 price proxy. No RPC calls should happen during outcome labeling.

`price_quote` is heuristic in v0 and may later be replaced by venue-specific execution or quote data.

## Research dataset rows

ResearchDatasetStore is a derived local artifact stored under `data/backtests/`.

It joins local feature snapshots and local outcome labels. No RPC calls should happen during dataset building.

Dataset rows are reproducible from FeatureSnapshotStore and OutcomeLabelStore.

## Baseline edge reports

Baseline edge reports are derived local artifacts built from ResearchDatasetStore rows.

They do not call RPC providers or external APIs. They should be reproducible from `data/backtests/research_dataset.jsonl`.

Report outputs live under `data/backtests/reports/`.

## Rule backtests

Rule backtests consume ResearchDatasetStore only.

No RPC calls should occur during rule backtesting.

Rule backtest results are derived artifacts stored under `data/backtests/`.

Reports are written under `data/backtests/reports/`.

## Walk-forward validation

Walk-forward validation consumes ResearchDatasetStore only.

No RPC calls should happen during walk-forward validation.

Walk-forward results are derived artifacts stored under `data/backtests/`.

Reports are written under `data/backtests/reports/`.

## Thesis registry and decisions

Thesis files live under top-level `theses/`.

Thesis decisions are derived artifacts stored under `data/backtests/thesis_decisions.jsonl`.

Thesis evaluation consumes local walk-forward validation results only.

No RPC calls occur during thesis evaluation.

## Evidence population

Stage 14 is the first evidence-bearing data population layer.

Candidate seeds are local/manual until real discovery ingestors are implemented.

Helius is only used for bounded targeted backfills.

All downstream parsing, features, outcomes, and datasets are local derived artifacts.

No live trading or wallet signing occurs.

## Real Candidate Discovery

DexScreener real discovery is the first real public candidate source for v3.

DexScreener token profiles and token boosts are discovery sources. The DexScreener token-pairs endpoint enriches token mints into pool/pair addresses so Helius backfills can target higher-value addresses than mint-only records.

Jupiter token enrichment is optional and used only for quality metadata such as verification, holder count, liquidity, market cap, organic score, and trading stats when the endpoint contract is confirmed.

Mock ingestors are test-only. Real discovery commands do not call the mock DexScreener, Jupiter, or Raydium placeholder ingestors.

Helius should only be used after real candidate quality is confirmed with non-mock candidates, pool addresses, and bounded liquidity filters.
