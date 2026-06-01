# Launch Discovery Source Registry

This registry tracks candidate sources for broad historical launch discovery. It is research-only and does not authorize paper trading, live trading, thesis promotion, or strategy validation claims.

## Current CandidateRegistry Sources

- Can discover failures: limited
- Can discover pre-DexScreener launches: only when another source already inserted them
- Historical availability: local JSONL only
- Expected bias: biased toward whatever upstream source seeded the registry
- Required fields: token mint, first seen timestamp, optional pool address, source, venue
- Approximate credit cost: zero for local reads
- Current status: active local source
- Recommended use: input to lifecycle labeling, not a complete launch universe

## DexScreener Current / Recent

- Can discover failures: weak; many failed launches never become visible
- Can discover pre-DexScreener launches: no
- Historical availability: limited through current/recent visible tokens unless an external archive is used
- Expected bias: survivorship, liquidity, and visibility bias
- Required fields: token mint, pair address, first seen timestamp if available, liquidity metadata
- Approximate credit cost: low network cost, no Helius credits
- Current status: useful but insufficient alone
- Recommended use: enrichment and visible-token registry updates only

## Jupiter Recent Tokens

- Can discover failures: weak
- Can discover pre-DexScreener launches: sometimes earlier than DexScreener if routed/listed quickly
- Historical availability: current/recent only unless externally archived
- Expected bias: routeable token bias
- Required fields: token mint, first seen timestamp, quote/tradeability metadata
- Approximate credit cost: low network cost, no Helius credits
- Current status: placeholder/local pattern only
- Recommended use: secondary enrichment, not primary historical cohort discovery

## Pump.fun Program Signatures

- Can discover failures: yes, if creation/bonding-curve instructions are decoded
- Can discover pre-DexScreener launches: yes
- Historical availability: available through Solana archival signature scans if RPC/indexer supports it
- Expected bias: closest source for full Pump.fun launch population, but requires decoder quality checks
- Required fields: token mint, creator, bonding curve account, block time, signature, instruction type
- Approximate credit cost: one signature request per program page plus transaction hydration for candidate signatures
- Current status: planned tiny probe
- Recommended use: primary next historical discovery source

## PumpSwap Program Signatures

- Can discover failures: partial; likely misses tokens that fail before pool creation
- Can discover pre-DexScreener launches: yes for pools before DexScreener visibility
- Historical availability: available through archival signature scans if RPC/indexer supports it
- Expected bias: pool-creation and migration bias
- Required fields: token mint, pool address, quote mint, block time, signature, instruction type
- Approximate credit cost: one signature request per program page plus selective hydration
- Current status: planned tiny probe
- Recommended use: pool-level launch timestamp verification and lifecycle enrichment

## Raydium LaunchLab / Pool Creation

- Can discover failures: partial for Raydium-origin launches; weak for tokens that never reach Raydium liquidity
- Can discover pre-DexScreener launches: yes for pool or LaunchLab activity before visibility
- Historical availability: available through archival signature scans if RPC/indexer supports it
- Expected bias: Raydium and liquidity-formation bias
- Required fields: token mint, pool address, launch/pool instruction type, block time, signature
- Approximate credit cost: one signature request per program page plus selective hydration
- Current status: planned tiny probe
- Recommended use: Raydium-specific cohort source and timestamp verification

## Helius Webhooks / LaserStream

- Can discover failures: yes for future launches after subscription starts
- Can discover pre-DexScreener launches: yes
- Historical availability: forward-only unless paired with historical RPC/indexer backfill
- Expected bias: low if filters are correct; coverage starts only after activation
- Required fields: program ID, instruction filters, token mint extraction, block time, signature
- Approximate credit cost: depends on stream volume and provider plan
- Current status: future live self-archive option, not part of this historical task
- Recommended use: future forward archive after historical dataset design is stable

## Third-Party Indexers

- Can discover failures: depends on schema and retention
- Can discover pre-DexScreener launches: yes if instruction/account creation tables are available
- Historical availability: often better than RPC pagination for large cohorts
- Expected bias: vendor/schema-specific
- Required fields: program calls, account creation, token mint, block time, signature, instruction details
- Approximate credit cost: query-dependent
- Current status: optional fallback if Helius RPC pagination remains too slow
- Recommended use: evaluate if program-signature RPC probes are too expensive or incomplete

## Current Recommendation

Use tiny bounded program-signature probes first, starting with Pump.fun creation/bonding-curve signatures. If the probe can identify token mints and launch timestamps cheaply, scale bounded program-signature discovery before spending credits on deeper lifecycle hydration.

## Pump.fun Create Scanner Guardrail

The bounded Pump.fun create scanner is the next candidate path for broad failed/pre-DexScreener launch discovery. It pages signatures in small batches, hydrates bounded samples, and stops when create-shaped instructions are found or scan limits are reached.

Before any broad historical import, the scanner must demonstrate extraction of:

- token mint
- bonding curve account
- associated bonding curve account when available
- creator wallet
- verified block time

Reports from this scanner remain discovery diagnostics. They are not launch datasets, backtests, strategy validation, or thesis evidence until a bounded importer writes reviewed candidate rows.
