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
