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
- [x] 8. Outcome labeler v0
  - Verified with outcome store, price series, label builder, and CLI tests.
- [x] 9. Research dataset builder v0
  - Verified with research dataset store, builder, report, and CLI tests.
- [x] 10. Baseline edge report v0
  - Verified with baseline analyzer, writer, CLI, and full v3 research pipeline regression tests.
- [x] 11. Rule-based backtester v0
  - Verified with rule backtester, library, store, report, CLI, and full v3 research pipeline regression tests.
- [x] 12. Walk-forward validator v0
  - Verified with splitter, validator, store, report, CLI, and full v3 research pipeline regression tests.
- [x] 13. Thesis registry and evaluation layer
  - Verified with thesis registry, decision store, evaluator, reports, CLIs, and full v3 research pipeline regression tests.

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

## Milestone 9 acceptance criteria

- ResearchDatasetRow model exists
- ResearchDatasetStore writes JSONL
- FeatureSnapshot rows join to OutcomeLabel rows by `snapshot_id`
- Dataset rows clearly separate feature fields from outcome fields
- Filtering by token/window/horizon/label quality works
- Dataset builder CLI exists
- Dataset report CLI exists
- Summary report works
- Tests pass without network

## Milestone 10 acceptance criteria

- BaselineEdgeAnalyzer exists
- Default feature list excludes outcome/future fields
- Numeric bucketing works
- Outcome summaries calculate forward return, win rate, runup, drawdown, rug-like drop rate, and no-future-liquidity rate
- BaselineEdgeReport model exists
- Markdown and JSON writers exist
- Baseline edge report CLI exists
- Smoke report CLI exists
- Tests pass without network

## Milestone 11 acceptance criteria

- RuleCondition and RuleDefinition models exist
- RuleBacktester evaluates simple deterministic rules
- Cost assumptions are applied to gross forward returns
- Rule backtest summaries include win rate, profit factor, cumulative net return, and max drawdown
- Default exploratory rule library exists
- RuleBacktestStore writes JSONL
- Markdown and JSON rule backtest reports exist
- Rule backtest CLI exists
- Smoke CLI exists
- Tests pass without network

## Milestone 12 acceptance criteria

- WalkForwardConfig and WalkForwardFold models exist
- Chronological fold splitter exists
- Train/test windows are separated by optional gap
- WalkForwardValidator evaluates rules across folds
- Train and test fold metrics are reported separately
- Rule summaries include consistency across test folds
- WalkForwardValidationStore writes JSONL
- Markdown and JSON walk-forward reports exist
- Walk-forward CLI exists
- Smoke CLI exists
- Tests pass without network

## Milestone 13 acceptance criteria

- Top-level `theses/` folder exists
- One Markdown file exists per thesis
- `THESIS_REGISTRY.md` exists
- ThesisRegistry can load thesis files
- ThesisDecisionStore writes JSONL
- ThesisEvaluator maps walk-forward rule summaries to theses
- Promotion/demotion recommendations are conservative
- Thesis evaluation report exists
- Registry check CLI exists
- Thesis evaluation CLI exists
- Tests pass without network
