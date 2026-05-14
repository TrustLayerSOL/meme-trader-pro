# MemeTraderPro Handoff

Last updated: 2026-05-14

## Current Repo

Use this repo as the real working copy:

`/Users/dianeposs/Desktop/Jordan 2/meme_trader_pro`

`/Users/dianeposs/Desktop/Jordan/meme_trader_pro` is intended to remain only a compatibility symlink to the real repo.

## Most Recent User Direction

- Refocus the project into Quant Wallet Tracker V2.
- Cut out broad trading-cockpit noise: charts, GUI polish, social/catalyst automation, manual protection expansion, Market Radar as its own strategy, AI explanations, marketing, and live execution work.
- Keep a clean way to evaluate wallet data.
- Define the right wallet data points, signal contexts, no-trade logging, and replay visibility before worrying about PnL.

## Current Status

- Live execution remains locked.
- Desktop API is running on `127.0.0.1:8765`.
- Paper bot/scanner, watchdog, and wallet discovery are running in `screen` sessions from `/Users/dianeposs/Desktop/Jordan 2/meme_trader_pro`.
- Runtime health reports bot, websocket, scanner, market, quotes, watchdog, open-position monitor, wallet discovery, and Market Radar fresh.
- Runtime currently reports 518 tracked wallets, 5719 paper-watch wallets, and 6237 observed wallets.
- Active Git branch is `phase6-protection-exits`. It has local commits beyond `origin/phase6-protection-exits`; push/PR should be intentional.
- GitHub default branch is `main`; `origin/main` has one newer README-only commit that local `main` does not have.
- Product focus is now Quant Wallet Tracker V2.
- `docs/superpowers/specs/2026-05-14-wallet-quant-tracker-design.md` defines the refocus.
- `docs/superpowers/plans/2026-05-14-wallet-quant-tracker.md` is the implementation plan.
- `research/BUILD_PLAN.md` now marks Quant Wallet Tracker V1 as the active roadmap.

## Performance Snapshot Excluding PENGUINZ

- Total trades: 38
- Closed: 29
- Open: 2
- Failed: 7
- Closed PnL: `-$280.93`
- Open unrealized PnL: about `-$1.98`
- Closed win rate: `3.4%`
- Excluded outlier: `Nietzschean Penguin` / PENGUINZ, about `+$797.21`

Interpretation: without PENGUINZ, the current paper data does not prove edge. The immediate priority is cleaner sample collection, not declaring profitability.

## Latest Change

Added Wallet Quant Baseline Comparison.

Files changed:

- `wallets/wallet_baseline_comparison.py`
- `utils/build_wallet_baseline_comparison.py`
- `tests/test_wallet_baseline_comparison.py`
- `ROADMAP.md`
- `EXPERIMENT_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`
- `handoff.md`

Behavior:

- `utils/build_wallet_baseline_comparison.py` reads `data/wallet_quant_report.json` and `data/wallet_outcome_ledger.json`.
- It writes `data/wallet_baseline_comparison.json`.
- It compares older quant-report recommendations against newer unified outcome-ledger recommendations.
- It classifies rows as agreement, conflict, quant signal unconfirmed, quant-only, ledger-only, ledger-stronger signal, or hold-more-data.
- This is review-only and does not affect trading or wallet-list apply logic.

Current generated comparison:

- Total wallets: `7,855`.
- Quant report wallets: `7,855`.
- Outcome ledger wallets: `28`.
- Overlap: `28`.
- Quant-only: `7,827`.
- Ledger-only: `0`.
- Comparison counts: `7,827` quant-only, `27` hold-more-data, `1` quant signal unconfirmed.

Interpretation:

- The older wallet quant report covers many wallets, but most have no unified outcome-ledger row yet.
- One older demotion signal is not confirmed by the stricter outcome ledger because it has only `5` known outcomes.
- Next work should expand unified outcome coverage before trusting wallet promotion/demotion recommendations.

Verification:

- `./trading_env/bin/python -m unittest tests.test_wallet_baseline_comparison` passed 4 tests.

Next implementation target:

1. Expand unified outcome ledger coverage for quant-only wallets.
2. Backfill accepted/rejected records from existing wallet performance/behavior evidence where decision-time safety is preserved.
3. Keep all promotion/demotion outputs review-only.

## Previous Change

Added later outcome labels and a review-only wallet recommendation engine.

Files changed:

- `research/outcome_labeler.py`
- `research/signal_schema.py`
- `wallets/wallet_promotion_engine.py`
- `wallets/wallet_outcome_ledger.py`
- `tests/test_outcome_labeler.py`
- `tests/test_wallet_promotion_engine.py`
- `tests/test_wallet_outcome_ledger.py`
- `ROADMAP.md`
- `EXPERIMENT_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`
- `handoff.md`

Behavior:

- Later token outcomes now get consistent review labels: `runner`, `rug`, `dead`, `loser`, `open`, or `unknown`.
- Outcome labels include classification reasons and confidence fields.
- The wallet ledger counts known outcomes from labels, not only raw status strings.
- Wallet promotion/demotion recommendation policy now lives in `wallets.wallet_promotion_engine`.
- Recommendations are still review-only and require at least `20` known outcomes before promotion review.

