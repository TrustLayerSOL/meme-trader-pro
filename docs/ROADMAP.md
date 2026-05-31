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
- [x] 14. Evidence-bearing historical dataset population v0
  - Verified with evidence pipeline package, seed loader, target planner, dry-run backfill, offline rebuild, full-cycle CLI, runbook, and full v3 research pipeline regression tests.
- [x] 15. Evidence run audit and target quality diagnostics v0
  - Verified with offline evidence audit, target inspection, post-run diagnostics, Markdown/JSON reports, and full v3 research pipeline regression tests.
- [x] 16. Real candidate discovery ingestion v0
  - Verified with bounded DexScreener discovery, candidate quality filtering, mock-safe target planning/backfill filters, and full v3 research pipeline regression tests.
- [x] 17. Price proxy coverage and real-only evidence hygiene v0
  - Verified with real-candidate filters, price coverage diagnostics, optional nearest entry fallback, dataset sufficiency reports, and full v3 research pipeline regression tests.
- [x] 18. Price inference and entry coverage improvement v0
  - Verified with diagnostic-only nearest-entry coverage comparison, real-only evidence quality reporting, price inference metadata, ambiguity handling, and full v3 research pipeline regression tests.
- [x] 19. Diagnostic validation review v0
  - Verified with diagnostic baseline/rule/walk-forward/thesis orchestration, clean-vs-fallback comparison reports, diagnostic-only stores, and full v3 research pipeline regression tests.
- [x] 20. Walk-forward fold sufficiency diagnostics v0
  - Verified with fold-window sufficiency sweeps, best diagnostic walk-forward gating, diagnostic-only reports, and full v3 research pipeline regression tests.
- [x] 21. Time-span expansion backfill plan v0
  - Verified with local coverage planning, dry-run-first execution wrapper, offline post-run rebuild helper, reports, and full v3 research pipeline regression tests.
- [x] 22. Bounded evidence expansion run 1
  - Completed as a run-only Helius expansion; generated data remains local and ignored.
- [x] 23. Fast offline rebuild observability v0
  - Adds bounded/progress/timing controls, faster derived-store writes, offline rebuild profile reports, and a fast review runner.
- [x] 24. Best diagnostic walk-forward review v0
  - Adds diagnostic walk-forward findings, fallback dependency reporting, one-command diagnostic cycle, and diagnostic-only review reports.
- [x] 25. Rule failure anatomy and evidence expansion decision v0
  - Adds rule failure anatomy, selected-row inspection, and offline decision reporting before any rule changes.
- [x] 26. Sample adequacy gate and evidence expansion plan v0
  - Prevents tiny diagnostic samples from promoting or demoting theses and reports bounded data expansion needs.
- [x] 27. Sample adequacy expansion plan v0
  - Combines adequacy shortfalls with bounded time-span target planning before any Helius execution.

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

## Milestone 14 acceptance criteria

- Evidence pipeline package exists
- Candidate seed loader exists
- Backfill target planner exists
- Evidence backfill CLI is dry-run by default
- Real Helius backfill requires `--execute`
- Offline research rebuild CLI exists
- Full research cycle CLI exists
- Evidence pipeline runbook exists
- Tests pass without network

## Milestone 15 acceptance criteria

- EvidenceAuditor exists
- Evidence audit counts local stores
- Target quality diagnostics exist
- Mint-only target warnings exist
- Dropoff analysis exists
- Bottleneck inference exists
- Recommended next actions exist
- Markdown/JSON audit reports exist
- Evidence audit CLI exists
- Post-evidence diagnostics CLI exists
- Backfill target inspection CLI exists
- Tests pass without network

## Milestone 16 acceptance criteria

- Real DexScreener ingestor exists
- Real discovery CLI exists
- Candidate quality filter CLI exists
- Mock ingestors are clearly marked test-only
- Real discovery candidates include token_mint and pool_address
- Target planner excludes mock candidates by default
- Evidence backfill excludes mock candidates by default
- Real discovery runbook exists
- Tests pass without network

## Milestone 17 acceptance criteria

- Real candidate filter exists
- Evidence audit distinguishes mock contamination from real evidence bottlenecks
- Price coverage report exists
- `no_price` causes are diagnosed
- Optional nearest entry fallback exists and is clearly diagnostic only
- Dataset sufficiency report exists
- Tests pass without network

## Milestone 18 acceptance criteria

- Entry price coverage comparison exists
- Diagnostic fallback labels and datasets use separate paths under `data/backtests/diagnostics/`
- Fallback rows remain identifiable as `nearest_research_fallback`
- Trade price inference records method metadata when price is inferred
- Ambiguous trade flows do not infer fake precision
- Real-only evidence quality report exists
- Tests pass without network

## Milestone 19 acceptance criteria

- Diagnostic validation review models exist
- Diagnostic validation review compares clean and fallback datasets
- Baseline, rule, walk-forward, and thesis layers can run against diagnostic dataset paths
- Diagnostic stores live under `data/backtests/diagnostics/`
- Diagnostic reports include the research-only fallback warning
- Rule comparisons count nearest fallback selected rows
- Walk-forward comparisons report valid test folds and selected counts
- Thesis comparisons mark diagnostic-only status changes
- Tests pass without network

## Milestone 20 acceptance criteria

- Fold sufficiency models exist
- Fold sufficiency analyzer evaluates multiple chronological fold configs
- Config ranking is based on evidence sufficiency, not returns
- Reports show dataset time span, config comparison, and per-rule sufficiency
- Best diagnostic walk-forward runs only when a config has evidence-bearing folds
- Diagnostic outputs stay under `data/backtests/diagnostics/`
- Tests pass without network

## Milestone 21 acceptance criteria

- Time-span coverage models exist
- Planner summarizes per-token raw/event/feature/outcome/research coverage
- Planner prioritizes no-raw and short-span real candidates
- Plan reports estimate bounded signature and transaction requests
- Execute wrapper defaults to dry-run and requires `--execute` for Helius
- Post-backfill helper runs offline rebuild and diagnostics only
- Tests pass without network
