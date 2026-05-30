# v3 Roadmap

## Milestones

- [x] 1. Repo migration and v3 scaffold
  - v3 package structure and legacy preservation are in place.
- [ ] 2. Candidate registry

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