Current generated ledger:

- Records: `4,747`.
- Wallets: `28`.
- Recommendation counts: `28` hold-more-data.

Verification:

- `./trading_env/bin/python -m unittest tests.test_outcome_labeler tests.test_wallet_promotion_engine tests.test_wallet_outcome_ledger tests.test_research_signal_schema` passed 13 tests.

Next implementation target:

1. Build a baseline comparison report between `data/wallet_quant_report.json` and `data/wallet_outcome_ledger.json`.
2. Surface agreement/conflict/missing-evidence per wallet.
3. Keep the report review-only until enough forward data exists.

## Previous Change

Added Wallet Outcome Ledger V1.

Files changed:

- `wallets/wallet_outcome_ledger.py`
- `utils/build_wallet_outcome_ledger.py`
- `tests/test_wallet_outcome_ledger.py`
- `ROADMAP.md`
- `EXPERIMENT_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`
- `handoff.md`

Behavior:

- `utils/build_wallet_outcome_ledger.py` reads current paper trades plus recent rejected-signal rows.
- It normalizes them through `research.signal_schema`.
- It writes `data/wallet_outcome_ledger.json`.
- The ledger aggregates wallet-level total signals, accepted/rejected counts, known outcomes, runner/rug/dead participation, average PnL, average liquidity, average token age, cluster duration, market-regime breakdown, confidence, promotion score, demotion score, and recommendation.
- This is review-only and does not affect trading.

Current generated ledger:

- Records: `4,084`.
- Wallets: `28`.

Verification:

- `./trading_env/bin/python -m unittest tests.test_wallet_outcome_ledger` passed 3 tests.

Next implementation target:

1. Harden later token outcome labels.
2. Add baseline comparison between wallet quant report and wallet-outcome ledger.
3. Make promotion/demotion engine consume ledger evidence as review-only input.

## Previous Change

Added research governance and the first unified signal outcome schema layer.

Files changed:

- `ROADMAP.md`
- `RESEARCH_RULES.md`
- `SIGNAL_REGISTRY.md`
- `EXPERIMENT_LOG.md`
- `research/__init__.py`
- `research/signal_schema.py`
- `tests/test_research_signal_schema.py`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`
- `handoff.md`

Behavior:

- Research changes now have root docs for roadmap, rules, signal registry, and experiment logging.
- New signals/filters/scores/replay features require hypothesis, decision-time safety, measurable source, baseline comparison, and experiment tracking.
- `research.signal_schema` can normalize accepted paper trades and rejected signals into one comparable record shape:

```text
wallet(s) -> signal context -> trade/skip decision -> later token outcome
```

Verification:

- `./trading_env/bin/python -m unittest tests.test_research_signal_schema` passed 3 tests.

Next implementation target:

1. Build `wallets/wallet_outcome_ledger.py`.
2. Backfill unified outcome records from rejected signals and paper trades.
3. Aggregate by wallet into review-only promotion, demotion, and confidence fields.

## Previous Change

Added Quant Wallet Tracker V2 context and replay foundation.

Files changed:

- `.gitignore`
- `wallets/__init__.py`
- `wallets/wallet_metrics.py`
- `wallets/wallet_profiles.py`
- `wallets/wallet_relationships.py`
- `wallets/wallet_score.py`
- `core/wallet_quant.py`
- `core/signal_context.py`
- `core/replay_visibility.py`
- `analysis/signal_context_logger.py`
- `analysis/rejection_hooks.py`
- `analysis/export_sqlite_skips.py`
- `utils/build_replay_visibility_report.py`
- `tests/test_wallet_quant.py`
- `tests/test_signal_context.py`
- `tests/test_replay_visibility.py`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`
- `handoff.md`

Behavior:

- Wallet quant rows now include explicit behavior profiles: ROI, win rate, average hold duration, rug association, entry timing quality, average PnL multiple, runner/rug participation, preferred token age, preferred liquidity range, conviction sizing, data completeness, relationship summary, coordinated entries, and review-only behavior score.
- Rejected scanner and Market Radar paths now build V2 signal contexts with triggering wallets, cluster timing, market state, holder/risk context, execution assumptions, score reasons, and market-regime tags.
- No-trade rows are richer and replay-friendly.
- `data/signal_contexts/contexts.jsonl` is now the runtime-generated signal-context append log.
- `data/replay_visibility_report.json` is generated from recent rejection rows for review.
- Live execution remains locked. This is analysis/reporting only.

Generated local reports:

- `data/wallet_quant_report.json`: 7,855 wallets.
- `data/replay_visibility_report.json`: 500 recent no-trade/rejection records.

Verification:

- `./trading_env/bin/python -m unittest tests.test_wallet_quant tests.test_signal_context tests.test_replay_visibility tests.test_rejection_hooks tests.test_export_sqlite_skips` passed 24 tests.

Next implementation target:

