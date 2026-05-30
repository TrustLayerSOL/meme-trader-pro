# v3 Roadmap

## Milestones

- [x] 1. Repo migration and v3 scaffold
  - v3 package structure and legacy preservation are in place.
- [x] 2. Candidate registry
  - Verified with `./trading_env/bin/python -m pytest research/tests/test_candidate_registry.py`.
- [x] 3. Helius historical adapter foundation
  - Verified with `./trading_env/bin/python -m pytest research/tests/test_helius_backfill.py`.
- [x] 4. Raw transaction store and backfill job ledger
  - Verified with Milestone 4 store, job, and normalizer tests.
- [x] 5. DEX event parser foundation
  - Verified with parser, venue classifier, and parse CLI tests.
- [x] 6. Trade event normalization v0
  - Verified with trade normalizer and trade normalization CLI tests.
- [x] 7. Feature snapshot builder v0
  - Verified with feature snapshot store, builder, and CLI tests.
- [ ] 8. Outcome labeler v0

## Milestone 2 acceptance criteria

- LaunchCandidate model exists in `research/mtp_research/ingestion/models.py`
- CandidateRegistry writes JSONL to `data/normalized/candidate_registry.jsonl`
- Upsert by `token_mint` works (`inserted`/`updated`)
- Earliest `first_seen_ts` is preserved during merges
- Metadata merges correctly with newer keys taking precedence
- Placeholder DexScreener/Jupiter/Raydium ingestors exist and return deterministic mock candidates
- CLI runner works and reports inserted/updated/total/output path
- Tests for registry behavior pass
- Root `research` package imports resolve from repository root
- `./trading_env/bin/python -m research.mtp_research.ingestion.run_candidate_registry` runs successfully
- `./trading_env/bin/python -m pytest research/tests/test_candidate_registry.py` passes

## Milestone 3 acceptance criteria

- HeliusBackfillRequest model exists
- HeliusHistoricalAdapter builds `getSignaturesForAddress` payloads
- Signature rows parse into normalized records
- Failed transaction filtering works
- Pagination `next_before` works
- CLI probe exists
- Tests pass without network

## Milestone 4 acceptance criteria

- BackfillTarget model exists
- RawTransactionStore writes JSONL
- Raw transactions upsert by signature
- Helius adapter can build `getTransaction` payloads
- CLI backfill target runner exists
- NormalizedEvent model/store exists
- Basic `transaction_observed` normalizer exists
- Tests pass without network

## Milestone 5 acceptance criteria

- TransactionSummary model exists
- TokenBalanceDelta model exists
- Solana raw transaction parser exists
- Token balance deltas are extracted from pre/post token balances
- Venue classifier exists
- Basic normalizer includes venue and parser metadata
- Raw transaction parse CLI exists
- Tests pass without network

## Milestone 6 acceptance criteria

- TradeFlow model exists
- TradeEventNormalizer exists
- `possible_buy` / `possible_sell` events can be inferred from token balance deltas
- Accumulation/distribution events can be inferred conservatively
- `target_token_mint` filtering works
- Normalized events include confidence and reasons
- Trade normalization CLI exists
- Tests pass without network

## Milestone 7 acceptance criteria

- FeatureSnapshot model exists
- FeatureSnapshotStore writes JSONL
- FeatureSnapshotBuilder creates rolling 1m/5m/15m snapshots
- Buy/sell/accumulation/distribution counts are calculated
- Confidence-weighted flow features are calculated
- Unique actor counts are calculated
- Venue and event type counts are calculated
- CLI feature snapshot builder exists
- Tests pass without network

## Milestone 8 acceptance criteria

- OutcomeLabel model exists
- OutcomeLabelStore writes JSONL
- TokenPriceSeriesBuilder creates price points from normalized events
- Entry price selection works with staleness control
- Forward points are strict future-only
- `forward_return` / `max_runup` / `max_drawdown` are calculated
- `survived_horizon` and `rug_like_drop` are labeled
- Future event counts and volumes are calculated
- CLI outcome label builder exists
- Tests pass without network
