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
- [ ] 5. DEX event parser foundation

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