1. Wire the same V2 signal context into successful paper entries and closed paper outcomes.
2. Build one wallet-outcome ledger that links wallet -> signal context -> paper entry/skip -> later outcome.
3. Use no-trade rows to identify filters that are protecting the system versus filters that are blocking winners.

## Previous Change

Refocused the product around Quant Wallet Tracking.

Files changed:

- `docs/superpowers/specs/2026-05-14-wallet-quant-tracker-design.md`
- `docs/superpowers/plans/2026-05-14-wallet-quant-tracker.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`
- `handoff.md`

New operating stance:

- Wallet behavior is the core measurable data loop.
- Runner discovery is an intake source for wallets, not a separate strategy.
- PnL remains useful but is not the primary proof until the wallet loop is clean.
- Broad GUI/chart/social/protection/live-execution lanes are frozen unless directly needed for wallet evaluation.

Next implementation target:

1. Simplify the GUI/reporting surface around wallet funnel, rankings, promotion queue, demotion queue, and wallet detail.
2. Hide/freeze non-wallet tabs or move them into a legacy/admin area.
3. Add stronger wallet outcome metrics from SQLite events/trades/token snapshots.
4. Add wallet tier history once recommendations are stable.

Completed for Wallet Quant Tracker V1:

- Created `core/wallet_quant.py`.
- Created `utils/build_wallet_quant_report.py`.
- Created `tests/test_wallet_quant.py`.
- Generated `data/wallet_quant_report.json`.
- Added read-only `/api/wallet-quant` endpoint.
- Restarted desktop API so the endpoint is live.

Latest wallet quant snapshot:

- Total wallets: `7,438`.
- Trusted: `518`.
- Paper-watch: `6,920`.
- Recommendations: `7,437` hold-more-data, `1` demotion-review, `0` promotion-review.

Important interpretation:

- There is now a large enough observation pool to evaluate, but the report shows very little promotion-grade evidence yet.
- One currently trusted wallet is already flagged for demotion review based on repeated losing paper outcomes and bad behavior labels.

## Previous Change

Completed file-integrity and GitHub audit after external upgrade work.

Findings:

- GitHub repo `TrustLayerSOL/meme-trader-pro` is reachable, public, and the current user has admin permission.
- No open PRs were present.
- The upload confusion is likely branch/state confusion, not a broken GitHub repo: active work is on `phase6-protection-exits`; default branch is `main`.
- `data/memetrader.db` was genuinely malformed. The corrupt copy and sidecars were archived in `data/archives/db_repair_20260514_020339/`.
- The recovered DB was verified and installed as the active `data/memetrader.db`.
- React desktop had type/test drift from upgrade work; shared API types were updated and Decision Ledger rich evidence rows were restored.
- `data/rejected_signals/` is runtime-generated and is now ignored.

Files changed in the audit:

- `.gitignore`
- `apps/desktop/src/components/DecisionLedger.tsx`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/lib/decisions.ts`
- `WORK_LOG.md`
- `handoff.md`

Verification:

- Python core/desktop/market tests passed 250 tests.
- Python compile check passed.
- JSON parse check passed.
- SQLite integrity and quick checks returned `ok`.
- Desktop TypeScript check passed.
- Desktop React tests passed 41 tests.
- Tauri/macOS desktop build completed and produced `.app` and `.dmg`.
- Desktop API `/api/runtime` is online and live execution remains locked.

## Prior Change

Added broad paper-watch wallet expansion.

Files changed:

- `core/wallet_discovery.py`
- `core/wallet_discovery_scheduler.py`
- `utils/discover_candidate_wallets.py`
- `utils/run_wallet_discovery_scheduler.py`
- `core/settings_manager.py`
- `tests/test_core_logic.py`
- `WORK_LOG.md`
- `handoff.md`
- `data/candidate_wallets.json`
- `data/paper_watch_wallets.json`

Behavior:

- Discovery now mines three wallet sources: local skipped runners, current Dexscreener Solana trending/boosted mints, and paper winners.
- Candidate report expanded to 309 wallets: 240 untracked, 69 already tracked.
- Paper-watch expanded from 1 wallet to 381 total wallets after merging new runner wallets with existing paper-watch state.
- Paper-watch wallets are observation only and are not live trade drivers.
- Demotion exists as a lifecycle review action: poor paper performance flags wallets for `DEMOTE_OFF_WATCH_REVIEW`; no automatic deletion yet.

Verification:

- Candidate wallet/wallet lifecycle/scheduler tests passed 18 tests.
- Compile checks passed for changed wallet discovery modules.
- Runtime confirms bot/scanner/websocket online and subscribed to 899 observed wallets.

## Next Logical Work

1. Decide branch integration path: merge/open PR from `phase6-protection-exits` into `main`, or keep `phase6-protection-exits` as the working branch intentionally.
2. Watch runtime pressure after expanding observed wallets; scanner active tasks/backpressure should not stay overloaded.
3. Add a clear GUI panel or report section showing paper-watch wallet performance, promotion candidates, and demotion candidates.
4. Let paper-watch collect closed outcomes before promoting any wallet to trusted.
5. Keep sample reporting lane-separated: wallet-main, Market Radar, exploration, manual/protected, and paper-watch source.
