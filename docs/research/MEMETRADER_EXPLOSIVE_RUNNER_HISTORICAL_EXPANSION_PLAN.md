# MemeTraderPro Explosive Runner Historical Expansion Plan

## Decision

Existing local data does not meet the preferred date-balance target. The next data acquisition should use parallel date-sharded pulls, not the previous slow serial approach.

## Target Gap

- Additional $20k-trigger rows needed: `578`
- Additional $20k-trigger dates needed: `27`

## Faster Parallel Pull Design

- sharding: `one bounded worker group per target date or small date range`
- worker_model: `parallel date shards with per-shard signature and transaction hydration workers`
- checkpointing: `checkpoint raw signatures, hydrated transactions, parsed lifecycle rows, and date-level completion separately`
- dedupe: `global signature and mint dedupe before snapshot construction`
- caps: `cap launches/date and requests/date; stop if date balance target cannot improve`
- preservation: `preserve raw Helius transactions under ORICO by date shard before parsing`
- avoid_cluster_repeat: `select dates to cap top-date share and avoid adding more 2026-06-01 dominated rows`

## First Pilot

- dates: `5-10 new target dates outside 2026-05-25, 2026-05-26, 2026-06-01`
- goal: `prove trigger reconstruction and rows/date before scaling`
- success: `>=10 $20k-trigger rows/date with >=90% forward path coverage`

## Guardrails

- Preserve raw transactions before parsing.
- Cap requests per date shard.
- Stop if date balance cannot improve.
- Do not run thesis, validation, trading logic, optimization, grid search, or ML during acquisition.
