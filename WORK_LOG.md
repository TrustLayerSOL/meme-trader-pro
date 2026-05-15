# MemeTraderPro Work Log

Running project diary: what is being worked on, what was completed, blockers, and next actions.

Last updated: 2026-05-15

## Current Work

<mark>Active section: Quant Wallet Tracker V2.</mark>

Current implementation target:

- Refocus the product around wallet discovery, wallet behavior measurement, paper-watch evidence, signal context capture, rejection analysis, and replay visibility.
- Freeze broad cockpit, chart, social, protection, Market Radar, AI explanation, marketing, and live-execution work unless it directly supports wallet evaluation.
- Build a Wallet Quant Tracker V2 data loop so every wallet signal, paper outcome, and rejected signal becomes explainable and replayable.

Lead-agent active plan for 2026-05-14:

1. Keep live execution locked.
2. Treat wallet tracking as the primary product and feedback loop.
3. Treat runner discovery as wallet intake, not as a separate strategy center.
4. Define wallet metrics, tiers, and recommendation reasons.
5. Expand `data/wallet_quant_report.json`, `data/signal_contexts/`, `data/rejected_signals/`, and `data/replay_visibility_report.json` around wallet-quality evidence.

Safety carryover:

1. Preserve paper-first behavior, no live auto-sell, and no execution-gate bypass.
2. Keep prepared paper/simulation exits visible but non-executing.
3. Keep durable protection-event/prepared-exit records intact.
4. Continue surfacing holder concentration, token mechanics, quote feasibility, and token snapshots in the native GUI.
5. Review, verify, and update docs after each meaningful GUI chunk.

Highest-value active workstreams:

- Research governance for signals, filters, scores, replay, and experiments.
- Unified signal outcome schema for accepted trades and rejected signals.
- Historical replay dataset contract for comparing past and future wallet signals without hindsight leakage.
- Wallet-outcome ledger from unified accepted/rejected records.
- Wallet Quant Tracker V2 report/context layer.
- Wallet tiering: candidate, paper-watch, promotion-review, trusted, demotion-review, blocked.
- Wallet metrics: early entry, runner capture, drawdown after entry, hold time, round-trip rate, rug exposure, dead-token rate, sample quality, recency decay.
- Signal context capture for every scanner/Market Radar skip path currently wired.
- Replay visibility reports for rejected/no-trade decisions.
- Wallet supply refresh from runners and paper-watch evidence.
- Clean wallet-evaluation UI/reporting.

2026-05-15 update - Historical Replay Dataset Contract:

Changed files:

- `.gitignore`
- `research/historical_replay_dataset.py`
- `utils/build_historical_replay_dataset.py`
- `tests/test_historical_replay_dataset.py`
- `ROADMAP.md`
- `EXPERIMENT_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`

What changed:

- Added the first review-only historical replay dataset contract.
- Unified records can now be converted into replay events with `decision_context`, `decision`, `execution_assumptions`, and `later_outcome` separated.
- Added a decision-time leakage validator that flags future/outcome-style fields inside replay decision context.
- Added a local builder that writes `data/historical_replay/replay_events.jsonl` and `data/historical_replay/summary.json`.
- Generated the first local replay dataset: `6,041` events, `36` accepted trades, `5` failed trades, `6,000` rejected signals, and `0` unsafe/leakage-flagged events.
- Added `data/historical_replay/` to `.gitignore` because replay datasets are generated local research data, not source code.

Verification:

- Added failing tests before implementation for replay event separation, leakage detection, dataset counts, and output writing.
- `./trading_env/bin/python -m unittest tests.test_historical_replay_dataset`
- `./trading_env/bin/python utils/build_historical_replay_dataset.py`

Remaining risk / next step:

- Current replay events are a schema-safe dataset, not a profitability proof.
- Next high-leverage step is fixed evaluation windows plus realistic slippage, latency, liquidity, and failed-fill assumptions before historical results are used to tune wallet scoring.

2026-05-15 update - Replay Realism Assumptions:

Changed files:

- `research/historical_replay_dataset.py`
- `tests/test_historical_replay_dataset.py`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`

What changed:

- Added fixed replay evaluation windows to every historical replay event: `30s`, `2m`, `5m`, and `15m`.
- Added review-only execution realism fields: latency seconds, slippage percent/bps, entry liquidity, liquidity floor, fill status, failed-fill assumption, and max position liquidity percent.
- Added dataset-level `fill_status_counts` so replay quality can be inspected without opening the full JSONL file.
- Regenerated the local historical replay dataset. Current counts: `6,041` events, `0` unsafe/leakage flags, `207` fillable-with-assumptions, `153` failed-liquidity-floor, and `5,681` unknown-liquidity.

Verification:

- Added failing tests before implementation for fixed windows, realistic fill controls, and summary fill-status counts.
- `./trading_env/bin/python -m unittest tests.test_historical_replay_dataset`
- `./trading_env/bin/python utils/build_historical_replay_dataset.py`

Remaining risk / next step:

- The `unknown_liquidity` bucket is too large to make strong historical conclusions.
- Next step is to improve decision-time market context coverage and then compute windowed later outcomes per replay window.

2026-05-15 update - Decision-Time Market Context Enrichment:

Changed files:

- `utils/build_wallet_outcome_ledger.py`
- `tests/test_wallet_signal_backfill.py`
- `ROADMAP.md`
- `research/BUILD_PLAN.md`
- `WORK_LOG.md`

What changed:

- Wallet-performance signal backfill now looks for the latest token snapshot at or before the signal timestamp, within a bounded prior window.
- The enrichment fills missing decision-time `market_info` fields such as price, liquidity, market cap, snapshot time, source, and context.
- Future snapshots remain excluded from decision context; they are still used only for later outcome labels.
- Rebuilt local generated research data. The replay summary improved from `5,681` unknown-liquidity events to `4,697`; fillable-with-assumptions increased from `207` to `691`; liquidity-floor failures increased from `153` to `653`.
- Rebuilt `data/wallet_outcome_ledger.json`: `366` wallets across `6,041` records.

Verification:

- Added failing test first to prove prior snapshot context is used and future snapshot liquidity is ignored.
- `./trading_env/bin/python -m unittest tests.test_wallet_signal_backfill`
- `./trading_env/bin/python utils/build_wallet_outcome_ledger.py`
- `./trading_env/bin/python utils/build_historical_replay_dataset.py`

Remaining risk / next step:

- `4,697` replay events still lack decision-time liquidity, so replay conclusions remain limited.
- Next step is windowed outcome labeling for `30s`, `2m`, `5m`, and `15m`, using only later outcome fields and keeping decision context unchanged.

2026-05-15 update - Wallet Review Queue Resolution:

Changed files:

- `wallets/wallet_candidate_audit.py`
- `utils/build_wallet_candidate_audit.py`
- `obsidian_export/candidate_note.py`
- `obsidian_export/dashboard_notes.py`
- `obsidian_export/exporter.py`
- `tests/test_wallet_candidate_audit.py`
- `tests/test_obsidian_export.py`
- `WORK_LOG.md`

What changed:

- Added resolved-candidate handling to the wallet candidate audit.
- Approved promotions now move out of the active candidate queue once the wallet is actually present in `data/tracked_wallets.json`.
- Resolved candidate review notes are still exported to Obsidian for history, but carry `review_resolved: true` and `audit_status: RESOLVED_APPLIED`.
- The Obsidian Wallet Candidate Audit Queue now filters out resolved review notes.
- Rebuilt `data/wallet_candidate_audit.json`; current active queue is `0` promotion reviews, `13` demotion reviews, and `1` resolved applied promotion.

Verification:

- `./trading_env/bin/python -m unittest tests.test_wallet_candidate_audit tests.test_obsidian_export.ObsidianExportTests.test_wallet_candidate_note_marks_resolved_reviews tests.test_obsidian_export.ObsidianExportTests.test_dashboard_notes_include_required_dataview_queries`
- `./trading_env/bin/python utils/build_wallet_candidate_audit.py`
- `./trading_env/bin/python -m unittest tests.test_wallet_candidate_audit tests.test_obsidian_export tests.test_core_logic.WalletListApplyTests`
- `./trading_env/bin/python -m py_compile wallets/wallet_candidate_audit.py utils/build_wallet_candidate_audit.py obsidian_export/candidate_note.py obsidian_export/dashboard_notes.py obsidian_export/exporter.py`
- `/Applications/MemeTraderPro Obsidian Export.app` completed successfully.

Remaining risk / next step:

- Demotion reviews are still active and need operator review or a compact bulk review policy.
- Next high-leverage step is promotion outcome monitoring: track post-promotion signal quality separately so promoted wallets are demoted if they stop performing.

2026-05-15 update - Approved Promotion Applied From Candidate Audit:

Changed files:

- `core/wallet_list_apply.py`
- `utils/apply_wallet_review.py`
- `tests/test_core_logic.py`
- `data/wallet_review_decisions.json`
- `data/tracked_wallets.json`
- `data/paper_watch_wallets.json`
- `data/wallet_list_update_audit.json`

What changed:

- Recorded the operator approval for the current `PROMOTION_REVIEW` wallet `4dFoJ7QHwq72n2R42J4YxGqX6Y4edYpVPDqnNxRwhfJL`.
- Tightened wallet-list apply so current `data/wallet_candidate_audit.json` can supply promotion evidence when the older lifecycle report still says `KEEP_PAPER_WATCH`.
- Added stale-decision protection: if a saved approval no longer maps to the current candidate audit, apply skips it instead of mutating wallet lists.
- Applied the approved promotion through `utils/apply_wallet_review.py --apply`.
- Tracked wallet count moved from `518` to `519`.
- Backup created at `data/archives/wallet_apply_20260515T010357512189Z_425058b0/`.
- Repaired the apply audit entry so the promotion metrics reflect candidate-audit evidence instead of older zeroed lifecycle metrics.

Verification:

- `./trading_env/bin/python -m unittest tests.test_core_logic.WalletListApplyTests tests.test_obsidian_export`
- `./trading_env/bin/python -m py_compile core/wallet_list_apply.py utils/apply_wallet_review.py tests/test_core_logic.py`
- `./trading_env/bin/python utils/apply_wallet_review.py` preview showed `Promoted: 1`, `Demoted: 0`, `Skipped: 0` before apply.
- `./trading_env/bin/python utils/apply_wallet_review.py --apply` completed with `Promoted: 1`, `Demoted: 0`, `Skipped: 0`.

Remaining risk / next step:

- The 13 `DEMOTION_REVIEW` wallets were not promoted or demoted in this step.
- Continue cycling promoted wallets through paper evidence; demote later if their tracked outcomes degrade.

2026-05-14 update - Obsidian Wallet Review Decisions Page:

Changed files:

- `obsidian_export/decision_note.py`
- `obsidian_export/exporter.py`
- `obsidian_export/README.md`
- `tests/test_obsidian_export.py`
- `WORK_LOG.md`
- `handoff.md`

What changed:

- Added an Obsidian dashboard page for `data/wallet_review_decisions.json`.
- Export now writes `MemeTraderPro/Dashboards/Wallet Review Decisions.md`.
- The page summarizes saved decisions, approved promotions/demotions, notes, timestamps, wallet links, and whether each decision still maps to the current candidate audit.
- Confirmed `/Applications/MemeTraderPro Obsidian Export.app` runs the current repo exporter against `/Users/dianeposs/Desktop/Jordan/obsidian-research/quant-database`.

Verification:

- `./trading_env/bin/python -m unittest tests.test_obsidian_export`

Remaining risk / next step:

- Saved decisions are visible in Obsidian, but the apply path should still be tightened to reject stale decisions that no longer appear in the current candidate audit.

2026-05-14 update - Obsidian Wallet Candidate Review Export:

Changed files:

- `obsidian_export/candidate_note.py`
- `obsidian_export/exporter.py`
- `obsidian_export/dashboard_notes.py`
- `obsidian_export/README.md`
- `tests/test_obsidian_export.py`
- `ROADMAP.md`
- `research/BUILD_PLAN.md`
- `WORK_LOG.md`
- `handoff.md`

What changed:

- Added generated Obsidian review notes for `data/wallet_candidate_audit.json`.
- Export now writes `MemeTraderPro/WalletCandidateReviews/` notes with wallet link, recommendation action, audit status, evidence gates, outcome evidence, recommendation reasons, and audit notes.
- The Obsidian dashboard now includes a Wallet Candidate Audit Queue Dataview section.
- Wallet-list apply remains blocked by generated audit state; this export is review-only.

Verification:

- `./trading_env/bin/python -m unittest tests.test_obsidian_export`
- `./trading_env/bin/python -m py_compile obsidian_export/*.py tests/test_obsidian_export.py`
- Smoke export to `/tmp/mtp_obsidian_candidate_smoke` wrote `619` generated notes, including candidate review notes.

Remaining risk / next step:

- Obsidian is still an external review surface, not source of truth. Next step is either exporting to the operator's actual vault path or tightening the approved-decision path against these candidate review packets.

2026-05-14 update - Wallet Candidate Audit Report:

Changed files:

- `wallets/wallet_candidate_audit.py`
- `utils/build_wallet_candidate_audit.py`
- `tests/test_wallet_candidate_audit.py`
- `ROADMAP.md`
- `EXPERIMENT_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`
- `handoff.md`

What changed:

- Added a review-only audit report for snapshot-linked promotion/demotion candidates.
- The report summarizes sample gates, source coverage, known outcomes, runner/rug/dead counts, average PnL, confidence, recommendation reasons, and baseline comparison status.
- Generated `data/wallet_candidate_audit.json`.
- Current audit counts: `14` candidates, `1` promotion-review, `13` demotion-review, `14` human-review-required, `0` insufficient-evidence.
- Wallet-list apply is explicitly blocked in the report.

Verification:

- Added failing tests before implementation for candidate inclusion, apply blocking, comparison status, and thin-sample audit status.
- Focused tests passed: `./trading_env/bin/python -m unittest tests.test_wallet_candidate_audit`.

Remaining risk / next step:

- This is an audit artifact only. Next step is a human-readable export/review workflow so the operator can inspect candidates before any list mutation is allowed.

2026-05-14 update - Snapshot-Linked Signal Outcomes:

Changed files:

- `research/outcome_linker.py`
- `utils/build_wallet_outcome_ledger.py`
- `tests/test_outcome_linker.py`
- `tests/test_wallet_signal_backfill.py`
- `ROADMAP.md`
- `EXPERIMENT_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`
- `handoff.md`

What changed:

- Added `research.outcome_linker` to link wallet-performance signal observations to later SQLite `token_snapshots`.
- The linker uses snapshots after the signal timestamp inside a bounded evaluation window.
- Future snapshot data is stored only as `later_token_outcome`; signal context and decision fields stay decision-time safe.
- Regenerated the local wallet outcome ledger: `5,766` unified records across `251` wallets.
- Snapshot linking produced `1,617` known outcomes: `269` runner labels, `54` rug labels, and `441` dead labels.
- Current generated recommendation counts: `13` demotion-review, `1` promotion-review, `237` hold-more-data.

Verification:

- Added failing tests before implementation for snapshot outcome linking and builder integration.
- Focused tests passed: `./trading_env/bin/python -m unittest tests.test_outcome_linker tests.test_wallet_signal_backfill`.

Remaining risk / next step:

- Snapshot-linked outcomes are a stronger research signal, but still need audit before wallet-list apply logic consumes them. Next step is an audit report for the generated promotion/demotion candidates.

2026-05-14 update - Wallet Performance Signal Backfill:

Changed files:

- `research/signal_schema.py`
- `utils/build_wallet_outcome_ledger.py`
- `tests/test_research_signal_schema.py`
- `tests/test_wallet_signal_backfill.py`
- `ROADMAP.md`
- `EXPERIMENT_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`
- `handoff.md`

What changed:

- Added `build_record_from_wallet_signal` to normalize `data/wallet_performance.json` signal observations into the unified signal outcome schema.
- Updated `utils/build_wallet_outcome_ledger.py` to include wallet-performance signal rows.
- These records preserve decision-time wallet/mint/score/token-age context, but keep later token outcome as `unknown`.
- Regenerated the local wallet outcome ledger: `5,762` unified records across `251` wallets.
- Regenerated the baseline comparison: `231` overlapping wallets, `7,624` quant-only wallets, `20` ledger-only wallets, and `1` unconfirmed quant demotion signal.

Verification:

- Added failing tests before implementation for wallet signal schema adaptation and builder backfill coverage.
- Focused tests passed: `./trading_env/bin/python -m unittest tests.test_research_signal_schema tests.test_wallet_signal_backfill`.

Remaining risk / next step:

- This expands observation coverage, not known outcome proof. Next step is linking signal observations to later token outcomes by mint/time where valid data exists.

2026-05-14 update - Wallet Quant Baseline Comparison:

Changed files:

- `wallets/wallet_baseline_comparison.py`
- `utils/build_wallet_baseline_comparison.py`
- `tests/test_wallet_baseline_comparison.py`
- `ROADMAP.md`
- `EXPERIMENT_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`
- `handoff.md`

What changed:

- Added a review-only comparison report that checks `data/wallet_quant_report.json` against `data/wallet_outcome_ledger.json`.
- The report classifies each wallet as agreement, conflict, unconfirmed quant signal, quant-only, ledger-only, ledger-stronger signal, or hold-more-data.
- Generated the local comparison report at `data/wallet_baseline_comparison.json`.
- Current generated comparison: `7,855` total wallets, `7,855` quant rows, `28` ledger rows, `28` overlap, `7,827` quant-only, `0` ledger-only.
- Current comparison counts: `7,827` quant-only, `27` hold-more-data overlaps, `1` quant signal unconfirmed.

Verification:

- Added failing tests before implementation for agreement, unconfirmed quant signal, quant-only/ledger-only counts, and hold-more-data status.
- Focused comparison tests passed: `./trading_env/bin/python -m unittest tests.test_wallet_baseline_comparison`.

Remaining risk / next step:

- The comparison shows the outcome ledger only covers a tiny slice of the broader wallet universe. Next step is expanding unified outcome coverage for quant-only wallets before trusting promotion/demotion decisions.

2026-05-14 update - Outcome Labels And Review-Only Wallet Recommendations:

Changed files:

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

What changed:

- Added consistent later-token outcome labels: `runner`, `rug`, `dead`, `loser`, `open`, and `unknown`.
- Added classification reasons, label confidence, max favorable excursion, and liquidity-change fields where data exists.
- Moved wallet promotion/demotion recommendation policy into `wallets.wallet_promotion_engine`.
- Kept recommendations review-only and blocked promotion review until a wallet has at least `20` known outcomes.
- Regenerated the local wallet outcome ledger from current data: `4,747` unified records across `28` wallets.
- Current generated recommendation counts: `28` hold-more-data, `0` promotion-review, `0` demotion-review.

Verification:

- Added failing tests before implementation for outcome labeling, promotion policy, and labeled-outcome known-count handling.
- Focused tests passed: `./trading_env/bin/python -m unittest tests.test_outcome_labeler tests.test_wallet_promotion_engine tests.test_wallet_outcome_ledger tests.test_research_signal_schema`.

Remaining risk / next step:

- This improves measurement quality, not profitability. Next step is a baseline comparison report between `data/wallet_quant_report.json` and `data/wallet_outcome_ledger.json`.

2026-05-14 update - Wallet Outcome Ledger V1:

Changed files:

- `wallets/wallet_outcome_ledger.py`
- `utils/build_wallet_outcome_ledger.py`
- `tests/test_wallet_outcome_ledger.py`
- `ROADMAP.md`
- `EXPERIMENT_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`
- `handoff.md`

What changed:

- Added a review-only wallet-outcome ledger that aggregates unified accepted-trade, failed-trade, and rejected-signal records by wallet.
- The ledger tracks total signals, accepted signals, rejected signals, known outcomes, runner/rug/dead participation, average PnL after signal, average liquidity, average token age, average cluster duration, market-regime breakdown, confidence, promotion score, demotion score, and recommendation.
- Added a builder utility that normalizes current paper trades and rejection rows through `research.signal_schema`, then writes `data/wallet_outcome_ledger.json`.
- Generated the local ledger from current data: `4,084` unified records across `28` wallets.
- Kept the ledger review-only. It does not promote wallets automatically and does not affect trading logic.

Verification:

- Added failing tests before implementing `wallets.wallet_outcome_ledger`.
- `./trading_env/bin/python -m unittest tests.test_wallet_outcome_ledger` passed 3 tests.

Remaining risk / next step:

- Later token outcome labels are still basic. The next grounded step is to harden outcome labeling and then make the promotion/demotion engine consume the ledger as review-only evidence.

2026-05-14 update - Research governance and unified signal outcome schema:

Changed files:

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

What changed:

- Added formal research governance docs so new signals, filters, wallet scores, and replay features require a hypothesis, decision-time safety, measurable source, baseline comparison, and experiment log entry.
- Added a root roadmap that keeps the active phase centered on Quant Wallet Tracker V2 and freezes dashboards, live execution, social scraping, ML, and unrelated UI work.
- Added a signal registry covering wallet ROI, win rate, hold duration, rug association, cluster timing, liquidity, market cap, token age, estimated slippage, concentration/risk flags, market regime, entry timing quality, rejection reason, and later token outcome.
- Added an experiment log template and first entry for the unified signal outcome schema.
- Added `research.signal_schema`, which creates one comparable record shape for accepted trades, failed trades, rejected signals, skipped signals, and future replay evaluations:

```text
wallet(s) -> signal context -> trade/skip decision -> later token outcome
```

Verification:

- Added failing tests first for the missing unified schema layer.
- `./trading_env/bin/python -m unittest tests.test_research_signal_schema` passed 3 tests.

Remaining risk / next step:

- The unified schema exists as a helper and adapters. Runtime accepted paper entries are not yet being persisted into a dedicated unified outcome ledger.
- Next step is `wallets/wallet_outcome_ledger.py`: aggregate unified signal outcome records by wallet and produce review-only promotion/demotion confidence fields.

2026-05-14 update - Quant Wallet Tracker V2 context and replay foundation:

Changed files:

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

What changed:

- Added Wallet Quant Tracker V2 behavioral profile fields without treating missing data as known evidence.
- Added review-only wallet profile helpers for ROI, win rate, average hold duration, rug association, entry timing, average PnL multiple, runner/rug participation, preferred token age, preferred liquidity range, conviction sizing, relationships, coordinated entries, and behavior score.
- Added canonical signal context construction for scanner and Market Radar skip paths, including triggering wallets, cluster timing, market/liquidity/token-age context, holder/risk context, execution assumptions, scoring tails, and market-regime tags.
- Added append-only signal-context logging at `data/signal_contexts/contexts.jsonl`; this is runtime-generated and ignored by git.
- Enriched no-trade/rejection rows so future filter calibration can review complete context instead of only prose reasons.
- Added Replay Visibility review report builder from rejection rows at `data/replay_visibility_report.json`.
- Kept all changes review-only and paper-safe. No live trading, buy/sell, auto-sell, or execution gates were enabled.

Generated local reports:

- `data/wallet_quant_report.json` regenerated with `7,855` wallets.
- `data/replay_visibility_report.json` generated from the latest `500` rejection/no-trade rows.

Verification:

- Added failing V2 tests first, then implemented the minimal passing layer.
- `./trading_env/bin/python -m unittest tests.test_wallet_quant tests.test_signal_context tests.test_replay_visibility tests.test_rejection_hooks tests.test_export_sqlite_skips` passed 24 tests.

Remaining risk / next step:

- Signal context logging is currently wired into scanner/Market Radar rejected-signal paths and SQLite skip export. The next high-leverage step is wiring the same context builder into successful paper entries and closed paper outcomes so entered trades and no-trades share one replayable schema.
- Wallet profile metrics still depend on JSON wallet performance/behavior sources. A later SQLite wallet-outcome table should become canonical after enough forward data exists.

2026-05-14 update - Quant Wallet Tracker refocus:

Changed files:

- `docs/superpowers/specs/2026-05-14-wallet-quant-tracker-design.md`
- `docs/superpowers/plans/2026-05-14-wallet-quant-tracker.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`
- `handoff.md`

What changed:

- Accepted the strategic refocus: MemeTraderPro is now centered on Quant Wallet Tracking, not a broad meme trading cockpit.
- Defined the strongest feedback loop as wallet discovery -> observation -> paper-watch evidence -> wallet scoring -> promotion/demotion.
- Frozen lanes for the next iteration: chart polish, broad GUI work, social/catalyst automation, AI explanations, Market Radar as a separate strategy, manual protection expansion, marketing assets, and live execution wiring.
- Created a design spec and implementation plan for Wallet Quant Tracker V1.
- Added `data/wallet_quant_report.json` as the next target wallet-evaluation artifact in the data source map.

Next step:

- Implement Wallet Quant Report V1: metric aggregation, tier recommendation, report builder, API endpoint, and wallet-first UI/report surface.

2026-05-14 update - Wallet Quant Report V1 foundation:

Changed files:

- `core/wallet_quant.py`
- `utils/build_wallet_quant_report.py`
- `tests/test_wallet_quant.py`
- `desktop_api.py`
- `tests/test_desktop_api.py`
- `research/DATA_SOURCE_MAP.md`
- `docs/superpowers/plans/2026-05-14-wallet-quant-tracker.md`
- `WORK_LOG.md`
- `handoff.md`

What changed:

- Added the first Quant Wallet Tracker metric module.
- Added review-only tier recommendation actions: `PROMOTION_REVIEW`, `DEMOTION_REVIEW`, `KEEP_TRUSTED`, and `HOLD_MORE_DATA`.
- Added behavior-focused wallet rows with tier, signal count, paper-watch sample size, win/loss counts, expectancy, rolling 7d/30d entries, 30d win rate, hold-time fields, closed/failed trade counts, exit/failure reasons, labels, sample quality, and recommendation reasons.
- Added `utils/build_wallet_quant_report.py`, which writes `data/wallet_quant_report.json`.
- Added read-only desktop API route `/api/wallet-quant`.
- Restarted the desktop API so the endpoint is live.

Current report snapshot:

- Wallets in report: `7,438`.
- Trusted wallets: `518`.
- Paper-watch wallets: `6,920`.
- Current recommendation counts: `7,437` hold-more-data, `1` demotion-review, `0` promotion-review.

Interpretation:

- The system now has a much larger wallet pool, but almost all wallets need more clean evidence before promotion.
- The first demotion-review wallet is a trusted wallet with five closed paper outcomes, all losses, negative expectancy, and copy-bait/follower-trap style labels.
- This confirms the refocus was needed: the public/trusted list should not be assumed good.

Verification:

- `./trading_env/bin/python -m unittest tests.test_wallet_quant tests.test_desktop_api tests.test_core_logic tests.test_market_checker` passed 256 tests.
- Python compile check passed.
- `data/wallet_quant_report.json` parsed as valid JSON.
- `git diff --check` passed.
- `npm --prefix apps/desktop run check` passed.
- Live `GET /api/wallet-quant?limit=3` returned `WALLET_QUANT_REVIEW_ONLY`, `live_execution_locked=true`, and the expected wallet counts.

Remaining risk / next step:

- Non-wallet GUI tabs still exist. Next pass should hide/freeze them or visually move them behind a legacy/admin area.
- Wallet metrics are still composed from existing JSON behavior/performance sources; later work should add canonical SQLite wallet outcome tables.

2026-05-14 update - File integrity and GitHub audit after external upgrade:

Changed files:

- `.gitignore`
- `apps/desktop/src/components/DecisionLedger.tsx`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/lib/decisions.ts`
- `WORK_LOG.md`
- `handoff.md`

What changed:

- Audited Git/GitHub state after the external upgrade work. The active branch is `phase6-protection-exits` and is synced with `origin/phase6-protection-exits`; GitHub default `main` has one newer README-only commit and the local `main` branch is behind it.
- Confirmed GitHub repo `TrustLayerSOL/meme-trader-pro` is reachable, public, and the current user has admin permission. No open pull requests were present.
- Found real SQLite corruption in `data/memetrader.db`. Backed up the malformed database and sidecars under `data/archives/db_repair_20260514_020339/`, recovered the database with SQLite `.recover --ignore-freelist`, verified the recovered database with `PRAGMA integrity_check`, and replaced the active DB with the verified recovered copy.
- Restored the React Decision Ledger detail rows for catalyst evidence, route feasibility, holder/cluster context, market context, Market Radar, paper outcome, and OpenAI advisory text. These helper summaries existed in `apps/desktop/src/lib/decisions.ts` but were no longer rendered, causing a regression test failure.
- Updated shared desktop API TypeScript contracts for social freshness, position-detail source contracts, and trade ledger source metadata.
- Added `data/rejected_signals/` to `.gitignore` because it is runtime-generated local state.
- Restarted desktop API, bot, watchdog, and wallet-discovery screens after DB recovery. Live execution remains locked.

Verification:

- `./trading_env/bin/python -m unittest tests.test_core_logic tests.test_desktop_api tests.test_market_checker` passed 250 tests.
- Python compile check for repo `.py` files passed.
- JSON parse check passed with `json_files_checked errors 0`.
- `sqlite3 data/memetrader.db 'PRAGMA integrity_check;'` and post-restart `PRAGMA quick_check` returned `ok`.
- `npm --prefix apps/desktop run check` passed.
- `npm --prefix apps/desktop test -- --run` passed 41 tests.
- `npm --prefix apps/desktop run build` completed and produced the macOS app and DMG bundle.
- Desktop API `/api/runtime` returned `online` with bot, websocket, scanner, market, quotes, watchdog, open-position monitor, wallet discovery, and Market Radar fresh.
- Desktop API `/api/trades` returned `source: sqlite_trades` and `live_execution_locked: true`.

Remaining risk:

- `main` and `phase6-protection-exits` are not the same branch. Upload/push confusion should be resolved by intentionally merging or opening a PR from `phase6-protection-exits` into `main`, rather than pushing random local files.
- Social freshness remains failed/stale because manual/catalyst/social collector inputs are old or errored; this is not a file-integrity failure but should be handled as a separate collector-health task.
- Runtime freshness still reports the old compatibility file `data/live_state.json` as old. Canonical root `live_state.json` is fresh.

2026-05-13 update - Broad paper-watch wallet expansion:

Changed files:

- `core/wallet_discovery.py`
- `core/wallet_discovery_scheduler.py`
- `utils/discover_candidate_wallets.py`
- `utils/run_wallet_discovery_scheduler.py`
- `tests/test_core_logic.py`
- `data/candidate_wallets.json`
- `data/paper_watch_wallets.json`
- `WORK_LOG.md`
- `handoff.md`

What changed:

- Shifted wallet discovery from only mining tracked-wallet local events to a broader runner-first harvest.
- Added local skipped-runner mining: tokens seen locally in `token_snapshots` that later ran hard are selected as wallet-discovery bait.
- Added Dexscreener trending/boosted wallet harvest using current Solana token-profile/boost feeds.
- Lowered paper-watch entry policy from repeat-only to discovery mode: one early buy on a verified runner can enter `paper_watch`; trusted promotion still requires repeat paper outcome evidence.
- Kept demotion/removal review-based. Bad wallets are flagged through lifecycle metrics after enough paper entries; they are not blindly deleted.
- Increased the wallet discovery scheduler to mine 24 hours of local events, local runners, paper winners, and Dexscreener trending mints every 15 minutes.

Runtime result:

- Candidate wallet report expanded to `309` candidates.
- Untracked candidate wallets: `240`.
- Already tracked wallets reviewed: `69`.
- Review summary: `3` promotion-review candidates, `237` paper-watch candidates, `14` demotion-review tracked wallets.
- Paper-watch list expanded from `1` wallet to `381` total wallets after merging new runner wallets with existing paper-watch state.
- Restarted the paper bot/scanner and wallet discovery scheduler.
- Runtime now shows `899` observed/subscribed wallets: `518` tracked plus `381` paper-watch.

Verification:

- `./trading_env/bin/python -m unittest tests.test_core_logic.CandidateWalletDiscoveryTests tests.test_core_logic.WalletLifecycleTests tests.test_core_logic.WalletDiscoverySchedulerTests` passed 18 tests.
- `./trading_env/bin/python -m py_compile core/wallet_discovery.py core/wallet_discovery_scheduler.py utils/discover_candidate_wallets.py utils/run_wallet_discovery_scheduler.py` passed.
- Confirmed runtime reports bot/scanner/websocket online and subscribed to `899` wallets.

Remaining risk:

- Expanding observed wallets increases event volume. Backpressure is active, but scanner throughput should be watched for stale heartbeats or heavy wallet backlog drops.
- Promotion to trusted should remain evidence-gated until paper-watch wallets have enough closed trade outcomes.

2026-05-13 update - Paper metrics without PENGUINZ outlier:

- Current strategy summary excluding the one `Nietzschean Penguin` / PENGUINZ trade: 38 total trades, 29 closed, 2 open, 7 failed.
- Closed PnL excluding PENGUINZ: `-$280.93`.
- Open unrealized PnL excluding PENGUINZ: about `-$1.98`.
- Closed win rate excluding PENGUINZ: `3.4%`.
- New-created/early scanner side remains the weak side: the open trades are still medium-risk exploration confirmation-block observations, both about `-20%`.
- The excluded PENGUINZ outlier remains separately tracked at about `+$797.21`; do not use it to declare edge until similar winners repeat.

2026-05-13 update - Bad-sample exploration suppressor:

Changed files:

- `core/paper_exploration.py`
- `core/settings_manager.py`
- `tests/test_core_logic.py`
- `WORK_LOG.md`
- `handoff.md`

What changed:

- Added a paper-only bad-sample suppressor for confirmation-blocked exploration trades.
- The suppressor blocks medium-risk confirmation-observation samples unless they clear stricter score/edge floors.
- It also blocks confirmation-observation samples with thin liquidity or too-small market cap when that market data is available.
- Main-lane paper entries and live execution are not loosened.
- Added persistent settings:
  - `paper_exploration_bad_sample_suppression_enabled`
  - `paper_exploration_confirmation_medium_risk_min_score`
  - `paper_exploration_confirmation_medium_risk_min_edge_score`
  - `paper_exploration_confirmation_min_liquidity_usd`
  - `paper_exploration_confirmation_min_market_cap_usd`

Verification:

- Added failing tests first for the medium-risk confirmation-block sample pattern.
- `./trading_env/bin/python -m unittest tests.test_core_logic` passed 159 tests.
- `./trading_env/bin/python -m py_compile core/paper_exploration.py core/settings_manager.py` passed.
- Restarted the paper bot/scanner so the new suppressor is active.

Remaining risk:

- Existing open exploration trades were not force-closed; the suppressor prevents new repeat samples but does not rewrite history.
- More cleanup may be needed after 50-100 new closed samples under the stricter gate.

2026-05-13 update - Market Radar throughput and RKC-style fresh-runner exception:

- Rechecked live Market Radar after the no-new-buy stall. The lane was healthy and using zero Jupiter quotes, but recent rejects were overwhelmingly thin/quiet tokens: mostly `liquidity_below_hot_lane` and `entry_liquidity_below_quality_gate`.
- Added a narrow fresh-pair exception for RKC-style runners. Very fresh pairs can now pass the age gate only when they already have high liquidity, market cap inside the meme window, heavy 1-hour volume, strong M5 activity, balanced buy/sell flow, social/site proof, and no M5/H1 decay block.
- Kept normal too-fresh/thin launches blocked; the exception does not loosen quote or buy budgets.
- Increased Market Radar scan depth from 40 to 120 candidates per cycle while keeping processed candidates at 8, paper entries at 1, and quote attempts at 1. This lets the lane scan past recently-seen feed clutter without adding Jupiter pressure.
- Restarted the paper bot with the full environment loaded. Live execution remains locked; one `memetrader_bot` process is running.
- Verified with `./trading_env/bin/python -m unittest tests.test_core_logic -k market_radar`, targeted settings tests, desktop Market Radar API tests, and Python compile checks.

2026-05-12 update - Wallet-main winner traits and RKC regression:

- Reviewed the two positive wallet-main/co-main paper outcomes against the losing main-lane trades.
- Key finding: quote pass alone is not predictive. The clean full-metadata winner had elite live wallet quality, low risk, deep liquidity, strong score, and no rapid-flip wallet behavior; the losing 1-2 wallet entries passed quotes but had weaker wallet quality, medium risk or sub-elite solo quality, thin liquidity/tiny market cap, and rapid-flip history.
- Added a wallet-main quality gate before swap quotes. Weak one/two-wallet main entries are now blocked from main-lane paper buys unless they meet conservative winner-like traits: low risk, stronger liquidity/market cap, elite solo score/quality or strong two-wallet average/top quality, and no rapid-flip history.
- Added an exact RKC regression for `7HgfXftRBBqsYtAEYcqjGLQrNJLL6Tww9ek4rE3Apump`: a hot Dexscreener Solana candidate with no wallet signal must enter Market Radar, write a decision, and open a paper-only `market_radar` trade when market and quote gates pass.
- Restarted the paper bot and desktop API so the new gate is active in the running app. Duplicate old bot process was removed; one `memetrader_bot` process is now running.
- Verified with `./trading_env/bin/python -m unittest tests.test_core_logic tests.test_desktop_api tests.test_market_checker`, `./trading_env/bin/python -m unittest tests.test_desktop_api`, and `npm --prefix apps/desktop test -- --run`.

2026-05-12 update - Market Radar postmortem detail:

- Extended the Market Radar Token Nursery API rows with a `postmortem` block for closed/failed paper-only radar outcomes.
- Postmortem detail now exposes entry/exit price, entry/exit liquidity, liquidity change %, entry/exit market cap, market-cap change %, PnL/PnL %, position size, exit/failure reason, and derived hold seconds from the decision result/paper outcome.
- React/Tauri Replay and the static browser Replay panel now show closed/failed radar rows as outcome rows: PnL in the score column, exit liquidity/market cap plus change %, and the exit/failure reason in the reason column.
- Verified with `./trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests.test_market_radar_review_groups_token_nursery_stages tests.test_desktop_api.DesktopApiTests.test_market_radar_review_stage_requires_quote_worthy_candidate_for_quote_watch`, `npm --prefix apps/desktop test -- --run`, and `node tests/test_desktop_gui_chart.mjs`.

2026-05-12 update - Market Radar entry decay gate:

- Added a paper-only Market Radar quality gate for fresh 5-minute price decay.
- New setting: `market_radar_min_m5_price_change_pct`, default `-12.0`.
- When Dex/Pump market data includes `price_change_m5` below the threshold, Market Radar now blocks before quotes with `entry_m5_price_decay`.
- Missing 5-minute price-change data does not block by itself, preserving RKC-style hot runners that pass liquidity, market-cap, activity, and social/site gates.
- Verified `entry_m5_price_decay` is written into the Market Radar decision payload and skips quote calls.
- `./trading_env/bin/python -m unittest tests.test_core_logic -k market_radar` passed 13 tests.
2026-05-12 update - Reddit social collector conservative run:
- Ran `./trading_env/bin/python -m social.reddit_collector --subreddit SolanaMemeCoins --subreddit memecoins --limit 5`.
- Live Reddit fetches failed with DNS resolution errors for both subreddits, so `fetched_count` and `stored_count` stayed at 0 and `trade_triggered` remained `false`.
- Rebuilt catalyst cards with `./trading_env/bin/python -m core.catalyst_cards`, which saved `data/catalyst_cards.json` with 6 cards.
- Verified social freshness through `desktop_api.build_social_freshness_payload()`: overall `FAIL`, rows = manual social import `STALE`, catalyst cards `FRESH`, Reddit collector `ERROR`.
- No execution settings were changed and live trading stayed disabled.
- Fast open-position monitor vs slower deep watchdog architecture split.
- Desktop app launch/session reliability and stale-state visibility.
- Selected-token chart polish and trade-stream candle pipeline.
- Wallet discovery and promotion/demotion workflow.
- Native wallet detail and protection drill-down panels.
- Native settings/log/status panels for daily operator use.
- Holder concentration / linked-cluster risk checks surfaced in token detail.
- Token risk/performance snapshots for entries, skips, exits, and watchdog checks surfaced in the native app.
- Social tracker / catalyst-card intelligence based on X hype, wallet confirmation, and price alignment.

Helper-agent coordination note:

- Helpers must update `WORK_LOG.md`, but no two helpers may edit the same file at the same time.
- Until a separate helper-log-fragment pattern is approved, use at most one editing helper at a time or use read-only helper agents whose findings the lead agent logs.
- Any helper must receive a narrow ownership area and must list exact files changed in its final report.

Why this matters:

- Manual trades can collapse faster than a human can react.
- The system needs to prove pre-entry rejection, fast open-position monitoring, alerting, exit advice, quote checks, audit state, and simulated sell intent before any real auto-sell is considered.
- This keeps the project aligned with paper-first safety rules.

## Current Blockers / Constraints

- Live execution remains locked by design.
- Auto-sell is not active and should not be activated yet.
- Deep watchdog checks can take 40-120 seconds due to RPC/market/mint inspection latency. This is too slow to represent as sub-second rug rescue, so fast open-position monitoring must be separated from deep inspection before live execution.
- Helius Gatekeeper, standard Helius mainnet, and public Solana read fallback currently report healthy.
- Some runtime and live-state sources are stale when the backend loops are not running.
- Holder concentration is now wired into quote-worthy live candidate decisions. True linked-wallet graph risk is still marked as not checked until a real owner/funder graph source exists.
- Prepared exits now carry quote-feasibility metadata. One protected token has a clearly marked simulated/test amount and quote-feasible result; remaining protected manual items still need wallet-derived or verified operator-owned amounts.

## Next Actions

1. Monitor the hourly Reddit collector for clean runs, rate-limit errors, duplicate quality, and noisy keywords before adding more sources.
2. Keep broader crypto and stablecoin data as market-regime context only; do not expand the trade universe beyond memecoin candidates until paper edge is proven.
3. Continue canonical read-path migration only where a table, backfill, and parity guard exist; wallet stats and social remain JSON-first for now.
4. Let the main strategy collect at least 50 closed trades, with 100 preferred, before judging main-strategy profitability.
5. Keep Exploration Lane conservative after the negative sample; it is now auto-paused when a small closed sample has poor expectancy.
6. Let Market Radar Co-Main collect hot Dex/Pump-style paper samples separately from wallet-main and exploration trades.
7. Keep the desktop API execution-locked; only token-protected metadata mutations are allowed.

## Completed Work

### 2026-05-12 - Market Radar Token Nursery Review

What changed:

- Added a read-only `/api/market-radar-review` endpoint that turns canonical Market Radar decision records into a Token Nursery: rejected, watch, quote watch, paper bought, closed, and failed.
- Added the Token Nursery to both Replay surfaces: the React/Tauri desktop Replay view and the static browser view at `http://127.0.0.1:8765/`.
- Added React Decision Ledger filters for Co-Main and Market Radar parity with the static browser view.
- Kept the feature review-only: it reads SQLite decision records and never mutates settings, trades, or live execution gates.
- Tightened nursery stage classification so quality-gate rejects with `buy_quote_pass=false` / `sell_quote_pass=false` no longer appear as Quote Watch unless the candidate actually passed Market Radar scoring and then hit quote/route budget or route failure.

Why:

- Market Radar Quality Gate V2 reduced bad hot-feed entries, but the operator still needed a quick way to see whether candidates were being rejected for the right reasons or getting stuck at quote/route checks.
- This makes the new co-main route auditable before more threshold tuning.

Verification:

- `./trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests.test_market_radar_review_groups_token_nursery_stages` passed.
- `npm --prefix apps/desktop test -- --run src/lib/api.test.ts src/lib/decisions.test.ts` passed.
- `npm --prefix apps/desktop test -- --run` passed 47 tests.
- `./trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests.test_market_radar_review_groups_token_nursery_stages tests.test_desktop_api.DesktopApiTests.test_paper_review_includes_decision_lane_report tests.test_desktop_api.DesktopApiTests.test_decision_lane_report_counts_market_radar_skip_reasons tests.test_desktop_api.DesktopApiTests.test_decision_outcome_analytics_groups_labeled_edges` passed 4 tests.
- `./trading_env/bin/python -m unittest tests.test_core_logic tests.test_desktop_api tests.test_market_checker` passed 267 tests.
- `node tests/test_desktop_gui_chart.mjs` passed.
- Browser sanity check confirmed Replay shows `Paper Profitability Review`, `Market Radar Token Nursery`, and `Decision Ledger` after restarting the local desktop API.
- `./trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests.test_market_radar_review_groups_token_nursery_stages tests.test_desktop_api.DesktopApiTests.test_paper_review_includes_decision_lane_report tests.test_desktop_api.DesktopApiTests.test_decision_lane_report_counts_market_radar_skip_reasons` passed after the stage-classification fix.

### 2026-05-12 - Market Radar Quality Gate V2

What changed:

- Root-caused the negative Market Radar sample: the lane was rewarding hot-feed visibility even when candidates had thin entry liquidity, collapsing 1-hour momentum, abnormal 1-hour volume versus liquidity, one-sided buy flow, or no social/site proof.
- Added a stricter paper-only Market Radar quality gate before any quote is spent.
- New blockers include `entry_liquidity_below_quality_gate`, `entry_market_cap_below_quality_gate`, `liquidity_market_cap_ratio_too_low`, `h1_volume_liquidity_anomaly`, `collapsing_h1_momentum`, `one_sided_buy_flow`, `one_sided_sell_flow`, `micro_tx_volume_anomaly`, `pair_too_fresh_for_market_radar`, `stale_pair_without_fresh_strength`, and `missing_social_or_site_quality_gate`.
- Dexscreener source bonus is capped to the strongest single source instead of stacking every source, so a candidate cannot pass just because it appeared in multiple Dex feeds.
- Kept RKC-style runners eligible: high liquidity, acceptable market cap, strong activity, non-collapsing short-term momentum, balanced buy/sell flow, and social/site evidence still pass.
- Added clean-room GitHub research inputs from SolClaw, Dexscreener meme analysis, Pump.fun token tracking, Pump.fun/Bonk.fun lifecycle bots, j33t-intel, MemeTrans, and SolRPDS.

Verification:

- Added failing tests first for the known Market Radar loser shape, one-sided buy-flow failures, missing social/site proof, too-fresh pairs, and stale resurrected pairs.
- `./trading_env/bin/python -m unittest tests.test_core_logic -k market_radar_quality_gate` passed 5 tests after implementation.
- `./trading_env/bin/python -m unittest tests.test_core_logic -k market_radar` passed 11 tests.
- `./trading_env/bin/python -m unittest tests.test_core_logic tests.test_desktop_api tests.test_market_checker` passed 264 tests.
- `npm test -- --run` passed 46 desktop React tests.
- `node tests/test_desktop_gui_chart.mjs` passed.

### 2026-05-12 - Market Radar Throughput And Skip Visibility

What changed:

- Fixed the Market Radar cycle bottleneck where the loop could inspect only the first `market_radar_max_candidates_per_cycle` rows and process zero candidates if those rows were already in cooldown.
- Added `market_radar_scan_candidates_per_cycle` so the lane can scan deeper through Dexscreener candidates while still capping actual evaluations, quote attempts, and paper entries.
- Added structured Market Radar decision evidence: open reason, skip reason, skip bucket, quote retryability, buy/sell route quote payloads, and visible action reasons.
- Quote cooldown/budget skips are now marked retryable and deferred briefly instead of putting the mint into the full six-hour candidate cooldown.
- Paper Review, Decision Outcome Analytics, React/Tauri Replay, and the static browser Replay view now surface Market Radar skip/open reason summaries.

Verification:

- Added failing tests first for scanning past recent candidates, visible quote-cooldown skips, structured score-skip reasons, Market Radar skip-reason API aggregation, and React decision formatting.
- `./trading_env/bin/python -m unittest tests.test_core_logic -k market_radar` passed 6 tests.
- `./trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests.test_decision_lane_report_counts_market_radar_skip_reasons tests.test_desktop_api.DesktopApiTests.test_paper_review_includes_decision_lane_report tests.test_desktop_api.DesktopApiTests.test_decision_outcome_analytics_groups_labeled_edges tests.test_desktop_api.DesktopApiTests.test_decisions_route_reads_canonical_decision_records` passed 4 tests.
- `npm test -- --run src/lib/decisions.test.ts src/components/DecisionLedger.test.tsx` passed 6 tests.
- `node tests/test_desktop_gui_chart.mjs` passed.

### 2026-05-12 - Market Radar Lane And Exploration Pause

What changed:

- Root-caused the missed RKC/Red Kitten Crew opportunity: the bot was wallet-first, so a token could run hard on Dexscreener/Pump-style feeds without ever entering our decision pipeline if no tracked wallet triggered it.
- Added a paper-only `market_radar` lane that polls Dexscreener latest profiles, latest boosts, and top boosts, filters Solana tokens, scores hot candidates by liquidity, market cap, 5-minute activity, 1-hour volume, buy ratio, momentum, source, and social/site presence, then records skip/entry decisions.
- Market Radar only checks Jupiter route quotes after a candidate is close to paper-entry quality, keeping the earlier Swap API pressure fix intact.
- Added `market_radar` metrics to Paper Review, Decision Lane Report, Decision Outcome Analytics, and runtime health so it can be judged separately from the main wallet strategy.
- Added a dedicated Market Radar quote budget and 5-minute quote cooldown so the new lane records weaker candidates without swap quotes and cannot recreate the Swap API pressure problem.
- Tightened the underperforming Exploration Lane: if the lane has at least five closed samples and both average PnL and win rate are poor, it auto-pauses instead of continuing to add negative paper trades.
- Raised the live runtime exploration thresholds back up after the negative sample and left live execution locked.
- GitHub research agent found the most relevant clean-room references for this path: `Flotapponnier/pulse-sniper`, `Ziondido/DexscreenerAPI`, `NadirAliOfficial/Solana-New-Pairs`, and `hcrypto7/rug_token_checker`.

Verification:

- `./trading_env/bin/python -m unittest tests.test_core_logic tests.test_desktop_api tests.test_market_checker` passed 257 tests after co-main regression coverage was added.
- `./trading_env/bin/python -m py_compile core/market_radar.py core/paper_exploration.py core/settings_manager.py infra/market_checker.py main.py core/scanner.py desktop_api.py` passed.

### 2026-05-12 - Market Radar Promoted To Co-Main Reporting

What changed:

- Promoted Market Radar from a purely experimental lane to a co-main paper strategy in reporting/readiness.
- Added combined `co_main` metrics for wallet-main plus Market Radar while preserving separate `main` and `market_radar` lane metrics for comparison.
- Decision Lane Report and Decision Outcome Analytics now include `co_main`, `main`, `market_radar`, `exploration`, and `protected_manual`.
- React/Tauri Paper Review now shows Co-Main Strategy, Wallet Main, Market Radar Co-Main, and Exploration Lane cards.
- Static desktop GUI Replay now shows the same co-main Paper Profitability Review and Market Radar filters at `http://127.0.0.1:8765/`.
- Live execution remains locked; this is a measurement/reporting promotion, not a live-buy promotion.

Verification:

- Added regression coverage for paper-review co-main metrics, decision-lane co-main aggregation, and decision-analytics co-main aggregation.
- `npm --prefix apps/desktop test -- --run` passed 45 tests after the Paper Review UI update.
- Browser verification confirmed the visible Replay panel shows Co-Main Strategy, Wallet Main, Market Radar Co-Main, Exploration Lane, and Decision Ledger Lanes.

Remaining:

- Let Market Radar collect enough closed samples before changing shared co-main thresholds.
- Add PumpPortal/Mobula-style streaming only if Dexscreener polling misses too many fast runners or creates too much lag.

### 2026-05-10 - Paper Sample Acceleration Lane

What changed:

- Added a paper-only route-failed observation mode inside Exploration Lane.
- Strong signals that fail buy/sell route checks can now open tiny `$5` exploration samples when `paper_exploration_route_failed_enabled` is on, while `live_should_trade` remains false and the sample is marked `route_observation_only`.
- Preserved main-strategy strictness: hard risk, market sanity, strategy guard, and confirmation blocks still prevent exploration samples.
- Paper trade reasons now distinguish `route_failed_observation` from normal `quote_ok` entries so route-failed samples do not pollute main-lane interpretation.
- Saved runtime controls for route-failed exploration thresholds: score `70`, edge `65`, size `$5`.
- Restarted the paper bot so the scanner is running the new acceleration logic; live execution stayed locked.

Verification:

- `./trading_env/bin/python -m unittest tests.test_core_logic.ScannerCandidateFilterTests.test_paper_exploration_lifts_safe_near_miss_as_separate_lane tests.test_core_logic.ScannerCandidateFilterTests.test_paper_exploration_does_not_override_hard_risk_block tests.test_core_logic.ScannerCandidateFilterTests.test_paper_exploration_does_not_override_exit_liquidity_block tests.test_core_logic.ScannerCandidateFilterTests.test_paper_exploration_can_sample_strong_route_failed_observation tests.test_core_logic.ScannerCandidateFilterTests.test_paper_exploration_route_failed_observation_requires_strong_signal tests.test_core_logic.SettingsManagerTests.test_save_settings_preserves_route_failed_exploration_controls`
- `./trading_env/bin/python -m unittest tests.test_core_logic tests.test_desktop_api`

### 2026-05-10 - Runtime Readiness Status Cleanup

What changed:

- Updated desktop runtime/readiness status handling so an old successful quote or expired Jupiter quote cooldown is treated as healthy idle state instead of a stale subsystem warning.
- Kept real quote failures visible: missing API key, current cooldown/429, HTTP errors, quote exceptions, or quote `last_error` still mark quotes unhealthy.
- Updated scanner freshness so a fresh scanner heartbeat with active wallet events is not failed only because route-backed swap ticks are quiet. It now reports `wallet_feed_quiet` with detail instead of failing the critical scanner component.
- Restarted the desktop API only; paper bot/scanner, watchdog, wallet discovery, and live execution settings were not loosened.
- Ran Reddit collector and rebuilt catalyst cards once to restore social freshness after it aged out.

Verification:

- Added regression tests for old `quote_ok`, expired quote cooldown, recent quote exception, and scanner events with quiet route-backed ticks.
- `./trading_env/bin/python -m unittest tests.test_desktop_api tests.test_core_logic tests.test_market_checker` passed 232 tests.
- `./trading_env/bin/python -m py_compile desktop_api.py` passed.
- `git diff --check` passed.
- `/api/readiness` now reports `overall: OK`, including `runtime_quotes: OK` and `runtime_scanner: OK`.
- `/api/social/freshness` reports `OK` after collector refresh.

### 2026-05-10 - Deep Watchdog RPC Pressure Control

What changed:

- Added watchdog-level cache and cooldown protection for deep Helius read calls: mint account inspection, owner token-balance lookup, holder largest-account checks, and prepared exit quote feasibility.
- Kept the fast open-position monitor separate from the slower deep watchdog path; this change only lowers repeated deep-check pressure and does not enable live execution.
- Added runtime counters for deep RPC cache hits, cooldown skips, and rate-limit cooldowns so operator status can show whether the watchdog is protecting upstream providers.
- Added scanner per-wallet backpressure using websocket subscription-to-wallet mapping so one noisy wallet cannot fill all scanner transaction tasks and crowd out other watched wallets.
- Restart targets are watchdog for deep-check cache/cooldown and paper bot/scanner for per-wallet backpressure. Live execution remains locked.

Verification:

- Added failing tests first for holder cache reuse, mint-inspection cooldown after `429`, wallet/mint scoped balance cache, and exit quote cache reuse.
- Added failing tests first for subscription ack wallet mapping and noisy-wallet queue isolation.
- `./trading_env/bin/python -m unittest tests.test_core_logic.WatchdogPressureTests` passed.
- `./trading_env/bin/python -m unittest tests.test_core_logic.SolanaRpcPressureTests` passed.
- `./trading_env/bin/python -m unittest tests.test_core_logic tests.test_desktop_api tests.test_market_checker` passed 228 tests.
- `./trading_env/bin/python -m py_compile infra/rpc_client.py core/rug_watchdog.py main.py desktop_api.py` passed.
- `git diff --check` passed.
- Restarted watchdog with 5-minute deep RPC cache/cooldown settings. Runtime shows watchdog fresh with deep cache hits and no active deep RPC cooldown.
- Restarted paper bot/scanner with `MEMETRADER_MAX_INFLIGHT_PER_WALLET=40`. Runtime recovered from scanner stale/fail to `online`; scanner active tasks dropped from the 2500 backlog ceiling into normal double digits and route-backed swap ticks became fresh again.
- Ran the Reddit collector and rebuilt catalyst cards once. `/api/social/freshness` returned `OK` with manual imports, Reddit collector, and catalyst cards fresh.

Remaining:

- Watch Helius holder/mint request volume over the next 1-4 hours and confirm the dashboard stays near the improved success rate.
- Watch per-wallet backlog drops. Drops are expected for noisy wallets, but scanner active tasks should stay well below the global backlog ceiling.
- Continue collecting paper outcomes; provider pressure control improves runtime durability but does not replace the 50 closed main-lane trade requirement.

### 2026-05-10 - Provider Pressure Control

What changed:

- Added Jupiter Price API pressure control: longer market cache, provider cooldown after `429`, per-provider request serialization, and safer Dexscreener fallback behavior.
- Restarted the paper bot/watchdog with lower-pressure market settings while keeping live execution locked.
- Added Helius `getTransaction` pressure control in the scanner runtime: per-signature cache, same-signature in-flight dedupe, max request pacing, backlog drop guard, and runtime counters for transaction cache/fetch behavior.
- Restarted the paper bot/scanner with `MEMETRADER_GET_TRANSACTION_MAX_RPS=8`, 5-minute transaction cache, and backlog protection.

Verification:

- Jupiter dashboard improved from roughly 63% Price API error rate to roughly 99.5% success / 0.45% error in the last-hour view after pressure control.
- Live runtime reports bot, websocket, scanner, wallet feed, fast open-position monitor, watchdog, wallet discovery, and Reddit collector fresh.
- Helius transaction limiter is active in runtime: `transaction_min_interval=0.125`, transaction cache filling, and `getTransaction` status 200.
- `./trading_env/bin/python -m unittest tests.test_core_logic tests.test_desktop_api tests.test_market_checker` passed 222 tests.
- `./trading_env/bin/python -m py_compile infra/rpc_client.py main.py core/scanner.py infra/market_checker.py core/fast_position_monitor.py core/rug_watchdog.py execution/jupiter_quote.py` passed.
- `git diff --check` passed.

Remaining:

- Watch the Helius dashboard over the next 1-4 hours. Requests should flatten below prior burst levels; if not, lower `MEMETRADER_GET_TRANSACTION_MAX_RPS` from 8 toward 5 and add log-level prefilters before transaction fetch.
- Helius holder/deep watchdog checks now have their own watchdog cache/cooldown layer. The next validation is live dashboard observation, not another backend pressure feature.

### 2026-05-10 - Fast Monitor, Decision Analytics, Reddit Hygiene

What changed:

- Added a separate fast open-position monitor path that performs cheap quote/liquidity checks for open paper trades and updates paper PnL/snapshots through the existing `PaperTrader.update_price()` lifecycle.
- Kept the deep watchdog separate for slower mint inspection, holder checks, wallet balances, prepared exits, and quote feasibility.
- Added `/api/decision-analytics` as a read-only decision outcome view over canonical SQLite decision records, grouping social catalyst, wallet-only, quote-failed, hard-risk, lane, and overall outcomes.
- Added a social expansion gate: broader social sources remain blocked until labeled social outcomes are large enough and outperform non-social decisions.
- Tightened Reddit collector hygiene with duplicate detection, noisy-author/thread rejection, explicit rejected/duplicate counts, and research-only source expansion metadata.
- Wired decision outcome analytics into the Replay/Paper Review surface in the React/Tauri GUI.

Next validation target:

1. Run the fast monitor during an active paper session and confirm open trades receive fresh snapshots without invoking deep watchdog checks.
2. Watch Reddit collector duplicate/noise counts over multiple scheduled runs.
3. Use decision analytics only after enough labeled closed outcomes exist; do not add Twitter/Telegram/etc. as scoring inputs until the social expansion gate is earned.

### 2026-05-09 - Hourly Reddit Collector Automation

What changed:

- Created active Codex automation `reddit-social-collector`.
- It runs the standalone Reddit social collector hourly against the local workspace, rebuilds catalyst cards after collection, verifies social freshness, and reports counts/errors.
- The automation prompt explicitly keeps live execution locked and does not enable trading or modify execution settings.
- Current local social freshness remains `OK`: manual/social events fresh, catalyst cards fresh, and Reddit collector fresh.

Verification:

- Confirmed `/api/social/freshness` helper reports `overall: OK` with 3 fresh rows.

### 2026-05-09 - Paper Outcome Decision Backfill

Changed files:

- `utils/sync_state_to_sqlite.py`
- `tests/test_core_logic.py`
- `WORK_LOG.md`
- `research/PROJECT_STATE.md`

What changed:

- Extended the SQLite sync utility so paper trades with `signal_metadata.decision_id` backfill `decision_records` action/result fields.
- Backfill covers open, closed, and failed paper trades, including lane, position size, trade status, PnL, PnL percent, and paper outcome details.
- Real local sync still found all 13 current paper trades missing decision IDs, so no historical decision outcomes could be backfilled. Future scanner-created trades carry `decision_id`, so new paper lifecycle events should populate the lane report.

Verification:

- `./trading_env/bin/python -m unittest tests.test_core_logic.PositionCockpitTests.test_trade_sync_backfills_decision_results_from_paper_trade_metadata`
- `./trading_env/bin/python utils/sync_state_to_sqlite.py`

### 2026-05-09 - Decision Ledger Lane Report

Changed files:

- `desktop_api.py`
- `apps/desktop/src/App.tsx`
- `apps/desktop/src/styles.css`
- `tests/test_desktop_api.py`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`
- `research/PROJECT_STATE.md`
- `research/DATA_SOURCE_MAP.md`

What changed:

- Added `decision_lane_report` to `/api/paper-review`, sourced from SQLite `decision_records`.
- The report summarizes main, exploration, and protected/manual lanes by candidate decisions, paper attempts, opens, skips, quote failures, hard blocks, social/wallet confirmation, open/closed/failed trades, PnL, win rate, and sample readiness.
- Protected/manual currently combines protected watchlist count with any protected/manual decision records.
- Lane normalization now prefers explicit non-main lanes from result paper outcome, action payload, or top-level decision row before falling back to main.
- Native Paper Review now shows a compact Decision Ledger Lanes grid beside the existing paper-trade lane metrics.

Verification:

- `./trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests.test_decision_lane_report_normalizes_protected_and_result_lanes tests.test_desktop_api.DesktopApiTests.test_decision_lane_report_summarizes_decision_record_outcomes tests.test_desktop_api.DesktopApiTests.test_paper_review_includes_decision_lane_report`
- `npm run check`
- `python3 -m py_compile desktop_api.py`

### 2026-05-09 - Reddit Social Collector Foundation

Changed files:

- `social/reddit_collector.py`
- `social/social_signal.py`
- `tests/test_core_logic.py`
- `tests/test_desktop_api.py`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`
- `research/PROJECT_STATE.md`
- `research/DATA_SOURCE_MAP.md`

What changed:

- Added a standalone Reddit collector that reads subreddit JSON listings, normalizes posts into local social evidence, and does not trigger trades.
- Avoided new dependencies after `requests` import proved blocking in this environment; the collector uses the standard library HTTP client plus injectable fetchers for tests.
- Reddit collector status now writes into `runtime_status.social_collectors.reddit`, which the existing `/api/social/freshness` contract already displays.
- Fixed social state compatibility: `SocialSignalEngine` now reads both canonical `events` and legacy `signals`; new manual and Reddit writes use canonical `events`.
- Added tests for Reddit post mapping, collector storage, manual-event preservation, social matching from `events`, and runtime social-collector freshness.
- First live standalone observation pass fetched 6 Reddit posts from `SolanaMemeCoins` and `memecoins`, stored them as local evidence, kept `trade_triggered: false`, rebuilt 3 catalyst cards, and moved social freshness to `OK`.

Verification:

- `./trading_env/bin/python -m unittest tests.test_core_logic.SocialSignalTests.test_social_engine_matches_canonical_events_rows tests.test_core_logic.SocialSignalTests.test_social_signal_extracts_ticker_mint_and_sentiment tests.test_core_logic.SocialSignalTests.test_exact_mint_matches_without_market_metadata tests.test_core_logic.SocialSignalTests.test_malformed_social_rows_do_not_break_active_signals tests.test_core_logic.PositionCockpitTests.test_reddit_collector_preserves_existing_canonical_events tests.test_core_logic.PositionCockpitTests.test_reddit_collector_stores_signals_and_status_without_trade_trigger`
- `./trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests.test_social_freshness_reads_runtime_social_collectors_dict tests.test_desktop_api.DesktopApiTests.test_social_freshness_payload_flags_stale_sources_and_collectors`
- `./trading_env/bin/python -m core.catalyst_cards`

### 2026-05-09 - Scanner Holder/Cluster Risk Decision Wiring

Changed files:

- `core/scanner.py`
- `core/settings_manager.py`
- `tests/test_core_logic.py`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`
- `research/PROJECT_STATE.md`
- `research/DATA_SOURCE_MAP.md`

What changed:

- Added a bounded scanner holder check using `getTokenLargestAccounts` and the existing `HolderConcentrationAnalyzer`.
- Gated holder RPC checks to quote-worthy or near-entry candidates so low-prescore skips do not slow the hot path.
- Holder `DANGER` now elevates the candidate risk to a hard block before paper entry; holder `WARNING` elevates risk context without bypassing quote or safety checks.
- Live decision records now receive holder concentration risk, warnings, metrics, and top-holder percentages through the canonical decision ledger.
- Linked-wallet graph risk is explicitly recorded as `NOT_CHECKED` with observed wallet-cluster context until a real linkage source exists.
- Added settings defaults for `scanner_holder_check_enabled` and `scanner_holder_check_timeout_seconds`.

Verification:

- `./trading_env/bin/python -m unittest tests.test_core_logic.ScannerRuntimeTests`
- `python3 -m py_compile core/scanner.py core/settings_manager.py`

### 2026-05-09 - Canonical Read Path Source Contracts

Changed files:

- `desktop_api.py`
- `tests/test_desktop_api.py`
- `core/storage.py`
- `utils/sync_state_to_sqlite.py`
- `tests/test_core_logic.py`
- `apps/desktop/src/App.tsx`
- `apps/desktop/src/components/TokenDetail.tsx`
- `apps/desktop/src/components/TokenDetail.test.tsx`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/lib/trades.ts`
- `apps/desktop/src/lib/trades.test.ts`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`
- `research/PROJECT_STATE.md`
- `research/DATA_SOURCE_MAP.md`

What changed:

- Migrated `/api/trades` and shared paper-trade state to prefer SQLite `trades` once SQLite and JSON pass bucket/key parity.
- Added a JSON fallback for trades when SQLite is empty or parity fails, with `mirror_warning`, `sqlite_counts`, and `json_counts`.
- Fixed SQLite trade mirror writes so failed rows are normalized as `failed`, terminal rows remove stale open mirror rows, and rebuilds preserve full payload JSON.
- Added a `utils/sync_state_to_sqlite.py --rebuild-trades` path and rebuilt the local SQLite `trades` table from `data/paper_trades.json`; live parity is now open 1, closed 10, failed 2.
- Migrated `/api/alerts` to prefer SQLite `alerts` with live-state fallback and summary-column fallback for malformed alert payload JSON.
- Added explicit source metadata to `/api/tokens/{mint}/snapshots`: `sqlite_token_snapshots`, `data/memetrader.db:token_snapshots`, and the related source contract.
- Added selected-position detail source metadata: JSON paper/manual position source, SQLite snapshot source, social/catalyst/wallet source contract, and a mixed-market-field warning.
- Added source contracts for wallet list/detail payloads and social payloads without migrating those JSON-first readers yet.
- React/Tauri Portfolio now shows the paper-trade source in the Portfolio header.
- React/Tauri selected-token Snapshot Feed now shows the SQLite snapshot source.
- React/Tauri Details now shows a Data Sources card for selected-token source contracts and mixed-field warnings.
- Mapped the remaining JSON/SQLite inconsistencies with a read-only helper pass. Full source-of-truth migration remains an Extra High task because it touches writers, retention, schema, backfill, and analytics.

Verification:

- Added failing tests first for trade and snapshot source contracts.
- Added failing tests first for the alert source contract and route payload.
- Added failing tests first for selected-position source contracts and the Details Data Sources card.
- Added failing tests first for SQLite-first trades, trade parity fallback, legacy failed-row bucketing, SQLite-first alerts, malformed alert payload fallback, wallet contracts, and social contracts.
- `./trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests.test_trades_payload_prefers_sqlite_source_of_truth tests.test_desktop_api.DesktopApiTests.test_trades_payload_falls_back_to_json_when_sqlite_parity_fails tests.test_desktop_api.DesktopApiTests.test_legacy_failed_sqlite_trade_rows_are_not_bucketed_as_open`
- `./trading_env/bin/python -m unittest tests.test_core_logic.PositionCockpitTests.test_event_store_normalizes_failed_trade_rows_for_sqlite_mirror tests.test_core_logic.PositionCockpitTests.test_event_store_terminal_trade_removes_stale_open_mirror_row tests.test_core_logic.PositionCockpitTests.test_trade_sync_rebuilds_sqlite_trades_to_match_json_buckets`
- `./trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests.test_alerts_payload_prefers_sqlite_source_of_truth tests.test_desktop_api.DesktopApiTests.test_alerts_payload_falls_back_to_live_state_when_sqlite_empty tests.test_desktop_api.DesktopApiTests.test_fetch_alert_rows_falls_back_to_summary_columns_when_payload_is_malformed tests.test_desktop_api.DesktopApiTests.test_alerts_route_uses_alerts_source_contract`
- `./trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests.test_position_detail_declares_mixed_json_and_sqlite_sources tests.test_desktop_api.DesktopApiTests.test_position_detail_declares_manual_watchlist_source tests.test_desktop_api.DesktopApiTests.test_position_detail_keeps_source_contract_without_selected_position`
- `./trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests.test_social_payload_declares_json_source_and_decision_evidence_boundary tests.test_desktop_api.DesktopApiTests.test_wallets_payload_merges_labels_and_performance tests.test_desktop_api.DesktopApiTests.test_wallet_detail_payload_includes_signals_and_paper_trades`
- `npm test -- --run src/lib/trades.test.ts`
- `npm test -- --run src/components/TokenDetail.test.tsx`
- `./trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests`
- `npm test`
- `python3 -m py_compile desktop_api.py`
- `npm run check`
- `npm run build:web`
- `git diff --check`

### 2026-05-09 - Social Collector Freshness Indicators

Changed files:

- `desktop_api.py`
- `tests/test_desktop_api.py`
- `apps/desktop/src/App.tsx`
- `apps/desktop/src/components/SocialFreshnessPanel.tsx`
- `apps/desktop/src/components/SocialFreshnessPanel.test.tsx`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/lib/api.test.ts`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`
- `research/PROJECT_STATE.md`
- `research/SOCIAL_CATALYST_AUTOMATION_WORKFLOW.md`

What changed:

- Added read-only `/api/social/freshness` for manual social imports, catalyst cards, and future automated collector status.
- Social freshness rows now report status, age, event count, last success, last error, enabled state, and freshness thresholds.
- React/Tauri Signals and System views now show Social Freshness without trade-action language.
- The API also embeds social freshness inside `/api/freshness` for system-level source health.

Verification:

- `./trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests.test_social_freshness_payload_flags_stale_sources_and_collectors tests.test_desktop_api.DesktopApiTests.test_social_freshness_route_is_read_only tests.test_desktop_api.DesktopApiTests.test_social_endpoint_supports_legacy_signals_key`
- `npm test -- --run src/lib/api.test.ts src/components/SocialFreshnessPanel.test.tsx`
- `./trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests`
- `npm test`
- `python3 -m py_compile desktop_api.py`
- `npm run check`
- `npm run build:web`
- `git diff --check`

### 2026-05-09 - React/Tauri Rich Decision Detail

Changed files:

- `apps/desktop/src/components/DecisionLedger.tsx`
- `apps/desktop/src/components/DecisionLedger.test.tsx`
- `apps/desktop/src/lib/decisions.ts`
- `apps/desktop/src/lib/decisions.test.ts`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`
- `research/PROJECT_STATE.md`
- `research/SOCIAL_CATALYST_AUTOMATION_WORKFLOW.md`

What changed:

- React/Tauri Decision Detail now shows the richer backend evidence already attached to decisions.
- Added detail cards for catalyst evidence, route feasibility, holder/cluster risk, market context, and paper outcome.
- Kept row density unchanged so the ledger remains scannable; the expanded evidence stays in the selected-decision drilldown.
- Added formatter and component render tests for the new evidence sections.

Verification:

- `npm test -- --run src/lib/decisions.test.ts src/components/DecisionLedger.test.tsx`
- `npm test`
- `npm run check`
- `npm run build:web`
- `git diff --check`

### 2026-05-09 - Backend Decision Evidence Fields

Changed files:

- `core/decision_ledger.py`
- `core/scanner.py`
- `tests/test_core_logic.py`
- `tests/test_desktop_api.py`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`
- `research/PROJECT_STATE.md`
- `research/SOCIAL_CATALYST_AUTOMATION_WORKFLOW.md`

What changed:

- Extended canonical backend decision payloads with structured social/catalyst evidence, market context, holder/cluster risk, and route-feasibility sections.
- Added paper-outcome detail to decision results, including lane, exploration state, prices, liquidity, size, fees, and entry/exit reasons when available.
- Scanner decision writes now include sanitized Jupiter quote route details such as route count, mints, raw amounts, slippage, max impact, and route-plan summary.
- Broad crypto/stablecoin inputs are now documented as context-only risk signals, not a product expansion into non-memecoin trading.

Verification:

- `./trading_env/bin/python -m unittest tests.test_core_logic.PositionCockpitTests.test_decision_record_preserves_extended_evidence_fields tests.test_core_logic.PositionCockpitTests.test_trade_result_preserves_paper_outcome_details`
- `./trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests.test_decisions_route_preserves_extended_decision_evidence`
- `python3 -m py_compile core/decision_ledger.py core/scanner.py`

### 2026-05-09 - React/Tauri Replay Decision Ledger Parity

Changed files:

- `apps/desktop/src/App.tsx`
- `apps/desktop/src/components/DecisionLedger.tsx`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/lib/api.test.ts`
- `apps/desktop/src/lib/decisions.ts`
- `apps/desktop/src/lib/decisions.test.ts`
- `apps/desktop/src/styles.css`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`

What changed:

- Added React/Tauri support for the canonical `/api/decisions` ledger.
- Added a dedicated native Decision Ledger panel in the Replay tab.
- Replay now prefers canonical decision records when present and falls back to paper-trade replay only when decision records are unavailable.
- Added decision filters matching the static desktop view: all, bought, skipped, exploration, quote failed, hard risk, social, and wallet.
- Added selectable decision rows and rich detail showing lane, score, threshold, risk, buy/sell quote reason, action reason, wallet evidence, social match, risk notes, and score notes.
- Added typed decision helper functions and tests for filter parity, selection fallback, quote badges, and wallet summaries.

Verification:

- `npm test -- --run src/lib/decisions.test.ts src/lib/api.test.ts`
- `npm run check`
- `npm test`
- `python3 -m py_compile desktop_api.py core/decision_ledger.py core/storage.py`
- `npm run build:web`

Remaining:

- Backend decision evidence fields are now complete in the later work-log entry above.
- Next GUI pass should expose those fields before the first automated Reddit collector is wired in.

### 2026-05-09 - Automated Social Catalyst Workflow Added To Roadmap

Changed files:

- `WORK_LOG.md`
- `AGENT_WORKFLOW.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `research/OPEN_SOURCE_REPO_REVIEW.md`
- `research/SOCIAL_CATALYST_AUTOMATION_WORKFLOW.md`

What changed:

- Reviewed the current work log, build plan, data source map, social tracker plan, decision ledger direction, and open-source research.
- Added a dedicated social-catalyst automation workflow that folds in Meme Radar, async Reddit ingestion, official X ingestion, Telegram/Discord, evidence capture, and Solana launch-discovery references.
- Reframed the next workflow as Decision Ledger first, automated social ingestion second, and social-to-price validation third.
- Kept the safety rule explicit: social evidence can raise priority and improve explanations, but cannot bypass wallet confirmation, risk gates, quote feasibility, lane separation, or live execution locks.

Verification:

- Documentation-only update; no runtime code changed.
- Cross-checked against the active Phase 2 / Phase 7 decision-ledger roadmap and current manual social import implementation.

Remaining:

- React/Tauri Replay Decision Ledger parity is now complete in the later work-log entry above.
- Add decision-record fields needed for social/catalyst evidence before adding the first Reddit collector.

### 2026-05-09 - Runtime SQLite Store Rebuilt

Changed files:

- `WORK_LOG.md`

Runtime state actions:

- Stopped active DB writers before touching the SQLite files:
  - paper bot,
  - protection watchdog,
  - wallet discovery scheduler,
  - desktop API.
- Preserved the unreadable runtime SQLite files under `data/archives/runtime_db_20260509_160203/`.
- Created a fresh `data/memetrader.db` using the current `EventStore` schema.
- Backfilled safely recoverable JSON state into SQLite:
  - paper trades,
  - live events/alerts,
  - manual watchlist.
- Restarted the desktop API, paper bot, protection watchdog, and wallet discovery scheduler.

Verification:

- `PRAGMA integrity_check` returns `ok`.
- Desktop API `/api/readiness` reports SQLite store OK.
- Desktop API `/api/decisions` is available.
- Runtime readiness reports OK after forcing one wallet-discovery cycle.
- Rebuilt SQLite counts after restart:
  - events: 1249,
  - alerts: 42,
  - trades: 13,
  - watchlist: 1,
  - token snapshots: 285,
  - swap ticks: 774,
  - decision records: 10.

Remaining:

- The old SQLite file was not readable, so historical token snapshots, swap ticks, and decision records inside that old file were not recovered.
- The decision ledger will repopulate from new scanner decisions going forward.
- Wallet discovery runs on a 300-second interval, so it can briefly look stale between scheduled cycles if the freshness threshold is tighter than the scheduler interval.

### 2026-05-09 - Decision Ledger Filters And Detail

Changed files:

- `desktop_api.py`
- `desktop_gui/assets/app.js`
- `desktop_gui/assets/render.js`
- `desktop_gui/assets/styles.css`
- `tests/test_desktop_api.py`
- `tests/test_core_logic.py`
- `tests/test_desktop_gui_chart.mjs`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`

What changed:

- Added read-only API filtering for `/api/decisions`, including quote-failed and lane filters.
- Added first-pass Decision Ledger filters in the static desktop Replay tab: all, bought, skipped, exploration, quote failed, hard risk, social, and wallet.
- Added selected-decision detail showing lane, score, threshold, risk, buy/sell quote reason, action reason, wallets, social match, risk notes, and score notes.
- Decision rows are now clickable and keep the selected decision highlighted.
- Isolated core logic tests from the developer-machine runtime database so local data corruption or non-SQLite runtime files do not break unit tests.

Verification:

- Added failing UI/API tests first for decision filters and selected detail, then implemented the behavior.
- Targeted desktop API decision-filter tests passed.
- Static desktop GUI test passed.
- Full Python suite passed from the repo root with 162 tests.
- JavaScript static syntax/chart tests passed.
- React/Tauri type check passed.

Operational note:

- The local runtime file `data/memetrader.db` is not currently a readable SQLite database. I did not delete or overwrite it. Tests are now isolated from that runtime file, and the runtime DB should be backed up/renamed/rebuilt deliberately before relying on SQLite panels against that local file.

Remaining:

- Add richer decision detail to the React/Tauri shell.
- Add backfill for older scanner snapshots and paper trades if we want historical decisions visible immediately.

### 2026-05-09 - Canonical Decision Ledger Foundation

Changed files:

- `core/decision_ledger.py`
- `core/storage.py`
- `core/scanner.py`
- `paper_trader.py`
- `desktop_api.py`
- `desktop_gui/assets/api.js`
- `desktop_gui/assets/app.js`
- `desktop_gui/assets/render.js`
- `desktop_gui/assets/styles.css`
- `tests/test_core_logic.py`
- `tests/test_desktop_api.py`
- `AGENT_WORKFLOW.md`
- `docs/OWNERS_MANUAL.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`

What changed:

- Tightened the roadmap around measurable edge, canonical state, and the fast-monitor vs deep-watchdog split.
- Added the first SQLite-backed `decision_records` ledger for candidate decisions.
- Added `core/decision_ledger.py` helpers for candidate decision records and paper-trade outcome updates.
- Scanner signal evaluation now creates a decision record and passes `decision_id` into paper-trade metadata when a paper open is attempted.
- Scanner runtime precheck skips update the decision action as `runtime_skip`.
- Paper-trade snapshots update the linked decision result for failed opens, opened trades, monitor updates, partial exits, and closed exits.
- Desktop API now exposes read-only `/api/decisions`.
- Static desktop Replay tab now shows the canonical Decision Ledger when decision records exist.

Verification:

- Targeted storage/decision tests passed.
- Targeted desktop API decision-route test passed.
- `py_compile` passed for the changed Python modules.

Remaining:

- Add richer filters and detail drilldown for decision records.
- Backfill existing scanner/paper history into decision records if needed.
- Continue separating fast open-position monitoring from slower deep watchdog inspection.

### 2026-05-09 - Repo Sync And Header Metric Text Fix

Changed files:

- `.gitignore`
- `desktop_gui/assets/styles.css`
- `apps/desktop/src/styles.css`
- `WORK_LOG.md`

What changed:

- Committed and pushed the current local project snapshot to `origin/phase6-protection-exits` so GitHub has the current working branch.
- Tightened ignore rules so local runtime files, live-state temp files, database side files, and archive state are not accidentally staged.
- Fixed token-header metric text overflow so Liquidity, Risk, and other metric values cannot overlap in the served desktop GUI or the React/Tauri GUI.

Verification:

- Secret scan checked for committed API/private key material in project files.
- `git diff --check`
- `node --check desktop_gui/assets/render.js && node --check desktop_gui/assets/app.js && node --check desktop_gui/assets/format.js`

Remaining:

- Continue the broader chart-rendering and GUI cleanup pass after confirming the header no longer overlaps in the running app.

### 2026-05-08 - Trade-Stream Candle Foundation

Changed files:

- `core/storage.py`
- `desktop_api.py`
- `desktop_gui/assets/render.js`
- `tests/test_core_logic.py`
- `tests/test_desktop_api.py`
- `tests/test_desktop_gui_chart.mjs`
- `docs/OWNERS_MANUAL.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`

What changed:

- Added SQLite `swap_ticks` storage with time, mint, signature, wallet, side, price, market cap, liquidity, token amount, SOL amount, source, and raw payload.
- Added storage helpers to insert and read swap ticks.
- `/api/candles` now checks for swap ticks first. When ticks exist for a mint, candles are built from tick rows and labeled `sample_kind=swap_tick` with `trade_stream_active=true`.
- When ticks do not exist, `/api/candles` keeps the existing sampled-snapshot fallback and still labels it as `sampled_quote`.
- Market Cap chart mode now estimates pump-token market cap from price when snapshots lack an explicit market-cap field, so watchdog-only pump tokens do not render as blank charts.
- Desktop chart rendering now drops malformed OHLC rows before passing data to `lightweight-charts`.
- SQLite readiness counts now include `swap_ticks`.
- Scanner wallet events now preserve transaction signature, block time, and native SOL balance delta when available.
- Scanner processing writes a conservative `wallet_event_market_enriched` swap tick when a wallet event has signature, token amount, SOL amount, and market enrichment with a valid USD price.

Verification:

- Added failing tests first for swap-tick storage, API tick-candle preference, and GUI malformed-OHLC filtering.
- Added a failing test for pump-token market-cap fallback from price.
- Added failing tests for scanner transaction metadata preservation and market-enriched tick writes.
- `trading_env/bin/python -m unittest tests.test_core_logic.PositionCockpitTests.test_event_store_records_swap_ticks_for_trade_stream_candles tests.test_core_logic.PositionCockpitTests.test_build_candles_groups_snapshots tests.test_core_logic.PositionCockpitTests.test_build_candles_can_infer_sparse_opens_from_previous_close tests.test_core_logic.PositionCockpitTests.test_build_candles_respects_requested_output_limit`
- `trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests.test_candles_payload_is_json_serializable tests.test_desktop_api.DesktopApiTests.test_candles_payload_can_use_liquidity_metric tests.test_desktop_api.DesktopApiTests.test_candles_payload_can_use_market_cap_metric tests.test_desktop_api.DesktopApiTests.test_market_cap_candles_infer_sparse_opens_from_previous_close tests.test_desktop_api.DesktopApiTests.test_candles_payload_reports_sampled_quote_quality tests.test_desktop_api.DesktopApiTests.test_candles_payload_prefers_swap_ticks_when_available tests.test_desktop_api.DesktopApiTests.test_invalid_candle_metric_falls_back_to_price`
- `node tests/test_desktop_gui_chart.mjs`
- `trading_env/bin/python -m py_compile core/storage.py core/position_cockpit.py desktop_api.py`
- `trading_env/bin/python -m unittest discover`
- `node --check desktop_gui/assets/api.js && node --check desktop_gui/assets/app.js && node --check desktop_gui/assets/render.js && node tests/test_desktop_gui_chart.mjs`

Remaining:

- Current tick rows are conservative wallet-event ticks enriched with current market price. The next upgrade is a deeper DEX instruction parser that derives exact execution price from transaction route economics instead of market enrichment.

### 2026-05-08 - Desktop API Session Ownership Stabilization

Changed files:

- `desktop_api.py`
- `apps/desktop/src-tauri/src/main.rs`
- `Start MemeTraderPro Desktop.command`
- `tests/test_desktop_api.py`
- `docs/OWNERS_MANUAL.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`

What changed:

- Desktop API health now reports the running process id and session start time.
- The desktop API session file now stores token, process id, and start time using an atomic write.
- The Tauri shell only trusts a saved API token when the session file matches the currently running API process.
- The fallback double-click command now reuses an already-running healthy API instead of starting a second API on the same port.
- The browser fallback no longer depends on a visible URL token; the local static app receives the session token from the served page when the API owns the session.

Verification:

- `trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests.test_session_file_records_running_process_identity tests.test_desktop_api.DesktopApiTests.test_health_route_reports_execution_locked_metadata_mode tests.test_desktop_api.DesktopApiTests.test_static_index_embeds_session_token_for_same_origin_app`
- `trading_env/bin/python -m py_compile desktop_api.py`
- `bash -n 'Start MemeTraderPro Desktop.command'`
- `cd apps/desktop/src-tauri && cargo test`

Remaining:

- Add a stronger runtime supervisor that can start/stop backend loops cleanly, not only the desktop API.
- Build the real trade-stream candle pipeline for Axiom-like candles from swap ticks instead of sampled quotes.

### 2026-05-08 - Review Remediation: Desktop Token And Wallet Apply Lock

Changed files:

- `desktop_api.py`
- `utils/apply_wallet_review.py`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/lib/api.test.ts`
- `apps/desktop/src/App.tsx`
- `apps/desktop/src-tauri/src/main.rs`
- `Start MemeTraderPro Desktop.command`
- `tests/test_core_logic.py`
- `tests/test_desktop_api.py`
- `apps/desktop/README.md`
- `docs/OWNERS_MANUAL.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`

What changed:

- Desktop metadata POST routes now require a session token when the desktop API is launched with one.
- The Tauri shell generates a token, launches the Python desktop API with that token in the environment, and passes the token to the React app for metadata POST headers.
- The fallback double-click command also launches the API with a token and opens the browser with the token in the local URL.
- The API reports `metadata_mutations_require_token=true` when protected.
- Wallet-list apply now uses a single apply lock and UUID-backed high-resolution stamps to reduce concurrent apply/backup/audit races.
- Wallet-list apply audit appends now use locked JSON updates.
- The desktop API was restarted with token protection active, without exposing the token in process arguments.

Verification:

- Added failing tests first for metadata POST token enforcement and wallet apply locking/stamp uniqueness.
- `trading_env/bin/python -m unittest discover`
- `trading_env/bin/python -m py_compile desktop_api.py utils/apply_wallet_review.py core/json_store.py`
- `npm run check`
- `npm test -- --run`
- `cargo test`
- `npm run build`
- Runtime check confirmed `/api/health` reports `metadata_mutations_require_token=true`.
- Runtime check confirmed missing-token POST returns `401` and tokened POST reaches normal validation.

Remaining:

- Broad scanner/API module splitting remains a maintainability task, not a current runtime blocker.

### 2026-05-08 - Review Remediation: Exploration And Wallet Safety

Changed files:

- `core/paper_exploration.py`
- `core/scanner.py`
- `paper_trader.py`
- `core/settings_manager.py`
- `core/wallet_list_apply.py`
- `desktop_api.py`
- `infra/rpc_client.py`
- `main.py`
- `apps/desktop/src/App.tsx`
- `tests/test_core_logic.py`
- `tests/test_desktop_api.py`
- `WORK_LOG.md`

What changed:

- Paper Exploration Mode can no longer reopen candidates blocked by confirmation or strategy guard.
- Exploration trades now carry `live_should_trade=false` so paper exploration cannot be mistaken for future live eligibility.
- Paper review readiness is now main-lane specific; exploration readiness is reported separately.
- Wallet promotions now require both paper-watch evidence and a promotion lifecycle recommendation.
- Failed paper buys now record `status=failed` and `failure_reason`.
- Invalid paper trades are quarantined before partial-sell or stop-loss logic can mutate them.
- Scanner signal evaluation is serialized per mint and queues a re-check if another wallet hit arrives mid-evaluation.
- Scanner now uses the configured Jupiter pre-score threshold.
- Tracked wallets take precedence over overlapping paper-watch membership.
- Settings save now parses string booleans correctly.
- `infra.rpc_client` and `main.py` are safer to import in tests without live API-key or event-loop side effects.
- Native selected-token paper lifecycle now looks up trades by selected mint, even when the token is not an open position.

Verification:

- Added failing tests first for the key review issues, then fixed them.
- `trading_env/bin/python -m unittest discover`
- `trading_env/bin/python -m py_compile core/paper_exploration.py core/scanner.py paper_trader.py core/settings_manager.py core/wallet_list_apply.py desktop_api.py infra/rpc_client.py main.py`
- `npm run check`
- `npm test -- --run`

Remaining:

- Add launcher-issued API token / stronger loopback mutation authentication.
- Split large scanner and desktop API modules after the current behavior stabilizes.
- Consider a transactional lock around the multi-file wallet-list apply operation.

### 2026-05-08 - Paper Exploration Lane

Changed files:

- `core/paper_exploration.py`
- `core/scanner.py`
- `paper_trader.py`
- `core/settings_manager.py`
- `desktop_api.py`
- `tests/test_core_logic.py`
- `tests/test_desktop_api.py`
- `apps/desktop/src/App.tsx`
- `apps/desktop/src/styles.css`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `docs/OWNERS_MANUAL.md`
- `WORK_LOG.md`

What changed:

- Added a separate paper-only Exploration Lane for safe near-miss candidates.
- The lane can only lift candidates after hard risk blocks, market sanity blocks, buy quote failures, sell/exit quote failures, and zero-size results have been rejected.
- Exploration trades use a smaller simulated size and are tagged with `paper_lane=exploration`.
- Paper Profitability Review now separates Main Strategy and Exploration Lane metrics.
- Settings now include exploration enablement, near-miss score threshold, edge-score threshold, and exploration size.

Verification:

- Added failing tests first for exploration lift/block behavior, trade lane recording, and review lane metrics.
- `trading_env/bin/python -m unittest tests.test_core_logic.ScannerCandidateFilterTests.test_paper_exploration_lifts_safe_near_miss_as_separate_lane tests.test_core_logic.ScannerCandidateFilterTests.test_paper_exploration_does_not_override_hard_risk_block tests.test_core_logic.ScannerCandidateFilterTests.test_paper_exploration_does_not_override_exit_liquidity_block tests.test_core_logic.PaperTraderPnlTests.test_open_trade_records_paper_lane_for_exploration tests.test_desktop_api.DesktopApiTests.test_paper_review_payload_reports_readiness_and_trade_quality`
- `trading_env/bin/python -m py_compile core/paper_exploration.py core/scanner.py paper_trader.py core/settings_manager.py desktop_api.py`
- `npm run check`

Remaining:

- Run long enough for at least 50 closed exploration trades, with 100-150 preferred before promotion/demotion tuning.
- Keep main strategy metrics separate when judging whether confirmation mode is profitable.

### 2026-05-08 - Paper Profitability Review Panel

Changed files:

- `desktop_api.py`
- `tests/test_desktop_api.py`
- `apps/desktop/src/App.tsx`
- `apps/desktop/src/styles.css`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `docs/OWNERS_MANUAL.md`
- `WORK_LOG.md`

What changed:

- Added read-only `/api/paper-review`.
- The payload summarizes paper-trade metrics, readiness gaps, exit reasons, failure reasons, entry reasons, wallet-label exposure, and next review actions.
- Native Replay tab now starts with a Paper Profitability Review panel.
- The panel shows whether the paper sample is meaningful yet, progress toward 50 closed trades, recommended 100-trade target, win rate, total PnL, expectancy, profit factor, reason breakdowns, and wallet-label exposure.
- Live execution remains locked; this panel is review and tuning evidence only.

Verification:

- Added failing API test first for paper-review readiness and trade-quality summary.
- `trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests.test_paper_review_payload_reports_readiness_and_trade_quality`
- `trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests.test_paper_review_payload_reports_readiness_and_trade_quality tests.test_desktop_api.DesktopApiTests.test_overview_payload_is_paper_locked`
- `trading_env/bin/python -m py_compile desktop_api.py core/performance_analyzer.py`
- `npm run check`

Remaining:

- Wait for at least 50 closed paper trades before treating profitability as meaningful.
- Tune confirmation rules only after repeated patterns appear in the paper review.

### 2026-05-08 - Cockpit Wallet Confidence Summary

Changed files:

- `desktop_api.py`
- `tests/test_desktop_api.py`
- `apps/desktop/src/App.tsx`
- `apps/desktop/src/styles.css`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `docs/OWNERS_MANUAL.md`
- `WORK_LOG.md`

What changed:

- Added `wallet_confidence` to `/api/overview`.
- The summary rolls up recent wallet signals and open paper-trade wallet attribution against wallet performance, behavior labels, and postmortem records.
- Native Cockpit now shows a Wallet Confidence card with wallet count, signal count, token count, open-trade driver count, proven wallet count, trap-risk count, average score, top labels, and top wallets.
- The summary is read-only and does not change tracked wallets, promote wallets, execute trades, or unlock live execution.

Verification:

- Added failing API test first for overview wallet-confidence summary.
- `trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests.test_overview_wallet_confidence_summarizes_recent_signal_wallets`
- `trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests.test_overview_wallet_confidence_summarizes_recent_signal_wallets tests.test_desktop_api.DesktopApiTests.test_overview_payload_is_paper_locked`
- `trading_env/bin/python -m py_compile desktop_api.py`
- `npm run check`

Remaining:

- Use this summary as review evidence for confirmation-mode threshold tuning, while keeping all live execution locked.

### 2026-05-07 - Selected Token Wallet Confidence

Changed files:

- `desktop_api.py`
- `tests/test_desktop_api.py`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/components/TokenDetail.tsx`
- `apps/desktop/src/styles.css`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `docs/OWNERS_MANUAL.md`
- `WORK_LOG.md`

What changed:

- Added selected-token `wallet_context` to `/api/positions/{mint}`.
- The context joins token-matched wallet signals and paper-trade attribution with wallet performance, behavior labels, rolling windows, and postmortem summaries.
- Native Details tab now has a Wallet Confidence card showing matched wallets, matched signals, proven wallets, trap wallets, average score, per-wallet score/PnL, closed/failed outcomes, and behavior labels.
- The feature is read-only and does not promote wallets, change strategy thresholds, buy, sell, or unlock live execution.

Verification:

- Added failing API test first for selected-token wallet context.
- `trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests.test_wallet_context_for_mint_summarizes_signal_wallet_confidence`
- `trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests.test_wallet_context_for_mint_summarizes_signal_wallet_confidence tests.test_desktop_api.DesktopApiTests.test_wallet_detail_payload_includes_signals_and_paper_trades`
- `trading_env/bin/python -m py_compile desktop_api.py`
- `npm run check`
- `npm test -- --run src/lib/api.test.ts`

Remaining:

- Add an Operator Brief summary that rolls up current wallet confidence/trap exposure across active candidates and selected token.

### 2026-05-06 - Per-Wallet Postmortem Rollups

Changed files:

- `core/wallet_behavior.py`
- `core/wallet_lifecycle.py`
- `desktop_api.py`
- `tests/test_core_logic.py`
- `tests/test_desktop_api.py`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/components/WalletIntelligence.tsx`
- `apps/desktop/src/styles.css`
- `data/wallet_behavior.json`
- `data/wallet_discovery_status.json`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `docs/OWNERS_MANUAL.md`
- `WORK_LOG.md`

What changed:

- Added per-wallet postmortem rollups from paper trades into `data/wallet_behavior.json`.
- Each wallet now gets closed-trade count, failed-trade count, best/worst trade, exit-reason counts, failure-reason counts, average hold time, and recent outcomes.
- Wallet lifecycle rows now include postmortem summaries, so promotion/demotion review can show whether a wallet's best/worst evidence is meaningful.
- Wallet detail payload now exposes behavior labels, rolling windows, and postmortem summary.
- Native Wallets tab now shows selected-wallet behavior labels, rolling 7d/30d windows, best/worst outcome, top exit/failure reason, and compact postmortem stats in the Promotion Queue.

Current result:

- `data/wallet_behavior.json` contains 110 wallets.
- 20 wallets currently have closed or failed paper outcomes in their postmortem rollups.
- Live execution remains locked; this is advisory review data only.

Verification:

- Added failing tests first for wallet postmortem generation, lifecycle postmortem merge, and desktop wallet detail payload.
- `trading_env/bin/python -m unittest tests.test_core_logic.WalletBehaviorTests.test_builds_per_wallet_postmortem_rollup_from_paper_trades`
- `trading_env/bin/python -m unittest tests.test_core_logic.WalletBehaviorTests.test_builds_per_wallet_postmortem_rollup_from_paper_trades tests.test_core_logic.WalletBehaviorTests.test_builds_rolling_wallet_stats_and_behavior_labels`
- `trading_env/bin/python -m unittest tests.test_core_logic.WalletLifecycleTests.test_lifecycle_report_includes_behavior_postmortem_rollup tests.test_desktop_api.DesktopApiTests.test_wallet_detail_payload_includes_signals_and_paper_trades`
- `trading_env/bin/python utils/run_wallet_discovery_scheduler.py --once`
- `npm run check`

Remaining:

- Surface wallet confidence and postmortem summaries in Token Console / selected-token detail.
- Consider using postmortem quality as an advisory confidence input without directly changing live execution.

### 2026-05-06 - Rolling Wallet Stats And Behavior Labels

Changed files:

- `core/wallet_behavior.py`
- `core/wallet_lifecycle.py`
- `core/wallet_discovery_scheduler.py`
- `core/data_freshness.py`
- `desktop_api.py`
- `tests/test_core_logic.py`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/components/WalletIntelligence.tsx`
- `apps/desktop/src/styles.css`
- `data/wallet_behavior.json`
- `data/wallet_discovery_status.json`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `docs/OWNERS_MANUAL.md`
- `WORK_LOG.md`

What changed:

- Added `data/wallet_behavior.json`, generated from local wallet performance, paper trades, and signal timing.
- Added rolling 7d and 30d wallet windows: entries, wins/losses, win rate, average PnL, total PnL, and median hold time.
- Added behavior labels including `early-buyer`, `late-buyer`, `paper-profitable`, `follower-trap`, `high-fee-churner`, `late-exit`, `rug-exit-fast`, and `copy-bait`.
- Wallet lifecycle rows now include labels and rolling windows.
- Native Wallets tab now shows labels and 7d/30d summaries in the Promotion Queue.
- Wallet discovery scheduler now refreshes wallet behavior each cycle.
- Restarted Wallet Discovery so continuous cycles use the new behavior report.

Current result:

- `data/wallet_behavior.json` contains 110 wallets.
- Current label counts include 54 early-buyer, 10 high-fee-churner, 8 late-buyer, 7 copy-bait, 7 follower-trap, 6 rug-exit-fast, and 2 late-exit labels.
- Lifecycle API returns labels and rolling windows for wallet review rows.

Verification:

- Added failing tests first for behavior report generation, lifecycle label merge, and scheduler behavior file writes.
- `trading_env/bin/python -m unittest tests.test_core_logic.WalletBehaviorTests tests.test_core_logic.WalletLifecycleTests.test_lifecycle_report_includes_behavior_labels_and_rolling_windows tests.test_core_logic.WalletDiscoverySchedulerTests.test_scheduler_cycle_refreshes_review_files_without_applying_wallet_lists`
- `trading_env/bin/python -m py_compile core/wallet_behavior.py core/wallet_lifecycle.py core/wallet_discovery_scheduler.py desktop_api.py`
- `trading_env/bin/python utils/run_wallet_discovery_scheduler.py --once`
- Direct `/api/wallet-lifecycle?limit=3` check returned labels and rolling windows.
- `trading_env/bin/python -m unittest discover`
- `npm run check`
- `npm test`
- `npm run build`

Remaining:

- Add per-wallet postmortem rollups from paper trades.
- Use behavior labels as advisory inputs in wallet review confidence, without directly changing live execution.

### 2026-05-06 - Live Paper-Watch Subscription Reload

Changed files:

- `infra/rpc_client.py`
- `core/scanner.py`
- `main.py`
- `tests/test_core_logic.py`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`
- `docs/OWNERS_MANUAL.md`

What changed:

- Added scanner support for adding new paper-watch wallets after startup.
- Added RPC support for subscribing only newly added paper-watch wallets on the active websocket.
- Added a periodic paper-watch reload loop to the bot runtime. It reads `data/paper_watch_wallets.json` and subscribes new paper-watch wallets without requiring a manual bot restart.
- Kept tracked-wallet promotions/demotions behind the guarded review/apply workflow. The reload path only adds paper-watch observation subscriptions.
- Restarted the paper bot so the new reload code is active.

Verification:

- Added failing tests first for scanner runtime wallet add and RPC new-wallet subscription.
- `trading_env/bin/python -m unittest tests.test_core_logic.WalletLifecycleTests.test_scanner_can_add_paper_watch_wallets_after_startup tests.test_core_logic.WalletLifecycleTests.test_rpc_subscribes_only_new_paper_watch_wallets`
- `trading_env/bin/python -m py_compile infra/rpc_client.py core/scanner.py main.py`
- `trading_env/bin/python -m unittest discover`
- `npm test`
- `npm run check`
- Restarted bot. Runtime status shows `websocket` subscribed to 519 observed wallets: 518 tracked plus 1 paper-watch, and scanner is `listening`.

Remaining:

- Add rolling 7d/30d wallet stats and behavior labels.
- Consider unsubscribe/removal handling later. Current reload safely adds new paper-watch subscriptions; it does not unsubscribe removed paper-watch wallets mid-session.

### 2026-05-06 - Always-On Wallet Discovery Scheduler

Changed files:

- `core/wallet_discovery_scheduler.py`
- `utils/run_wallet_discovery_scheduler.py`
- `tests/test_core_logic.py`
- `core/runtime_status.py`
- `core/process_guard.py`
- `core/data_freshness.py`
- `core/system_health.py`
- `desktop_api.py`
- `launcher.py`
- `data/candidate_wallets.json`
- `data/paper_watch_wallets.json`
- `data/runtime_status.json`
- `data/wallet_discovery_status.json`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `docs/OWNERS_MANUAL.md`
- `WORK_LOG.md`

What changed:

- Added a safe wallet discovery scheduler cycle that refreshes watch-only candidate wallets, paper-watch wallets, scheduler status, and wallet apply preview.
- Added `utils/run_wallet_discovery_scheduler.py` with `--once` and continuous loop modes.
- Added a dedicated `wallet_discovery` runtime heartbeat so Ops/System can show whether discovery is fresh.
- Added wallet-discovery status and wallet review files to data freshness reporting.
- Added launcher-managed Wallet Discovery process and log at `logs/wallet_discovery.log`.
- Start System now starts Dashboard, Watchdog, Wallet Discovery, and Bot.
- Scheduler calls wallet apply in dry-run mode only. It never applies tracked-wallet mutations and never executes trades.

Verification:

- Added failing scheduler test first, then implemented the module.
- `trading_env/bin/python -m unittest tests.test_core_logic.WalletDiscoverySchedulerTests`
- `trading_env/bin/python -m py_compile core/wallet_discovery_scheduler.py utils/run_wallet_discovery_scheduler.py launcher.py core/runtime_status.py core/process_guard.py core/data_freshness.py core/system_health.py desktop_api.py`
- `trading_env/bin/python utils/run_wallet_discovery_scheduler.py --once`
- Direct runtime payload check showed `wallet_discovery` fresh with `cycle_ok`.
- `trading_env/bin/python -m unittest discover`
- `npm test`
- `npm run check`

Current result:

- Latest scheduler cycle found 12 candidate wallets.
- Paper-watch lane has 1 wallet.
- Approved apply-preview changes are 0.
- Live execution remains locked.

Remaining:

- The running bot loads paper-watch wallets at startup. Newly synced paper-watch wallets may require a bot restart until a runtime reload path is added.
- Add rolling wallet windows and behavior labels.

### 2026-05-06 - Native Wallet Review Apply View

Changed files:

- `desktop_api.py`
- `tests/test_desktop_api.py`
- `apps/desktop/src/App.tsx`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/lib/api.test.ts`
- `apps/desktop/src/components/WalletIntelligence.tsx`
- `apps/desktop/src/styles.css`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `docs/OWNERS_MANUAL.md`
- `WORK_LOG.md`

What changed:

- Added `GET /api/wallet-review-apply` as a dry-run preview of approved wallet promotion/demotion changes.
- Added `POST /api/wallet-review-apply` with exact confirmation `APPLY_WALLET_REVIEW` before any local wallet list update can happen.
- The route uses the existing controlled apply tool, creates backups/audits on real apply, and strips large state lists from the API response.
- Added an Approved List Update panel to the native Wallets tab with promote/demote/skipped counts, previewed changes, backup status, and a disabled-until-ready apply button.
- Apply remains local wallet metadata only. It does not buy, sell, unlock live execution, or touch execution routes.

Verification:

- `trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests.test_wallet_review_apply_route_returns_dry_run_preview_without_state_lists tests.test_desktop_api.DesktopApiTests.test_wallet_review_apply_route_requires_exact_confirmation_for_apply tests.test_desktop_api.DesktopApiTests.test_wallet_review_apply_route_applies_after_exact_confirmation`
- Direct `GET /api/wallet-review-apply` route check returned dry-run true, live execution locked true, 0 ready changes, and no raw tracked-wallet list in the response.
- `npm test -- --run src/lib/api.test.ts`
- `npm run check`
- `trading_env/bin/python -m unittest discover`
- `npm test`
- `npm run build`

Remaining:

- Add an always-on scheduler for discovery, paper-watch sync, lifecycle review, and apply preview refresh.
- Add rolling wallet windows and behavior labels.

### 2026-05-06 - Native Wallet Review Decision Controls

Changed files:

- `desktop_api.py`
- `tests/test_desktop_api.py`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/lib/api.test.ts`
- `apps/desktop/src/components/WalletIntelligence.tsx`
- `apps/desktop/src/styles.css`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `docs/OWNERS_MANUAL.md`
- `WORK_LOG.md`

What changed:

- Added a scoped desktop metadata route, `POST /api/wallet-review-decision`, for wallet lifecycle decisions.
- The route writes only `data/wallet_review_decisions.json`; it does not mutate `data/tracked_wallets.json`, `data/bad_wallets.json`, or any execution path.
- Added Wallets-tab buttons to save review decisions: approve promotion, approve demotion, hold, or reject.
- Added visible saved/error status on each lifecycle row so the operator can tell whether the approval was recorded.
- Kept the actual tracked-wallet update behind the separate controlled apply tool.

Verification:

- `trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests.test_wallet_review_decision_route_writes_approval_metadata_only tests.test_desktop_api.DesktopApiTests.test_wallet_review_decision_route_rejects_unknown_decision`
- `npm test -- --run src/lib/api.test.ts`
- `npm run check`
- `trading_env/bin/python -m unittest discover`
- `npm test`
- `npm run build`

Remaining:

- Add a native dry-run/apply review screen so approved changes can be previewed and applied without hand-running the utility.
- Add an always-on scheduler for discovery, paper-watch sync, and lifecycle refresh.

### 2026-05-06 - Controlled Wallet List Apply Tool

Changed files:

- `core/wallet_list_apply.py`
- `utils/apply_wallet_review.py`
- `tests/test_core_logic.py`
- `data/wallet_review_decisions.json`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`

What changed:

- Added a controlled apply step for approved wallet promotions and demotions.
- Apply reads `data/wallet_review_decisions.json`; raw lifecycle recommendations do not mutate lists by themselves.
- Default mode is dry-run. `--apply` is required to write changes.
- Promotions add approved wallets into `data/tracked_wallets.json` using the existing Axiom-style row shape.
- Demotions remove approved wallets from `data/tracked_wallets.json` and add wallet address strings to `data/bad_wallets.json` for current compatibility.
- Applies create backups under `data/archives/wallet_apply_YYYYMMDDTHHMMSSZ/`.
- Applies write `APPLY_SUMMARY.json` in the backup folder and append to `data/wallet_list_update_audit.json`.
- Created empty `data/wallet_review_decisions.json` for operator approvals.

Verification:

- `trading_env/bin/python -m unittest tests.test_core_logic.WalletListApplyTests`
- `trading_env/bin/python -m py_compile core/wallet_list_apply.py utils/apply_wallet_review.py`
- `trading_env/bin/python utils/apply_wallet_review.py`
- `trading_env/bin/python -m unittest discover`
- `npm run check`
- `npm test -- --run src/lib/api.test.ts`
- `git diff --check`

Remaining:

- Add a native UI to write review decisions instead of manual JSON editing.
- Add scheduler to refresh discovery, paper-watch sync, lifecycle queue, and optionally dry-run apply summary.

### 2026-05-06 - Wallet Promotion/Demotion Review Queue

Changed files:

- `desktop_api.py`
- `tests/test_desktop_api.py`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/lib/api.test.ts`
- `apps/desktop/src/App.tsx`
- `apps/desktop/src/components/WalletIntelligence.tsx`
- `apps/desktop/src/styles.css`
- `WORK_LOG.md`

What changed:

- Added read-only `/api/wallet-lifecycle` endpoint for promotion/demotion review.
- Added native Wallets tab Promotion Queue.
- Queue rows are plain and evidence-based: action, wallet, source, trade count, win/loss record, win rate, total PnL, average PnL, score, and reason/blocker.
- The queue currently reports 521 wallets, with 0 promotion-review and 3 demote-review based on current paper-performance evidence.
- Rebuilt the packaged Tauri app so the double-click app includes the queue.

Verification:

- `trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests.test_wallet_lifecycle_payload_flags_promotion_and_demotion tests.test_desktop_api.DesktopApiTests.test_wallet_lifecycle_route_is_read_only tests.test_core_logic.WalletLifecycleTests`
- `npm test -- --run src/lib/api.test.ts`
- `trading_env/bin/python -m unittest discover`
- `npm run check`
- `npm test`
- Direct `/api/wallet-lifecycle?limit=5` route check returned wallet performance metrics and lifecycle actions.
- `npm run build`
- `git diff --check`

Remaining:

- Add an explicit apply step that backs up and edits `data/tracked_wallets.json` only after review approval.
- Add scheduler to keep discovery, paper-watch sync, and lifecycle review fresh.

### 2026-05-06 - Paper-Watch Wallet Learning Lane

Changed files:

- `core/wallet_lifecycle.py`
- `utils/sync_paper_watch_wallets.py`
- `core/scanner.py`
- `infra/rpc_client.py`
- `main.py`
- `tests/test_core_logic.py`
- `data/paper_watch_wallets.json`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`

What changed:

- Added wallet lifecycle scoring for tracked, candidate, and paper-watch wallets.
- Added review actions for wallet movement: keep paper-watch, promote to trusted review, keep trusted, demote off-watch review, or observe.
- Added `data/paper_watch_wallets.json`, created from reviewed `PAPER_WATCH` candidates.
- Added `utils/sync_paper_watch_wallets.py` to rebuild the paper-watch lane without editing `data/tracked_wallets.json`.
- Bot startup now loads paper-watch wallets separately from tracked wallets.
- RPC subscription now observes both tracked and paper-watch wallets.
- Scanner now keeps separate wallet source labels: `tracked`, `paper_watch`, and `unobserved`.
- Paper-watch wallets can produce paper evidence, but remain `live_trade_driver: false`.

Verification:

- `trading_env/bin/python -m unittest tests.test_core_logic.WalletLifecycleTests`
- `trading_env/bin/python -m unittest tests.test_core_logic.ScannerCandidateFilterTests.test_scanner_keeps_paper_watch_wallets_in_separate_observed_lane tests.test_core_logic.WalletLifecycleTests`
- `trading_env/bin/python utils/sync_paper_watch_wallets.py --write`
- `trading_env/bin/python -m py_compile core/wallet_lifecycle.py core/scanner.py infra/rpc_client.py main.py utils/sync_paper_watch_wallets.py`
- `trading_env/bin/python -m unittest discover`
- `npm run check`
- `npm test -- --run src/lib/api.test.ts`

Remaining:

- Add an always-on scheduler for discovery and paper-watch sync.
- Add manual review persistence and UI actions.
- Add native visibility for paper-watch wallet lane and lifecycle status.

### 2026-05-06 - Owner Manual

Changed files:

- `docs/OWNERS_MANUAL.md`

What changed:

- A helper documentation agent created a plain-English owner/operator manual covering the product, major features, safety status, tabs, scanner, wallet intelligence, candidate wallets, paper-watch, protection, social/catalyst features, settings, runtime health, and current non-live limitations.

Verification:

- Helper reported only `docs/OWNERS_MANUAL.md` changed and no runtime/data/trading files were touched.

Remaining:

- Keep the manual updated as new features are completed.

### 2026-05-06 - Candidate Wallet Review Policy

Changed files:

- `core/wallet_discovery.py`
- `utils/discover_candidate_wallets.py`
- `tests/test_core_logic.py`
- `tests/test_desktop_api.py`
- `desktop_api.py`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/components/WalletIntelligence.tsx`
- `data/candidate_wallets.json`
- `research/BUILD_PLAN.md`
- `WORK_LOG.md`

What changed:

- Added conservative review-only policy states for discovered wallets: `PROMOTION_REVIEW`, `PAPER_WATCH`, `HOLD_REVIEW`, `TRACKED_REVIEW`, `DEMOTE_REVIEW`, and `REJECT`.
- Promotion review now requires stronger multi-mint proof: score at least 82, at least 2 winner mints, at least 2 unique mints, repeated early buys, and low sell ratio.
- Paper-watch is softer but still read-only: score at least 70, repeated early buys, winner overlap, and acceptable sell ratio.
- Tracked wallets with weak current evidence are flagged for demotion review without mutating `data/tracked_wallets.json`.
- Regenerated `data/candidate_wallets.json` with review actions. Current summary: 1 paper-watch, 2 hold-review, 13 tracked-review, 10 demote-review, 0 promotion-review.
- Updated the native Wallets candidate panel to show the review action and reason/blocker.

Verification:

- `trading_env/bin/python -m unittest tests.test_core_logic.CandidateWalletDiscoveryTests`
- `trading_env/bin/python -m unittest tests.test_core_logic.CandidateWalletDiscoveryTests tests.test_desktop_api.DesktopApiTests.test_candidate_wallets_payload_is_watch_only tests.test_desktop_api.DesktopApiTests.test_candidate_wallets_route_is_read_only`
- `trading_env/bin/python utils/discover_candidate_wallets.py --local-hours 6 --local-limit 5000 --from-paper-winners --max-winner-mints 3 --signature-limit 30 --max-transactions 15 --max-buyers-per-mint 20 --write`
- `trading_env/bin/python -m unittest discover`
- `npm run check`
- `npm test`
- `npm run build`
- `git diff --check`
- Direct `/api/candidate-wallets?limit=3` route check returned review summary and per-wallet actions.

Remaining:

- Add manual review persistence for approve/reject/hold decisions.
- Add a paper-watch lane that increases observation priority without touching live tracked wallets.

### 2026-05-06 - Native Candidate Wallet Review Panel

Changed files:

- `desktop_api.py`
- `tests/test_desktop_api.py`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/lib/api.test.ts`
- `apps/desktop/src/App.tsx`
- `apps/desktop/src/components/WalletIntelligence.tsx`
- `apps/desktop/src/styles.css`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`

What changed:

- Added read-only `/api/candidate-wallets` backed by `data/candidate_wallets.json`.
- Added candidate-wallet frontend types and API path helper.
- Added a Candidate Wallet Review section to the native Wallets tab showing score, tier, tracked/new status, evidence counts, and top reason.
- Rebuilt the packaged Tauri app so the double-click app includes the review panel.
- Kept the surface read-only: no approve, reject, promote, buy, or live-trade action was added.

Verification:

- `trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests.test_candidate_wallets_payload_is_watch_only tests.test_desktop_api.DesktopApiTests.test_candidate_wallets_route_is_read_only`
- `npm test -- --run src/lib/api.test.ts`
- `trading_env/bin/python -m unittest discover`
- `npm run check`
- `npm test`
- `npm run build`
- `git diff --check`
- Direct `/api/candidate-wallets?limit=5` route check returned `WATCH_ONLY_REVIEW`, read-only true, live execution locked true, and 5 candidate rows.

Remaining:

- Add explicit review decisions and promotion thresholds before candidate wallets can affect runtime tracking.

### 2026-05-06 - Watch-Only Candidate Wallet Discovery

Changed files:

- `core/wallet_discovery.py`
- `utils/discover_candidate_wallets.py`
- `tests/test_core_logic.py`
- `data/candidate_wallets.json`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`

What changed:

- Added a wallet discovery scorer that combines local scanner buy/sell activity, optional early-buyer evidence from winning paper-trade mints, existing tracked-wallet status, and existing wallet-performance scores.
- Added a read-only discovery utility that writes `data/candidate_wallets.json` in `WATCH_ONLY_REVIEW` mode and never edits `data/tracked_wallets.json`.
- Ran the first discovery pass using 6 hours of local scanner events plus a small read-only chain pass against recent paper winners.
- Current output: 17 candidate rows, including 3 untracked wallets for review. The top untracked wallet is `Hn7hvWN26CLTrzUypwwdwHAWDGPuqsMXZDXtgqNrN6Nn` with tier `tier_2_confirm`.

Verification:

- `trading_env/bin/python -m unittest tests.test_core_logic.CandidateWalletDiscoveryTests`
- `trading_env/bin/python -m py_compile core/wallet_discovery.py utils/discover_candidate_wallets.py`
- `trading_env/bin/python -m unittest discover`
- `trading_env/bin/python utils/discover_candidate_wallets.py --local-hours 6 --local-limit 5000 --from-paper-winners --max-winner-mints 3 --signature-limit 30 --max-transactions 15 --max-buyers-per-mint 20 --write`

Remaining:

- Add candidate-wallet review UI in the native Wallets tab.
- Define promotion/demotion thresholds before any candidate moves into the tracked-wallet runtime list.

### 2026-05-06 - Review Finding Fixes: API Boundary, State Races, And Candidate Feed

Changed files:

- `desktop_api.py`
- `infra/market_checker.py`
- `paper_trader.py`
- `core/watchdog_state.py`
- `tests/test_desktop_api.py`
- `tests/test_market_checker.py`
- `tests/test_core_logic.py`
- `apps/desktop/src/App.tsx`
- `apps/desktop/src-tauri/tauri.conf.json`
- `apps/desktop/README.md`
- `Start MemeTraderPro Desktop.command`
- `WORK_LOG.md`

What changed:

- Restricted desktop API CORS to the Tauri origin instead of trusting arbitrary localhost browser origins.
- Rejected unsafe candidate image URLs in the desktop API and removed `data:` image allowance from the Tauri CSP.
- Fixed market enrichment so Dexscreener can replace Jupiter zero liquidity/volume values while preserving a valid Jupiter price.
- Fixed paper-state merge logic so stale bot instances cannot re-open a trade already closed or failed in the current ledger.
- Fixed failed paper-buy dedupe so repeated failed attempts for the same mint remain distinct by attempt time.
- Preserved operator-entered protected amount metadata when a newer watchdog result merges after a slow pass.
- Expanded candidate feed snapshot fetch depth before filtering/deduping so repeated/watchdog snapshots do not hide valid scanner candidates.
- Preserved clicked scanner-candidate selection across overview refreshes even when the candidate is not an active position.
- Updated the double-click command to open the packaged Tauri app when available, falling back to the legacy static server only if the app bundle is missing.
- Clarified the desktop README: execution remains read-only/locked, but protected amount metadata is an allowed local mutation.

Verification:

- Added failing tests first for CORS tightening, unsafe image rejection, candidate feed fetch depth, Dex zero liquidity/volume merge, stale paper open resurrection, distinct failed-buy attempts, and watchdog amount preservation.
- `trading_env/bin/python -m unittest discover` passed 80 tests.
- `npm run check` in `apps/desktop` passed.
- `npm test` in `apps/desktop` passed 17 tests.
- `python3 -m py_compile desktop_api.py infra/market_checker.py paper_trader.py core/watchdog_state.py` passed.
- `npm run build` in `apps/desktop` produced the updated `.app` and `.dmg`.
- Restarted desktop API and reopened the packaged native app; runtime reports online with no stale components.
- CORS check confirms arbitrary `http://localhost:8765` no longer receives `Access-Control-Allow-Origin`, while `tauri://localhost` does.

Remaining:

- Direct same-user local processes can still call the loopback API; the browser-origin issue is closed, but a future launcher token would further harden non-browser local access.
- Larger maintainability work remains: split `desktop_api.py`, consolidate snapshot normalization, and retire or clearly deprecate the static `desktop_gui` client.

### 2026-05-06 - Native Live Launch Candidate Feed

Changed files:

- `desktop_api.py`
- `infra/market_checker.py`
- `tests/test_desktop_api.py`
- `tests/test_market_checker.py`
- `apps/desktop/src/App.tsx`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/lib/api.test.ts`
- `apps/desktop/src/styles.css`
- `apps/desktop/src-tauri/tauri.conf.json`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`

What changed:

- Added read-only `/api/candidates` backed by SQLite `token_snapshots` scanner contexts.
- The endpoint dedupes recent scanner candidates by mint and exposes image URL, name/symbol, market cap, liquidity, tx count, holder count, wallet score, risk, and pass/skip/block reasons when those fields are present.
- Added Dexscreener metadata extraction so new market snapshots can carry token image URL, website/social links, and 5-minute buy/sell/tx counts.
- Added a native Live Launch Feed in the Tauri GUI so scanned coins are visible even when the bot correctly skips them.
- Updated the packaged app content-security policy to allow token images over HTTPS without opening additional API or script permissions.
- Live execution remains locked; this is display/read-only candidate monitoring.

Verification:

- Added failing backend tests first for candidate-feed compaction and route behavior.
- Added failing market metadata extraction test first for image/link/tx fields.
- Added failing frontend API helper test first for the candidate endpoint path.
- `python3 -m unittest tests.test_desktop_api tests.test_core_logic` passed 69 tests.
- `trading_env/bin/python -m unittest tests.test_market_checker` passed.
- `npm test -- --run src/lib/api.test.ts` passed 12 tests.
- `npm run check` in `apps/desktop` passed.
- `npm test` in `apps/desktop` passed 17 tests.
- `npm run build` in `apps/desktop` produced the updated `.app` and `.dmg`.
- `python3 -m py_compile desktop_api.py core/scanner.py paper_trader.py` passed.
- Restarted the desktop API and reopened the packaged native app; `/api/candidates?limit=5` returned recent scanner candidates.

Remaining:

- Existing historical scanner snapshots usually lack image and tx fields. New scans can populate them when Dexscreener returns metadata.
- Holder count is still mostly available from watchdog/protection snapshots, not ordinary scanner snapshots.

### 2026-05-06 - Candidate Feed Metadata Enrichment Follow-Up

Changed files:

- `desktop_api.py`
- `infra/market_checker.py`
- `tests/test_desktop_api.py`
- `tests/test_market_checker.py`
- `apps/desktop/src/App.tsx`
- `apps/desktop/src/lib/api.ts`
- `WORK_LOG.md`

What changed:

- Confirmed the Live Launch Feed was updating, but candidates were mostly skipped and historical scanner records lacked image/tx/market-cap fields.
- Fixed market enrichment so Jupiter price results can still be merged with Dexscreener display metadata instead of blocking on Jupiter-only data.
- Added pump-style estimated market cap fallback for candidate feed rows when direct market cap is missing but price is present.
- Added an `Est. MC` label in the native feed so estimated market cap is distinguishable from direct market data.

Verification:

- Added failing tests first for Jupiter/Dexscreener metadata merge and pump market-cap estimation.
- Added failing desktop API test first for candidate feed estimated market cap.
- `trading_env/bin/python -m unittest tests.test_market_checker` passed 4 tests.
- `python3 -m unittest tests.test_desktop_api.DesktopApiTests.test_candidate_feed_compacts_scanner_snapshots_with_images_and_reasons tests.test_desktop_api.DesktopApiTests.test_candidate_feed_estimates_pump_market_cap_when_missing` passed.
- `npm run check` in `apps/desktop` passed.
- `npm run build` in `apps/desktop` produced the updated `.app` and `.dmg`.
- Restarted desktop API and reopened the packaged native app. `/api/candidates?limit=5` now returns estimated market cap for current pump candidates.

Remaining:

- Token images and tx counts still depend on Dexscreener returning metadata for the scanned mint and on new scans flowing through the enrichment path.

### 2026-05-06 - Major/Stable Candidate Block And Bad Trade Reset

Changed files:

- `core/scanner.py`
- `paper_trader.py`
- `tests/test_core_logic.py`
- `data/paper_trades.json`
- `data/archives/bad_trade_reset_20260506T071717Z/`
- `WORK_LOG.md`

What changed:

- Added scanner candidate sanity checks that hard-block known major/stable mints and symbols from meme-token paper entries.
- Added oversized market-cap/liquidity blocks so large non-meme assets cannot enter the meme strategy lane.
- Added paper PnL sanity checks that mark impossible paper-value states invalid instead of reporting absurd PnL.
- Removed the bad open paper trade for `Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB` after archiving the prior state.
- Restarted the paper bot after the patch.

Verification:

- Added failing tests first for major/stable candidate blocking, oversized market blocking, allowed pump-style candidate, and impossible PnL rejection.
- `python3 -m unittest tests.test_core_logic.PaperTraderPnlTests.test_update_pnl_rejects_impossible_paper_value tests.test_core_logic.ScannerCandidateFilterTests` passed.
- `python3 -m unittest discover` passed 67 tests.
- `python3 -m py_compile core/scanner.py paper_trader.py` passed.
- Desktop API reports runtime `online` with no critical stale components and `open_trades: 0`.

Remaining:

- Quotes heartbeat can remain stale until a fresh quote-worthy candidate triggers quote checking; runtime is still online because critical bot/websocket/scanner heartbeats are fresh.

### 2026-05-05 - Current Position Reset

Changed files:

- `data/paper_trades.json`
- `data/manual_watchlist.json`
- `data/archives/positions_reset_20260505T201643Z/`
- `WORK_LOG.md`

What changed:

- Stopped the paper bot and watchdog before resetting active local position state.
- Archived the prior paper-trade and manual-watchlist files under `data/archives/positions_reset_20260505T201643Z/`.
- Cleared 2 open paper trades from `data/paper_trades.json`.
- Cleared 3 protected manual positions from `data/manual_watchlist.json`.
- Preserved closed/failed paper-trade history.
- Restarted the paper bot and protection watchdog after the reset.

Verification:

- Desktop API reports runtime `online` with no stale components.
- `/api/overview` reports `open_trades: 0` and `protected_positions: 0`.
- Running processes: `desktop_api.py`, `main.py`, and `core.rug_watchdog`.

Remaining:

- This starts a clean paper-observation window from zero active positions.

### 2026-05-05 - Runtime Restart For Native GUI

Changed files:

- `WORK_LOG.md`

What changed:

- Investigated the native GUI `stale` status.
- Confirmed stale state came from old heartbeats in `data/runtime_status.json`, not a broken desktop GUI.
- Started persistent local bot/scanner/websocket and protection watchdog processes using detached Python process launching.
- Kept live execution locked; this restart only restored paper/runtime scanning and watchdog heartbeats.

Verification:

- Desktop API remained available on `127.0.0.1:8765`.
- Running processes: `main.py`, `core.rug_watchdog`, and `desktop_api.py`.
- `/api/overview` reports runtime `online` with no stale components.

Remaining:

- Old `last_error` strings are still visible in some fresh component rows until each component clears or overwrites its previous error field.

### 2026-05-04 - Native Protected Position Amount Editor

Changed files:

- `desktop_api.py`
- `tests/test_desktop_api.py`
- `apps/desktop/src/App.tsx`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/lib/api.test.ts`
- `apps/desktop/src/components/ProtectionDrilldown.tsx`
- `apps/desktop/src/styles.css`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`

What changed:

- Added a narrow local desktop API mutation route: `POST /api/watchlist/protected-amount`.
- The route only updates protected-position amount metadata in `data/manual_watchlist.json`; it cannot buy, sell, enable auto-sell, or unlock live execution.
- Added a native Protection-tab editor for amount, decimals, optional raw amount, and test/simulated marker.
- The editor validates missing amount/decimals client-side and surfaces server validation errors.
- Saved results update the native watchlist state immediately.

Verification:

- Added failing tests first for the scoped metadata route and frontend endpoint helper, then implemented the feature.
- `python3 -m unittest tests.test_desktop_api` passed 32 tests.
- `python3 -m unittest discover` passed 63 tests.
- `python3 -m py_compile desktop_api.py core/protection_amounts.py` passed.
- `npm run check` in `apps/desktop` passed.
- `npm test` in `apps/desktop` passed 16 tests.
- `npm run build` in `apps/desktop` produced the updated `.app` and `.dmg`.

Remaining:

- Restart any already-running desktop API process before using this route, because an old server process will not know the new endpoint.
- Add an optional "run watchdog quote check after save" control after the job/progress monitor is in place.

### 2026-05-04 - Native Chart Viewport Persistence

Changed files:

- `apps/desktop/src/components/TradingChart.tsx`
- `apps/desktop/src/styles.css`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`

What changed:

- Preserved the chart's visible time range and price range across 1-second selected-token refreshes.
- Added a `Fit Latest` control so the operator can reset the chart after zooming or panning.
- Kept charting display-only; no trading, route, safety, or runtime mutation behavior changed.

Verification:

- `npm run check` in `apps/desktop` passed.
- `npm test` in `apps/desktop` passed 15 tests.
- `npm run build` in `apps/desktop` produced the updated `.app` and `.dmg`.

Remaining:

- Perform a visual/manual pass in the packaged app to confirm mouse-wheel zoom, axis drag, and center-chart panning feel right on the actual desktop window.

### 2026-05-04 - Native Protection Exit Readiness Checklist

Changed files:

- `apps/desktop/src/components/ProtectionDrilldown.tsx`
- `apps/desktop/src/styles.css`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`

What changed:

- Added an Exit Readiness checklist to the native Protection drilldown.
- The checklist separates amount present/missing, wallet/manual/test ownership source, sell-route quote state, live execution lock state, and auto-sell state.
- Test amounts now read as simulated route-testing inputs instead of wallet-owned balances.
- Live execution and auto-sell remain locked/off; this is display-only operator safety context.

Verification:

- `npm run check` in `apps/desktop` passed.
- `npm test` in `apps/desktop` passed 15 tests.
- `npm run build` in `apps/desktop` produced the updated `.app` and `.dmg`.

Remaining:

- Add a controlled native editor later for protected-token amount entry after the local mutation workflow is designed and gated.

### 2026-05-04 - Simulated Protection Quote Feasibility Test

Changed files:

- `core/protection_amounts.py`
- `utils/set_protected_amount.py`
- `core/watchdog_state.py`
- `desktop_api.py`
- `tests/test_core_logic.py`
- `tests/test_desktop_api.py`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/components/ProtectionDrilldown.tsx`
- `apps/desktop/src/styles.css`
- `data/manual_watchlist.json` local runtime state
- `data/runtime_status.json` local runtime state
- `WORK_LOG.md`

What changed:

- Added explicit test-amount support for protected positions: `token_amount_source=operator_test_amount`, `wallet_balance_status=test_amount`, `test_amount=true`, and a safety note.
- Native Protection drilldown now displays a warning note when an amount is simulated rather than wallet-owned.
- Applied a simulated 1,000-token amount with 6 decimals to protected token `79ogrGd2bhRS455phmsJo8iHYzBusqgLeyxF9Tf5pump`.
- Ran the watchdog once to exercise quote feasibility with that clearly marked test amount.

Verification:

- Watchdog checked 3 protected tokens.
- The simulated protected token remained `EMERGENCY`.
- Its prepared sell quote moved to `feasible`, `quote_pass=True`, `quote_reason=quote_passed`, `quote_route_count=1`, `quote_price_impact_pct=0.02457896165618861`, using `quote_input_amount_raw=1000000000`.
- `python3 -m unittest discover` passed 61 tests.
- `trading_env/bin/python -m unittest discover` passed 61 tests.
- `python3 -m py_compile core/protection_amounts.py utils/set_protected_amount.py desktop_api.py core/watchdog_state.py` passed.
- `npm run check` passed TypeScript checking.
- `npm test` passed 15 React/helper tests.
- `npm run build` produced the updated macOS `.app` and `.dmg`.

Remaining:

- The quote result is simulation-only and does not prove an owned wallet position can sell.
- For real manual trades, replace test amount with wallet balance lookup or verified operator-owned amount.

### 2026-05-04 - Manual Protected Amount Handling

Changed files:

- `core/protection_amounts.py`
- `utils/set_protected_amount.py`
- `desktop_api.py`
- `tests/test_core_logic.py`
- `tests/test_desktop_api.py`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/components/ProtectionDrilldown.tsx`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`

What changed:

- Added validated manual protected-position amount handling for decimal amount + decimals or raw token amount.
- Added a local utility for explicitly setting a protected token amount in `data/manual_watchlist.json`.
- Manual amount patches stamp `token_amount_source=operator_manual`, `token_amount_updated_at`, and `wallet_balance_status=manual_amount`.
- Prepared exits move from `amount_missing` to `pending` when a valid manual raw amount is available, while live execution remains locked.
- Desktop API now includes amount, decimals, wallet-balance, and quote reason fields in protection summaries.
- Native Protection drilldown now shows amount, amount source, balance status, decimals, and amount/quote reason.

Verification:

- Added tests for decimal amount conversion, missing-decimals rejection, watchlist amount patching, and desktop protection amount payloads.
- `python3 -m unittest discover` passed 59 tests.
- `trading_env/bin/python -m unittest discover` passed 59 tests.
- `python3 -m py_compile core/protection_amounts.py utils/set_protected_amount.py desktop_api.py` passed.
- `npm run check` passed TypeScript checking.
- `npm test` passed 15 React/helper tests.
- `npm run build` produced the updated macOS `.app` and `.dmg`.

Remaining:

- Use the utility or dashboard form to add actual token amounts for protected manual positions before re-running watchdog quote feasibility.
- Native direct editing remains intentionally out of scope until the validated Settings/editor workflow is implemented.

### 2026-05-04 - Live Watchdog Race-Control Verification

Changed files:

- `data/manual_watchlist.json` local runtime state
- `data/runtime_status.json` local runtime state
- `WORK_LOG.md`

What changed:

- Ran one approved live watchdog pass against the current local manual protection watchlist.
- The watchdog checked 3 protected tokens and stamped the run with `watchdog_run_id` / checked timestamps.
- All 3 protected tokens reported `EMERGENCY` based on severe liquidity and price drawdown from peak.
- Exit quote status remained `amount_missing` because the protected manual positions do not currently include token amounts.
- No live trade, sell, auto-sell, execution route, or safety-gate unlock occurred.

Verification:

- `trading_env/bin/python -m core.rug_watchdog_once` completed successfully and reported `Checked 3 protected token(s)`.
- Runtime status reported watchdog `complete`, 3 protected tokens, active provider `helius_gatekeeper`, and no stale watchdog update skips on this run.

Remaining:

- To test quote feasibility and prepared exit sizing, manual protected positions need token amount/decimals populated from wallet balance lookup or operator input.

### 2026-05-04 - Watchdog And Paper Trade Race Controls

Changed files:

- `core/watchdog_state.py`
- `core/rug_watchdog.py`
- `paper_trader.py`
- `tests/test_core_logic.py`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`

What changed:

- Added a dependency-light watchdog state merge helper with per-token freshness checks.
- Watchdog runs now stamp protected-token updates with `watchdog_run_id`, `watchdog_started_at_epoch`, `watchdog_checked_at_epoch`, and `watchdog_checked_at`.
- Watchlist saves now reject stale watchdog updates instead of allowing a slower older run to overwrite newer risk state.
- Stale watchdog skips are counted in runtime status via `watchdog.stale_updates_skipped`.
- Paper-trade state merging now deduplicates currently open positions by mint, preventing duplicate open trades from concurrent bot instances.
- Duplicate open attempts preserve the first open trade and record `duplicate_open_attempts`, `last_duplicate_open_attempt_at`, and `last_duplicate_open_attempt_reason`.
- Live execution and auto-sell remain locked; this was a persistence/process-safety hardening pass only.

Verification:

- Added regression tests for stale watchdog write rejection, newer watchdog write acceptance, and duplicate open paper-trade dedupe.
- `python3 -m unittest discover` passed 56 tests.
- `trading_env/bin/python -m unittest discover` passed 56 tests.
- `python3 -m py_compile core/watchdog_state.py core/rug_watchdog.py paper_trader.py` passed.
- `npm run check` passed TypeScript checking.
- `npm test` passed 15 React/helper tests.
- `npm run build` produced the updated macOS `.app` and `.dmg`.

Remaining:

- Run `core.rug_watchdog_once` against live watchlist state during the next live-data test window if we want an end-to-end RPC-backed watchdog verification.
- Continue process ownership work for launcher/backend/websocket/scanner lifecycle visibility.

### 2026-05-03 - Native Loading And Empty-State Polish

Changed files:

- `apps/desktop/src/App.tsx`
- `apps/desktop/src/components/OpsPanel.tsx`
- `apps/desktop/src/components/PanelState.tsx`
- `apps/desktop/src/styles.css`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`

What changed:

- Added reusable loading and empty-state components for the native Tauri/React shell.
- Replaced first-load `UNKNOWN` flashes in Cockpit, Replay, Ops, and System panels with explicit loading states.
- Added clearer empty-state copy for positions, snapshots, paper-trade replay, readiness rows, SQLite counts, data freshness, runtime components, provider health, and local logs.
- Kept all changes display-only; no execution, auto-sell, trading, settings mutation, or safety gates changed.

Verification:

- Desktop API and Vite preview both responded locally during inspection.
- `/api/overview`, `/api/readiness`, and `/api/operator-config` returned live local payloads.
- `npm run check` passed TypeScript checking.
- `npm test` passed 15 React/helper tests.
- `python3 -m unittest discover` passed 53 tests.
- `trading_env/bin/python -m unittest discover` passed 53 tests.
- `npm run build` produced the updated macOS `.app` and `.dmg`.

Remaining:

- Run a human visual pass in the packaged app and tighten any spacing/overflow issues found on real window sizes.
- Start the next chunk: validated native Settings view or the watchdog/process race-control pass.

### 2026-05-02 - Review Remediation Pass

Changed files:

- `desktop_api.py`
- `paper_trader.py`
- `tests/test_desktop_api.py`
- `tests/test_core_logic.py`
- `apps/desktop/src/App.tsx`
- `apps/desktop/src/components/WalletIntelligence.tsx`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`

What changed:

- Restricted desktop API CORS to local/Tauri origins instead of wildcard access, while keeping the API read-only.
- Added safe request handling so unexpected desktop API exceptions return a locked 500 payload instead of crashing the request thread.
- Hardened query parsing and decoded path parameters for wallet/token/detail routes.
- Fixed paper PnL so entry fees remain included after price refreshes.
- Preserved valid zero values for price, liquidity, market cap, holder count, and wallet trade PnL summaries instead of falling through to stale fallbacks.
- Split native GUI refresh into critical and optional API loads so a secondary endpoint failure does not blank the main cockpit.
- Cleared stale selected-token detail state when no token is selected and added wallet-detail overlap protection.
- Corrected wallet detail PnL rollups to display dollar PnL instead of percent formatting.
- Made protected-token rows selectable in the native Protection tab.

Verification:

- Added regression coverage for local-only CORS, safe API error handling, malformed query fallback, decoded path params, paper PnL fee retention, and zero-value preservation.
- `python3 -m unittest discover` passed 53 tests.
- `trading_env/bin/python -m unittest discover` passed 53 tests.
- `npm run check` passed TypeScript checking.
- `npm test` passed 15 React/helper tests.
- `npm run build:web` passed Vite production build.
- `npm run build` produced the updated macOS `.app` and `.dmg`.

Remaining:

- Larger maintainability items remain: split `desktop_api.py` into smaller modules, define shared API contracts, and continue consolidating canonical JSON/SQLite ownership.
- Race findings around watchdog runs and duplicate paper-bot instances still need a dedicated storage/process-control pass.

### 2026-05-02 - Native System Data Freshness

Changed files:

- `apps/desktop/src/App.tsx`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/lib/api.test.ts`
- `apps/desktop/src/styles.css`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`

What changed:

- Wired existing read-only `/api/freshness` into the native System tab.
- Added Data Freshness status cards and source rows showing source status, age, path, owner, and detail.
- Added warning-pill styling so fresh/stale/broken states read consistently with the rest of the native UI.
- Kept the feature inspection-only; no state mutation or runtime restart control was added.

Verification:

- `python3 -m unittest discover` passed 46 tests.
- `trading_env/bin/python -m unittest discover` passed 46 tests.
- `npm run check` passed TypeScript checking.
- `npm test` passed 15 React/helper tests.
- `npm run build:web` passed Vite production build.
- Browser verification confirmed System tab renders Data Freshness and source rows after API refresh.
- `npm run build` produced the updated macOS `.app` and `.dmg`.

Remaining:

- Add clearer first-load skeletons for System panels so they do not briefly show `UNKNOWN` before the first API payload arrives.

### 2026-05-02 - Native Wallet Drilldown

Changed files:

- `desktop_api.py`
- `tests/test_desktop_api.py`
- `apps/desktop/src/App.tsx`
- `apps/desktop/src/components/WalletIntelligence.tsx`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/lib/api.test.ts`
- `apps/desktop/src/styles.css`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`

What changed:

- Added read-only `/api/wallets/<wallet>` detail payload with wallet score summary, matching recent wallet signals, and directly attributed paper trades.
- Added selected-wallet state to the native app and loaded wallet detail on the same read-only local API pattern.
- Made the Wallets tab selectable so clicking a wallet updates the detail panel and selected-wallet signal list.
- Kept the feature inspection-only; no wallet edits, copy toggles, live buys, sells, or execution routes were added.

Verification:

- Wrote failing backend tests for wallet detail payload and route, then implemented the endpoint.
- `python3 -m unittest discover` passed 46 tests.
- `trading_env/bin/python -m unittest discover` passed 46 tests.
- `npm run check` passed TypeScript checking.
- `npm test` passed 14 React/helper tests.
- `npm run build:web` passed Vite production build.
- Temporary desktop API check confirmed `/api/wallets/<wallet>` returns wallet detail, signal count, paper trade count, and live execution locked.
- Browser verification confirmed the Wallets tab renders Wallet Detail, selected-wallet signals, and wallet selection changes between rows.
- `npm run build` produced the updated macOS `.app` and `.dmg`.

Remaining:

- Add per-wallet token outcome charts/hold-time stats after paper-trade records expose enough structured timing fields.

### 2026-05-01 - Helius Provider Failover And Status

Changed files:

- `core/rpc_provider.py`
- `core/rug_watchdog.py`
- `desktop_api.py`
- `tests/test_core_logic.py`
- `tests/test_desktop_api.py`
- `apps/desktop/src/components/OpsPanel.tsx`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/styles.css`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`

What changed:

- Added a shared Helius RPC provider layer that prefers Gatekeeper, falls back to standard Helius mainnet, supports custom fallback URLs, and redacts keys in safe URLs/errors.
- Added public Solana RPC as the built-in last-resort read fallback when Helius paths are unavailable.
- Wired watchdog mint, wallet-balance, and holder-account Helius calls through provider failover instead of hard-coded mainnet-only calls.
- Added cached provider health to the desktop API and surfaced Provider Health in the native Ops tab.
- Ensured the desktop API loads local `.env` provider config before checking provider health.
- Kept live execution locked; provider health does not unlock buys, sells, or auto-sell.

Verification:

- `python3 -m unittest tests.test_core_logic.RpcProviderTests` passed 4 provider tests.
- `python3 -m unittest discover` passed 44 tests.
- `trading_env/bin/python -m unittest discover` passed 44 tests.
- `npm run check` passed TypeScript checking.
- `npm test` passed 13 React helper tests.
- `npm run build:web` passed Vite production build.
- `npm run build` produced the updated macOS `.app` and `.dmg`.
- Temporary desktop API check confirmed `/api/operator-config` reports degraded provider state, active `helius_mainnet`, and live execution locked.
- Browser verification confirmed the native Ops tab renders Provider Health with `degraded`, `helius_mainnet`, Gatekeeper `max usage reached`, and live execution locked.
- Latest live provider health check now reports `healthy`, active `helius_gatekeeper`, standard Helius mainnet healthy, public Solana RPC healthy, and live execution still locked.

Remaining:

- Add a paid/private non-Helius provider fallback before any real-money live mode is considered; the public endpoint is best treated as an emergency read-only backstop.
- LaserStream is out of scope for now due to cost. Keep the provider plan focused on Helius API + Gatekeeper, with public Solana RPC only as an emergency read-only backstop.

### 2026-05-01 - Native Chart Viewport Persistence

Changed files:

- `apps/desktop/src/components/TradingChart.tsx`

What changed:

- Changed the native chart to preserve its chart instance across 1-second data refreshes.
- Enabled mouse wheel, drag panning, touch drag, and axis scaling through the chart options.
- Limited automatic `fitContent()` to initial load and metric changes so manual zoom/pan is not reset every refresh.

Verification:

- Covered by the TypeScript, React, Vite, and Tauri build verification in the provider-failover chunk above.

Remaining:

- Browser verification confirmed the chart remains interactive after refresh while using scroll/drag gestures against live local state.

### 2026-05-01 - Native 1s Candle Aggregation

Changed files:

- `core/position_cockpit.py`
- `desktop_api.py`
- `tests/test_core_logic.py`
- `tests/test_desktop_api.py`
- `apps/desktop/src/components/TradingChart.tsx`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/lib/api.test.ts`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`

What changed:

- Changed selected-token candle requests to use 1-second candle intervals.
- Updated candle aggregation so sparse one-point price buckets can infer their open from the previous close, producing meaningful red/green candle bodies when live data arrives once per second.
- Added `interval_seconds` to candle API payloads and surfaced `1s candles` in the native chart header.
- Kept the change display-only/read-only; no trading, watchdog execution, or auto-sell behavior was changed.

Verification:

- `python3 -m unittest tests.test_core_logic tests.test_desktop_api` passed 38 tests.
- `npm run check` passed TypeScript checking.
- `npm test` passed 13 React helper tests.
- `npm run build:web` passed Vite production build.
- `python3 -m unittest discover` and `trading_env/bin/python -m unittest discover` each passed 38 tests.
- Restarted the read-only desktop API and confirmed `/api/candles?...&interval=1` returns 1-second candles with inferred red/green bodies.
- Browser interaction verification passed: cockpit rendered Price chart, `1s candles`, and TradingView lightweight-charts credit with no API error.
- `npm run build` produced the updated macOS `.app` and `.dmg`.

Remaining:

- True real-time behavior still depends on live snapshot ingestion. This prepares the GUI/chart path for that data once the feed is consistently fresh.

### 2026-05-01 - Native Ops And Logs Panel

Changed files:

- `desktop_api.py`
- `tests/test_desktop_api.py`
- `apps/desktop/src/App.tsx`
- `apps/desktop/src/components/OpsPanel.tsx`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/lib/api.test.ts`
- `apps/desktop/src/styles.css`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`

What changed:

- Added read-only `/api/operator-config` with strategy thresholds, refresh timing, runtime summary, and safety lock state.
- Added read-only `/api/logs` with bounded, redacted tails for local bot/dashboard/desktop/watchdog logs.
- Added native Ops tab with Operator Config, Runtime Freshness, and Local Logs panels.
- Kept all behavior read-only; no settings mutation, live execution, or auto-sell control was added.

Verification:

- `python3 -m py_compile desktop_api.py tests/test_desktop_api.py`
- `python3 -m unittest tests.test_desktop_api` passed 20 tests.
- `npm run check` passed TypeScript checking.
- `npm test` passed 13 React helper tests.
- `npm run build:web` passed Vite production build.
- Restarted the read-only desktop API and confirmed `/api/operator-config` and `/api/logs?limit=2` returned HTTP 200.
- Browser interaction verification passed: clicking the native React `ops` tab rendered Operator Config, Runtime Freshness, Local Logs, and Live Execution sections.
- `python3 -m unittest discover` and `trading_env/bin/python -m unittest discover` each passed 37 tests.
- `npm run build` produced the updated macOS `.app` and `.dmg`.

Remaining:

- Add deeper per-wallet drilldown and refine the Ops panel layout after real use.
- Later add validated settings editing only after explicit write controls and audit records are designed.

### 2026-05-01 - Native Wallet Intelligence Panel

Changed files:

- `desktop_api.py`
- `tests/test_desktop_api.py`
- `apps/desktop/src/App.tsx`
- `apps/desktop/src/components/WalletIntelligence.tsx`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/lib/api.test.ts`
- `apps/desktop/src/styles.css`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`

What changed:

- Added a read-only `/api/wallets` endpoint that merges tracked wallet labels with wallet performance records.
- Added wallet score, label, signal count, paper entries, win rate, PnL metrics, last-seen age, and recent wallet signals to the desktop API payload.
- Added a native Wallets tab with wallet list, top-wallet snapshot, and recent wallet signal feed.
- Kept the endpoint and UI inspection-only; no wallet edits, live trading, spending, or execution behavior was added.

Verification:

- `python3 -m py_compile desktop_api.py tests/test_desktop_api.py`
- `python3 -m unittest tests.test_desktop_api` passed 17 tests.
- `npm run check` passed TypeScript checking.
- `npm test` passed 12 React helper tests.
- `npm run build:web` passed Vite production build.
- Browser interaction verification passed: clicking the native React `wallets` tab rendered Wallet Intelligence, Top Wallet Snapshot, and Recent Wallet Signals sections.
- `python3 -m unittest discover` and `trading_env/bin/python -m unittest discover` each passed 34 tests.
- `npm run build` produced the updated macOS `.app` and `.dmg`.
- Restarted the read-only desktop API in the background and confirmed `/api/wallets?limit=1` returned HTTP 200.

Remaining:

- Add settings/log/status panels for daily operator use.
- Add deeper per-wallet drilldown later, including wallet-specific trade history and token outcomes.

### 2026-05-01 - Native Selected-Token 1s Refresh

Changed files:

- `apps/desktop/src/App.tsx`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/lib/api.test.ts`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`

What changed:

- Changed the native GUI selected-token data path to refresh every 1 second.
- Kept broader overview/readiness/trades/watchlist refresh at 7 seconds to avoid unnecessary API churn.
- Added overlap protection so slow selected-token requests do not stack on top of each other.
- Kept all routes read-only; this only affects chart/detail/protection data freshness.

Verification:

- `npm run check` passed TypeScript checking.
- `npm test` passed 11 React helper tests.
- `npm run build:web` passed Vite production build.
- `npm run build` produced the updated macOS `.app` and `.dmg`.

Remaining:

- Add true streaming/WebSocket ingestion later for sub-second/event-driven updates.
- Keep emergency auto-sell locked until safety gates, audit logs, and live execution controls are complete.

### 2026-05-01 - Native Protection Drilldown Panel

Changed files:

- `apps/desktop/src/App.tsx`
- `apps/desktop/src/components/ProtectionDrilldown.tsx`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/styles.css`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`

What changed:

- Added a native read-only Protection tab drilldown backed by `/api/watchlist`.
- Added protected-token list, selected protection summary, drawdown metrics, quote state, holder/top-10 metrics, token mechanics, and explicit live-action/auto-sell lock state.
- Kept all controls inspection-only; no execution, sell, buy, add-position, or auto-sell route was added.

Verification:

- `npm run check` passed TypeScript checking.
- `npm test` passed 10 React helper tests.
- `npm run build:web` passed Vite production build.
- `npm run build` produced the updated macOS `.app` and `.dmg`.
- Browser interaction verification passed: clicking the native React `protection` tab rendered Protected Tokens, Protection Drilldown, Safety State, and Live Action sections.

Remaining:

- Add wallet detail and settings/log/status panels in the native shell.
- Continue replacing Streamlit-only workflows with dense native equivalents.

### 2026-05-01 - Native Token Detail Panel

Changed files:

- `apps/desktop/src/App.tsx`
- `apps/desktop/src/components/TokenDetail.tsx`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/styles.css`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`

What changed:

- Added a native read-only Details tab to the Tauri shell.
- Added a selected-token Token Detail panel with Token Mechanics, Holder / Dev Risk, Quote Feasibility, and Decision Record sections.
- Extended the native API types so the GUI can display token mechanics risk, hard-block reasons, holder concentration, dev bonded-token reputation, quote pass/fail state, confirmation reasons, score reasons, and strategy guard output.
- Kept the surface inspection-only: no live buy, sell, add-position, or auto-sell route was added.

Verification:

- `npm test` passed 10 React helper tests.
- `npm run check` passed TypeScript checking.
- `npm run build:web` passed Vite production build.
- `npm run build` produced the macOS `.app` and `.dmg`.
- `cargo test` passed 2 Rust launcher tests.
- `cargo check` passed for the Tauri app.
- `python3 -m unittest discover` and `trading_env/bin/python -m unittest discover` each passed 32 tests.
- Browser interaction verification passed: clicking the native React `details` tab rendered exactly one Token Mechanics, Holder / Dev Risk, Quote Feasibility, and Decision Record section.

Remaining:

- Add wallet detail and protection drill-down views with the same dense read-only pattern.
- Continue improving native panel ergonomics before any live execution work.

### 2026-05-01 - Tauri Desktop Shell Spike

Changed files:

- `apps/desktop/package.json`
- `apps/desktop/package-lock.json`
- `apps/desktop/index.html`
- `apps/desktop/tsconfig.json`
- `apps/desktop/vite.config.ts`
- `apps/desktop/src/App.tsx`
- `apps/desktop/src/main.tsx`
- `apps/desktop/src/styles.css`
- `apps/desktop/src/components/LockedActions.tsx`
- `apps/desktop/src/components/PositionMonitor.tsx`
- `apps/desktop/src/components/TradeLifecycle.tsx`
- `apps/desktop/src/components/TradingChart.tsx`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/lib/api.test.ts`
- `apps/desktop/src/lib/trades.ts`
- `apps/desktop/src/lib/trades.test.ts`
- `apps/desktop/src-tauri/Cargo.toml`
- `apps/desktop/src-tauri/Cargo.lock`
- `apps/desktop/src-tauri/build.rs`
- `apps/desktop/src-tauri/src/main.rs`
- `apps/desktop/src-tauri/tauri.conf.json`
- `apps/desktop/src-tauri/capabilities/default.json`
- `apps/desktop/src-tauri/icons/icon.png`
- `apps/desktop/README.md`
- `desktop_api.py`
- `tests/test_desktop_api.py`
- `.gitignore`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`

What changed:

- Added a separate Tauri + React desktop app shell under `apps/desktop/`.
- Added a strict read-only frontend API helper that only allows `/api/*` calls against `http://127.0.0.1:8765`.
- Added a first native desktop cockpit screen with runtime status, positions, selected-token metrics, and explicit live-execution lock status.
- Added Tauri config, macOS window sizing, CSP limited to the local desktop API, and a generated local app icon.
- Added a safe Tauri launcher bridge that checks `/api/health` and starts only `desktop_api.py` on `127.0.0.1:8765` if the read-only API is offline.
- Added frontend launcher status so the native shell reports whether the local API is already running or started by the app.
- Added native React selected-token parity panels: price/liquidity chart toggle, selected-token protection rail, signal/catalyst rail, and snapshot feed.
- Added shared React format helpers and selected-token API helpers with tests.
- Added native top navigation for Cockpit, Protection, Signals, Replay, and System.
- Added System readiness panel using read-only `/api/readiness`, including OK/WARN/FAIL counts, readiness rows, and SQLite table counts.
- Added a denser native position table with token, risk, and PnL columns.
- Added a read-only native Replay tab backed by `/api/trades`, with open, closed, and failed paper-trade panels.
- Replaced the hand-rolled SVG line chart with `lightweight-charts` candlestick/line charting for price and liquidity.
- Added a selected-position monitor panel with market cap, liquidity, holders, top-holder concentration, PnL, quote state, risk, snapshot age, source, wallet count, and score.
- Added locked action controls for Exit Now, Add Position, Protect Position, and sell presets. These controls are disabled and do not call execution routes.
- Added a paper trade lifecycle panel that shows entry/current values, size, PnL, remaining position, reason, exit advice, and source wallets for the selected token.
- Hardened native polling so refreshes cannot overlap and stale selected-token detail cannot drift onto a different displayed position.
- Added read-only CORS/preflight support to `desktop_api.py` so the Tauri/WebKit shell can read the local API from the desktop app origin while mutations remain blocked.
- Visually inspected the native app after launch; the cockpit now loads live local state, renders the chart, position list, selected-position monitor, and read-only API status correctly.
- Tightened the native cockpit layout for a denser trading-terminal feel: shorter topbar/hero, smaller status cards, tighter metric cards, narrower side rails, and a larger primary chart viewport.
- Kept this as a shell spike only: no live trading, buy/sell, execution, or auto-sell routes were added.

Verification:

- `npm test` passed 10 React helper tests.
- `npm run check` passed TypeScript checking.
- `npm run build:web` passed Vite production build.
- `cargo test` passed 2 Rust launcher tests.
- `cargo check` passed for the Tauri app.
- `npm run build` produced:
  - `apps/desktop/src-tauri/target/release/bundle/macos/MemeTraderPro.app`
  - `apps/desktop/src-tauri/target/release/bundle/dmg/MemeTraderPro_0.1.0_aarch64.dmg`
- Offline-start verification passed: after stopping port `8765`, opening `MemeTraderPro.app` started the local read-only API and `/api/health` returned `mode: READ_ONLY` with `live_execution_locked: true`.
- Native app relaunch verification passed after selected-token parity: app process started, `/api/health` stayed read-only/locked, and selected-token detail/candles/snapshots endpoints returned data.
- Native app relaunch verification passed after navigation: app process started, `/api/health` stayed read-only/locked, and `/api/readiness` returned readiness data for the System tab.
- Native app relaunch verification passed after the Replay tab: app process started, `/api/health` returned `mode: READ_ONLY` and `live_execution_locked: true`, and `/api/trades` returned 1 open, 9 closed, and 1 failed trade records.
- Native app relaunch verification passed after the cockpit upgrade: app process started, `/api/health` returned `mode: READ_ONLY` and `live_execution_locked: true`, `/api/positions` returned 4 positions, and `/api/trades` returned 1 open, 9 closed, and 1 failed trade records.
- Native visual inspection passed after the CORS/preflight fix: no desktop API error banner, runtime showed online, local API showed running, and the chart/position monitor rendered loaded state.
- Native visual inspection passed after the dense layout pass using direct window capture: the chart is now the dominant first-screen element, side panels fit without visible overlap, and API/live lock state remained visible.
- CORS/preflight verification passed with `Origin: tauri://localhost`: `GET /api/overview` returned `Access-Control-Allow-Origin: *`, and `OPTIONS /api/overview` returned `204`.
- Project Python tests passed in both environments: `python3 -m unittest discover` and `trading_env/bin/python -m unittest discover` each passed 31 tests.

Remaining:

- The Tauri app currently starts only the read-only desktop API. It does not start the bot, scanner, watchdog, or live execution services.
- Next step is adding richer native navigation and panel density until it can replace the static `desktop_gui/` prototype.

### 2026-05-01 - Read-Only Desktop GUI Foundation

Changed files:

- `desktop_api.py`
- `desktop_gui/index.html`
- `desktop_gui/assets/styles.css`
- `desktop_gui/assets/app.js`
- `Start MemeTraderPro Desktop.command`
- `tests/test_desktop_api.py`
- `docs/superpowers/plans/2026-05-01-desktop-gui-foundation.md`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`

What changed:

- Added a non-Streamlit desktop-style GUI foundation served locally from `desktop_api.py`.
- Added read-only endpoints for health, overview, runtime, readiness, freshness, positions, position details, token snapshots, candles, trades, watchlist, alerts, social state, catalyst cards, and settings.
- Added a dense dark Axiom-style static cockpit shell with position list, candle chart, runtime panel, counts, and locked controls.
- Added a double-click macOS launcher for the desktop view on `http://127.0.0.1:8765/`.
- Kept all API routes read-only; `POST`/mutation requests return `405`, and no execution modules are called.

Verification:

- `python3 -m py_compile desktop_api.py tests/test_desktop_api.py dashboard/dashboard.py core/position_cockpit.py`
- `python3 -m unittest discover` passed 24 tests.
- `trading_env/bin/python -m unittest discover` passed 24 tests.
- Local desktop server returned `200` for `/`, `/api/health`, `/api/overview`, `/api/runtime`, `/api/readiness`, `/api/freshness`, `/api/positions`, `/api/candles`, `/api/trades`, `/api/watchlist`, `/api/social`, `/api/catalyst-cards`, and `/api/settings`.
- `POST /api/positions` returned `405` with the read-only safety message.

Remaining:

- Investigated the `http://127.0.0.1:8765/` in-app browser glitch. Server-side checks showed static assets and normal API calls were fast; the risk was the UI auto-refresh plus an unscoped `/api/candles` route that could scan all token snapshots.
- Desktop GUI now uses manual refresh, limited selected-token candle/snapshot requests, HTTP/1.1 responses, and `/api/candles` without a mint returns an empty diagnostic payload instead of scanning all tokens.
- Added selected-token detail and snapshot-feed panels using read-only `/api/positions/{mint}` and `/api/tokens/{mint}/snapshots?limit=25`.
- Added a lower operator-intelligence panel to the desktop GUI with tabs for Trades, Protection, Social/Catalysts, and Readiness.
- Escaped dynamic browser-rendered text from local state before inserting it into HTML.
- Split the desktop GUI JavaScript into focused modules: `api.js`, `format.js`, `render.js`, and a small `app.js` coordinator.
- Replaced the primitive dot-like candle strip with an SVG connected price-line chart because local snapshots often produce one-point candles with identical open/high/low/close values.
- Added a selected-token-only `Auto 7s` refresh toggle so the graph can update without refreshing the full app or scanning all token snapshots.
- Added selected-token chart metric controls for Price and Liquidity using a strict read-only API metric allowlist.
- Added selected-token trend metrics for price change, liquidity change, latest snapshot source/context, and snapshot age.
- Added a selected-token Protection Rail showing state, risk level, quote status, sell-plan percentage, token mechanics, peak drawdowns, and the explicit locked live/auto-sell state.
- Added a selected-token Signal Rail for matching catalyst cards and direct local social signal matches.
- Fixed the desktop `/api/social` compatibility path so it reads the existing `signals` key as well as newer `events`.
- Separated top navigation from lower intel tabs and added real read-only panels for Replay, Positions, Orders, Holders, and Dev/Risk.
- Added explicit selected-token loading/error states so stale chart, protection, signal, detail, or snapshot panels do not remain visible after a failed local API request.
- Relaunched the desktop prototype in `memetrader_desktop` on `http://127.0.0.1:8765/`.
- After Codex reset, also relaunched `memetrader_dashboard`, `memetrader_bot`, and `memetrader_watchdog`; dashboard returned HTTP 200 and runtime heartbeats were fresh except quote status, which remains stale/error from the quote subsystem.
- Add richer panels after the static shell proves stable.
- Latest verification: `node --check desktop_gui/assets/*.js`, `python3 -m py_compile desktop_api.py tests/test_desktop_api.py`, `python3 -m unittest discover`, and `trading_env/bin/python -m unittest discover` passed 31 tests.
- Latest desktop route checks returned HTTP 200 for `/`, `/assets/app.js`, `/assets/render.js`, `/assets/styles.css`, `/api/social`, `/api/positions`, and `/api/positions/{mint}` with trend/protection/signal keys.
- Next desktop GUI step: start the React/Tauri decision spike, then move the stable read-only cockpit into the final double-click app shell.

### 2026-04-30 - Axiom-Style Position Cockpit Foundation

Changed files:

- `core/position_cockpit.py`
- `dashboard/dashboard.py`
- `tests/test_core_logic.py`
- `docs/superpowers/specs/2026-04-30-position-cockpit-design.md`
- `docs/superpowers/plans/2026-04-30-position-cockpit-implementation.md`
- `.gitignore`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`

What changed:

- Added a Position Cockpit foundation for open paper trades and protected manual positions.
- Added local candle-style chart rendering from SQLite token snapshots.
- Added Axiom-style token header metrics for market cap, price, liquidity, holders, risk, quote state, and snapshot feed.
- Added simulation-only action intents for add-position and exit-early preparation.
- Left live Buy More and Sell Now controls disabled and clearly marked as locked.
- Normalized boolean detail values in protection tables so Streamlit/Arrow does not emit mixed-type serialization tracebacks.
- Added tests for candle grouping and simulation-only action intent safety.

Verification:

- `python3 -m py_compile dashboard/dashboard.py core/position_cockpit.py tests/test_core_logic.py`
- `python3 -m unittest discover` passed 17 tests.
- `trading_env/bin/python -m unittest discover` passed 17 tests.
- Restarted Streamlit dashboard on `http://127.0.0.1:8501/`; HTTP check returned `200 OK`.
- Streamlit `AppTest` rendered the dashboard with `exception_count 0`, found `Position Cockpit`, and found the simulation/locked action buttons.

Remaining:

- Restart and visually verify the Streamlit dashboard.
- Replace Streamlit with the final pro double-click GUI stack after the cockpit behavior and data model are proven.

### 2026-04-30 - Competitor Bot Research Pass

Changed files:

- `research/COMPETITOR_BOT_REVIEW.md`
- `WORK_LOG.md`

What changed:

- Added a read-only competitor review covering 10 Solana/meme trading bots and terminals.
- Compared each competitor against MemeTraderPro's current local cockpit direction.
- Captured final-focus recommendations around fee transparency, wallet intelligence, manual protection, holder/bundle risk, and explainable decision records.

Verification:

- Research was compiled from current public sources and repo docs.
- No runtime state, trading behavior, or secrets were touched.

Remaining:

- Decide which recommended final-focus items should become immediate build tasks.

### 2026-04-30 - Six-Agent Review Remediation Pass

Changed files:

- `core/storage.py`
- `core/system_health.py`
- `core/rug_watchdog.py`
- `core/watchdog_balance.py`
- `core/catalyst_cards.py`
- `core/settings_manager.py`
- `core/wallet_performance.py`
- `dashboard/dashboard.py`
- `execution/jupiter_quote.py`
- `infra/market_checker.py`
- `launcher.py`
- `paper_trader.py`
- `social/social_signal.py`
- `social/manual_social_test.py`
- `force_test_event.py`
- `tests/__init__.py`
- `tests/test_core_logic.py`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`

What changed:

- Restricted `.env` and SQLite/WAL/SHM files to owner-only permissions.
- Added DB permission enforcement in `EventStore` and surfaced unsafe private-file modes in System Readiness.
- Forced manual protection `auto_sell` to persist as locked/off while allowing only a non-actionable `requested_auto_sell` note.
- Fixed watchdog save merging so watchdog checks patch watchdog-owned fields without overwriting operator/dashboard-owned fields.
- Fixed wallet no-balance lookup so it no longer clears manually entered token amounts.
- Replaced process-randomized social IDs with stable SHA-256 IDs and added defensive malformed-row handling.
- Allowed exact mint social matches even when market name/symbol metadata is missing.
- Made catalyst cards recognize `rug_watchdog` snapshots as watchdog risk data.
- Redacted quote, market, and dashboard watchdog errors before storing or displaying them.
- Converted candidate ledger and settings writes to lock/atomic write paths.
- Added lock-backed merge saves for paper-trade state and wallet-performance updates to reduce duplicate-process lost-update risk.
- Added per-component launcher start locks so duplicate launcher instances cannot pass check-then-spawn at the same time.
- Guarded manual test scripts so they do not mutate real runtime state unless explicitly invoked with `--write-real-state`.
- Fixed default `python3 -m unittest discover` so it now runs the project tests.

Verification:

- `python3 -m py_compile core/storage.py core/system_health.py social/social_signal.py core/catalyst_cards.py core/settings_manager.py execution/jupiter_quote.py infra/market_checker.py dashboard/dashboard.py core/rug_watchdog.py core/watchdog_balance.py social/manual_social_test.py force_test_event.py tests/test_core_logic.py`
- `python3 -m unittest discover` passed 15 tests.
- `python3 -m unittest tests.test_core_logic` passed 15 tests.
- `trading_env/bin/python -m py_compile ...` passed for changed Python files.
- `trading_env/bin/python -m unittest discover` passed 15 tests.
- `trading_env/bin/python utils/sync_state_to_sqlite.py` completed and reported populated counts.
- `stat` confirmed `.env`, `data/memetrader.db`, `data/memetrader.db-wal`, and `data/memetrader.db-shm` are mode `600`.
- Restarted dashboard, backend, and watchdog into `memetrader_dashboard`, `memetrader_bot`, and `memetrader_watchdog` screen sessions.
- Dashboard returned `HTTP/1.1 200 OK`.
- Runtime heartbeats were fresh: bot `alive`, websocket `subscribed`, scanner `listening`, watchdog `checking`, market loop `alive`.

Remaining:

- Dashboard remains oversized and should be split into service/panel modules before large UI additions.
- SQLite migrations/upserts should be hardened with explicit migration/version handling and stable trade IDs.
- Remaining lower-priority risk is mainly structural: dashboard/service extraction and SQLite migration/upsert hardening.

### 2026-04-30 - Local Social Signal Ingestion

Changed files:

- `social/social_signal.py`
- `dashboard/dashboard.py`
- `tests/test_core_logic.py`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`

What changed:

- Expanded social signals into structured local events with:
  - `event_id`,
  - platform,
  - account category,
  - keywords,
  - tickers,
  - mints,
  - sentiment,
  - discovered timestamp,
  - engagement/raw fields.
- Added ticker and Solana mint extraction from pasted social text.
- Added bulk import support for `account | text | url` and `@account: text` lines.
- Added a dashboard Social Catalyst Tracker section for adding/importing signals and reviewing recent signals/top keywords.
- Social evidence remains an input to review/catalyst context only; it does not bypass risk, quote, mechanics, or live-execution gates.

Verification:

- `python3 -m py_compile social/social_signal.py dashboard/dashboard.py tests/test_core_logic.py`
- `python3 -m unittest tests.test_core_logic` passed 10 tests.

Remaining:

- Add price-at-social-event alignment and cached X/API ingestion once credentials/path are selected.

### 2026-04-30 - Candidate Workbench Catalyst Context

Changed files:

- `dashboard/dashboard.py`
- `WORK_LOG.md`

What changed:

- Candidate Workbench now loads generated catalyst cards.
- Opportunity Inbox rows now include catalyst outcome and social-match columns.
- Candidate expanders now show catalyst outcome, social match, paper status, paper PnL, catalyst summary, and thesis lines when available.
- Restarted the dashboard cleanly after clearing the old Streamlit process that still owned port `8501`.
- Live execution and auto-sell behavior were not changed.

Verification:

- `python3 -m py_compile dashboard/dashboard.py`
- `python3 -m unittest tests.test_core_logic` passed 8 tests.
- Dashboard returned `HTTP/1.1 200 OK`.
- In-app browser DOM confirmed catalyst context is visible.

Remaining:

- Richer social ingestion/backfill is the next high-value item.

### 2026-04-30 - Runtime Restart And Scanner Heartbeat Fix

Changed files:

- `infra/rpc_client.py`
- `WORK_LOG.md`

What changed:

- Restarted the local runtime stack:
  - dashboard,
  - bot/WebSocket/scanner,
  - protection watchdog.
- Added scanner heartbeat updates in the WebSocket runtime so the scanner reports `initialized` and `listening` even when no wallet event is currently being processed.
- This prevents a false dashboard offline warning when WebSocket subscriptions are healthy but the scanner is idle.
- Live execution and auto-sell behavior were not changed.

Verification:

- `python3 -m py_compile infra/rpc_client.py`
- Bot heartbeat is fresh and `alive`.
- WebSocket heartbeat is fresh and `subscribed` to 518 wallets.
- Scanner heartbeat is fresh and `listening`.
- Watchdog heartbeat is fresh and checking 2 protected tokens.
- Dashboard is listening on `http://127.0.0.1:8501/` and returned `HTTP/1.1 200 OK`.

Remaining:

- Streamlit import/startup is slow on this machine after restarts; it did eventually bind to port `8501`.

### 2026-04-30 - Catalyst Card Ledger Foundation

Changed files:

- `core/catalyst_cards.py`
- `dashboard/dashboard.py`
- `core/data_freshness.py`
- `tests/test_core_logic.py`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`

What changed:

- Added a local catalyst-card builder that reads SQLite token snapshot payloads and produces token thesis/outcome cards.
- Generated `data/catalyst_cards.json` from current snapshots.
- Data Store now has a Catalyst Cards tab with a refresh button and summary rows.
- Token Console now shows catalyst outcome in the token table and has a per-token Catalyst detail tab.
- Freshness tracking now includes `data/catalyst_cards.json`.
- Added deterministic unit coverage for card generation from scanner and paper snapshots.
- Live trading, watchdog execution, and auto-sell behavior were not changed.

Verification:

- `python3 -m py_compile core/catalyst_cards.py dashboard/dashboard.py tests/test_core_logic.py`
- `python3 -m unittest tests.test_core_logic` passed 8 tests.
- `python3 -m core.catalyst_cards` generated 2 cards.
- `curl -I --max-time 5 http://127.0.0.1:8501/` returned `HTTP/1.1 200 OK`.

Remaining:

- Attach catalyst cards directly to Candidate Workbench candidate cards.

### 2026-04-30 - Scanner And Paper Trade Token Snapshots

Changed files:

- `core/scanner.py`
- `paper_trader.py`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`

What changed:

- Scanner signal evaluations now write durable SQLite `token_snapshots` rows with `scanner_skip` or `scanner_entry_candidate` context.
- Scanner runtime precheck skips now write `scanner_runtime_skip` snapshots for cases like missing paper trader, missing market data, or invalid entry price.
- PaperTrader now writes lifecycle snapshots for:
  - `paper_entry_opened`
  - `paper_entry_failed`
  - `paper_partial_exit`
  - `paper_exit_closed`
- Snapshot payloads include market, liquidity, market cap, risk label/score, wallet list, signal metadata, entry/exit reason, position size, remaining percentage, and PnL where available.
- Live execution and auto-sell behavior were not changed.

Verification:

- `python3 -m py_compile core/scanner.py paper_trader.py core/storage.py tests/test_core_logic.py`
- `python3 -m unittest tests.test_core_logic` passed 7 tests.

Remaining:

- Add dashboard snapshot-context filters and the candidate/catalyst-card ledger so these records become easier to review.

### 2026-04-30 - Token Snapshot Review Filters

Changed files:

- `dashboard/dashboard.py`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`

What changed:

- Data Store Snapshots tab now loads recent token snapshots with context/source filters.
- Added a context-count summary so scanner skips, entry candidates, watchdog checks, and paper lifecycle events can be separated quickly.
- Kept this read-only; no trading, watchdog, or execution behavior changed.

Verification:

- `python3 -m py_compile dashboard/dashboard.py`
- `curl -I --max-time 5 http://127.0.0.1:8501/` returned `HTTP/1.1 200 OK`.

Remaining:

- Build the candidate/catalyst-card ledger that turns these snapshots into reviewable token theses and outcomes.

### 2026-04-30 - Protected Wallet Balance Lookup

Changed files:

- `core/token_balance.py`
- `core/rug_watchdog.py`
- `dashboard/dashboard.py`
- `tests/test_core_logic.py`
- `WORK_LOG.md`

What changed:

- Added a pure owner-token-balance parser for Solana `getTokenAccountsByOwner` responses.
- Watchdog now performs wallet-balance lookup for protected entries that include a wallet address.
- When a balance is found, watchdog updates:
  - `token_amount_raw`,
  - `token_amount`,
  - `decimals` / `token_decimals`,
  - `token_amount_source: wallet_balance_lookup`,
  - wallet-balance status metadata.
- Prepared exit quote checks can now use wallet-derived raw balances instead of relying only on manual token amount entry.
- Dashboard protected-position cards now show wallet-balance status, account count, amount source, and balance update timestamp.
- Added deterministic unit coverage for owner-token-balance parsing.

Verification:

- `python3 -m py_compile core/token_balance.py core/rug_watchdog.py dashboard/dashboard.py tests/test_core_logic.py`
- `python3 -m unittest tests.test_core_logic` passed 7 tests.
- `trading_env/bin/python -m core.rug_watchdog_once`
- `python3 utils/sync_state_to_sqlite.py`
- `curl -I --max-time 5 http://127.0.0.1:8501/` returned `HTTP/1.1 200 OK`.

Current limitation:

- Existing protected entries currently have blank wallet fields, so they still show `amount_missing` until wallet addresses or manual token amounts are supplied.

### 2026-04-30 - Review Remediation Pass

Changed files:

- `.gitignore`
- `core/json_store.py`
- `core/redaction.py`
- `core/runtime_status.py`
- `dashboard/live_state.py`
- `paper_trader.py`
- `core/wallet_performance.py`
- `core/storage.py`
- `core/rug_watchdog.py`
- `dashboard/dashboard.py`
- `infra/rpc_client.py`
- `tests/test_core_logic.py`
- `WORK_LOG.md`

What changed:

- Addressed the highest-priority findings from the six-agent review.
- Added a shared JSON store helper with atomic writes and advisory file locks.
- Switched runtime status, live state, paper-trade saves, wallet-performance saves, dashboard watchlist edits, and watchdog watchlist saves toward atomic/locked writes.
- Fixed stale raw-token amount behavior: when an operator updates decimal token amount/decimals and leaves raw amount blank, old raw amount is cleared instead of overriding the new balance.
- Hardened watchdog mint/holder RPC paths so non-timeout client/JSON errors mark that token `UNKNOWN` for the relevant check instead of aborting the whole watchdog pass.
- Added secret redaction for Helius/Jupiter key patterns before RPC/WebSocket errors are printed or stored in runtime status.
- Added SQLite WAL mode and busy timeout.
- Migrated SQLite `watchlist` persistence from mint-only primary key to mint+wallet, so same-mint protected positions do not collapse in the Data Store view.
- Removed hidden trade cleanup from `EventStore()` initialization; cleanup/migration work should be explicit, not run from read paths.
- Added deterministic unit tests for protection-exit planning, Token-2022 mechanics, and holder concentration.
- Ignored runtime lock files with `data/*.lock`.

Verification:

- `python3 -m py_compile core/json_store.py core/runtime_status.py dashboard/live_state.py paper_trader.py core/wallet_performance.py core/storage.py core/rug_watchdog.py infra/rpc_client.py core/redaction.py dashboard/dashboard.py tests/test_core_logic.py`
- `python3 -m unittest tests.test_core_logic` passed 6 tests.
- `python3 utils/sync_state_to_sqlite.py`
- `trading_env/bin/python -m core.rug_watchdog_once`
- `python3` EventStore check confirmed counts and wallet-aware watchlist rows.
- `curl -I --max-time 5 http://127.0.0.1:8501/` returned `HTTP/1.1 200 OK`.

Remaining:

- The Streamlit dashboard remains unauthenticated beyond localhost binding.
- The dashboard and scanner are still large/coupled and need service-layer extraction before a real pro GUI.
- More deterministic tests are needed for scanner decisions, settings, quote analysis, storage migrations, and dashboard command handlers.

### 2026-04-30 - Watchdog Token Snapshot Storage

Changed files:

- `core/storage.py`
- `core/rug_watchdog.py`
- `dashboard/dashboard.py`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`

What changed:

- Added SQLite `token_snapshots` table and storage helpers.
- Watchdog now writes a durable token snapshot for each protected-token check, including:
  - market price/liquidity,
  - baseline/peak drawdowns,
  - mechanics risk,
  - holder concentration metrics,
  - prepared-exit action and quote status,
  - live-action permission state.
- Data Store dashboard now shows Token Snapshot counts and a recent Snapshots tab.
- Updated data source map with the new table and panel mapping.

Verification:

- `python3 -m py_compile core/storage.py core/rug_watchdog.py dashboard/dashboard.py utils/sync_state_to_sqlite.py`
- `python3 utils/sync_state_to_sqlite.py`
- `trading_env/bin/python -m core.rug_watchdog_once`
- `python3` EventStore check confirmed `token_snapshots: 2` and showed recent rows for both protected tokens.
- `curl -I --max-time 5 http://127.0.0.1:8501/` returned `HTTP/1.1 200 OK`.

Remaining:

- Extend this snapshot model to scanner entries, skips, exits, and eventual catalyst cards.

### 2026-04-30 - Holder Concentration Watchdog Wiring

Changed files:

- `core/rug_watchdog.py`
- `dashboard/dashboard.py`
- `WORK_LOG.md`

What changed:

- Watchdog now fetches `getTokenLargestAccounts` via the existing Helius RPC session.
- Wired the existing `HolderConcentrationAnalyzer` into protected-token checks.
- Stores holder concentration risk, warnings, and metrics on protected watchlist items.
- Dashboard protected-position cards now show holder risk plus holder count, top 1, top 5, and top 10 concentration metrics.
- Holder concentration remains soft risk: it can elevate otherwise safe items to warning, but it does not create a hard block or enable live execution.

Verification:

- `python3 -m py_compile core/rug_watchdog.py core/holder_concentration.py dashboard/dashboard.py`
- `python3 core/holder_concentration.py`
- `trading_env/bin/python -m core.rug_watchdog_once`
- `curl -I --max-time 5 http://127.0.0.1:8501/` returned `HTTP/1.1 200 OK`.

Observed current protected-token results:

- `nnJpF9wLXbXWLXddZTrpN7Vh5s2sJYefg7tnQukXkHU`: holder concentration `DANGER`, top 1 `94.25%`, top 5 `96.42%`.
- `79ogrGd2bhRS455phmsJo8iHYzBusqgLeyxF9Tf5pump`: holder concentration `WARNING`, top 1 `33.51%`, top 5 `54.02%`.

Remaining:

- Add system-account / pool-account exclusions or labels before using holder concentration as a stronger decision input.
- Persist normalized token risk/performance snapshots for entries, skips, exits, and watchdog checks.

### 2026-04-30 - Manual Protected Amount Capture

Changed files:

- `dashboard/dashboard.py`
- `WORK_LOG.md`

What changed:

- Added optional Token Amount, Decimals, and Raw Token Amount fields to the Manual Trade Protection form.
- Added External Position and Exit Priority fields to the same form so externally bought tokens can be tracked more explicitly.
- Updated `add_manual_watch` to preserve amount/decimal/raw amount metadata on new or existing protected entries.
- Protected-position cards now display token amount, raw amount, decimals, external-position status, and exit priority.
- This unlocks real quote-route checks on the next watchdog run whenever a protected item has a token amount.

Verification:

- `python3 -m py_compile dashboard/dashboard.py core/protection_exit.py core/rug_watchdog.py`
- Planner smoke test confirmed decimal amount plus decimals resolves to raw token amount and `quote_status: pending`.
- `curl -I --max-time 5 http://127.0.0.1:8501/` returned `HTTP/1.1 200 OK`.

Remaining:

- Existing protected entries still need their token amounts entered manually or populated by a future wallet-balance lookup.

### 2026-04-30 - Watchdog Timeout Hardening

Changed files:

- `core/rug_watchdog.py`
- `WORK_LOG.md`

What changed:

- Added per-token timeout wrappers for market checks, mint inspections, and sell-route quote checks.
- Market timeouts now mark the token `NO_DATA` / `WARNING` for that cycle instead of stalling the whole watchdog.
- Mint-inspection timeouts now mark mechanics risk `UNKNOWN` with an explicit timeout reason.
- Quote-check timeouts now mark prepared exits as `quote_status: timeout` and keep `live_action_allowed: false`.
- Watchdog runtime status counters now track market, mint-inspection, and quote timeouts.

Verification:

- `python3 -m py_compile core/rug_watchdog.py core/protection_exit.py dashboard/dashboard.py`
- `trading_env/bin/python -m core.rug_watchdog_once`
- `curl -I --max-time 5 http://127.0.0.1:8501/` returned `HTTP/1.1 200 OK`.

Remaining:

- Current protected/manual items still need token amounts or wallet-balance lookup before true sell-route quote feasibility can be checked.

### 2026-04-30 - Protection Exit Quote Feasibility Metadata

Changed files:

- `core/protection_exit.py`
- `core/rug_watchdog.py`
- `dashboard/dashboard.py`
- `research/BUILD_PLAN.md`
- `WORK_LOG.md`

What changed:

- Added protected-token amount resolution for prepared simulation exits.
- Prepared exits now distinguish:
  - `not_required` when no sell is suggested,
  - `amount_missing` when a sell is suggested but the protected/manual position has no token amount,
  - `pending` when a token amount is known and the watchdog can check a sell route.
- Watchdog now attempts a Jupiter sell-route quote only when a prepared exit suggests selling and a token amount is available.
- Quote results stay simulation-only and preserve `live_action_allowed: false`.
- Dashboard Manual Protection cards now show quote reason, checked timestamp, route count, input amount, price impact, and token amount source.
- Updated build plan current focus now that quote-feasibility metadata landed.

Verification:

- `python3 -m py_compile core/protection_exit.py core/rug_watchdog.py dashboard/dashboard.py execution/jupiter_quote.py`
- `python3 core/protection_exit.py`
- Planner smoke test for decimal token amount conversion to raw units.
- `trading_env/bin/python -m core.rug_watchdog_once`
- `curl -I --max-time 5 http://127.0.0.1:8501/` returned `HTTP/1.1 200 OK`.

Remaining:

- Current protected/manual items do not have token balances, so watchdog reports `amount_missing` rather than a real feasible/blocked route.
- Next implementation step is watchdog timeout hardening, then manual/protected amount capture or wallet-balance lookup.

### 2026-04-29 - Rohun Vora Full Repo Sweep

Changed files:

- `research/OPEN_SOURCE_REPO_REVIEW.md`
- `WORK_LOG.md`

What changed:

- Reviewed the broader `rohunvora` GitHub repo list and local read-only clones under `/tmp/rohunvora-full-review`.
- Confirmed the prior top five remain the strongest trading-edge references: `paste-trade`, `walletdoctor`, `tweet-price-charts`, `x-research-skill`, and `why-pump`.
- Added additional useful references:
  - `twitter-feedback` for reply/quote community-reaction scoring,
  - `chart-ai` for future structured chart-read/invalidation panels,
  - `rrcalc` for an operator EV/risk sizing widget,
  - `anti-slop-library` and `taste-library` for future pro GUI quality gates,
  - `cool-claude-skills` incremental-fetch discipline for social/wallet ingestion,
  - `github-tndr` / `openclaw` as longer-term alerting/control-plane references.
- Marked unrelated/media/school/demo repos as low immediate relevance.

Verification:

- Documentation-only update.
- No external repo code copied into MemeTraderPro.
- No live trading, runtime data deletion, secrets, or execution behavior touched.

Next steps:

- Keep Phase 6 safety work first.
- After quote/sell-route feasibility and watchdog hardening, build the candidate/catalyst-card ledger as the foundation for social, wallet, risk, paper-entry, skip, and postmortem learning.

### 2026-04-29 - Social Tracker Adaptation Plan

Changed files:

- `research/SOCIAL_TRACKER_ADAPTATION_PLAN.md`
- `WORK_LOG.md`

What changed:

- Broke down the GitHub/Rohun social tracker ideas into a MemeTraderPro implementation plan.
- Accepted the other agent's take: the strongest pieces to adapt are:
  - `paste-trade` signal-to-thesis-to-P&L lifecycle,
  - `walletdoctor` wallet analytics/backfill discipline,
  - `tweet-price-charts` social-signal-to-price-impact alignment,
  - `x-research-skill` cached X watchlist/pulse checks,
  - `why-pump` catalyst-card explanations.
- Defined proposed Social Event, Catalyst Card, and Social Price Alignment data objects.
- Set first implementation ticket: local catalyst-card schema/module before live X ingestion.

Verification:

- Documentation-only update.
- No live trading, secrets, runtime data deletion, or execution code touched.

Next steps:

- Build `core/catalyst_cards.py` and `data/catalyst_cards.json` after the current Phase 6 quote/watchdog safety work or as a clearly isolated side branch.

### 2026-04-29 - Critical Runtime Offline Dashboard Warning

Changed files:

- `dashboard/dashboard.py`
- `core/system_health.py`
- `WORK_LOG.md`

What changed:

- Added a top-of-dashboard red warning when the bot, websocket, or scanner heartbeat is missing or stale.
- Added explicit operator text: dashboard-only does not mean the scanner is running.
- Reused `data/runtime_status.json` heartbeat timestamps and existing runtime freshness conventions.
- Updated Runtime Health so missing critical heartbeats no longer fall through to the green "current" message.
- Updated System Readiness so missing/stale bot, websocket, or scanner heartbeats are `FAIL` instead of soft warnings.
- Did not change live execution behavior, wallet keys, buy/sell logic, launcher behavior, or trading actions.

Verification:

- `python3 -m py_compile dashboard/dashboard.py core/system_health.py`
- `python3` SystemHealth report check confirmed current missing `runtime_bot`, `runtime_websocket`, and `runtime_scanner` heartbeats return `FAIL`.
- `curl -I --max-time 5 http://127.0.0.1:8501/` returned `HTTP/1.1 200 OK`.

Next steps:

1. Make launcher/system start verify fresh bot/scanner heartbeats and visible `bot.log`.
2. Add parser diagnostics for tracked-wallet account-key hits that do not become token-owner delta events.
3. Add a postmortem mint lookup tool that reports scanner-offline vs wallet-list miss vs parser miss.

### 2026-04-29 - Red Cross Miss Postmortem

Changed files:

- `core/protection_exit.py`
- `data/manual_watchlist.json`
- `WORK_LOG.md`

What changed:

- Investigated live token `79ogrGd2bhRS455phmsJo8iHYzBusqgLeyxF9Tf5pump` after user reported it was running on Axiom and held externally.
- Added the token to manual protection as alert-only, external-position tracking:
  - `auto_sell: false`,
  - `alert_only: true`,
  - `external_position: true`,
  - `exit_priority: immediate`.
- Updated `ProtectionExitPlanner` so a user-declared immediate external exit alert creates a simulation-only `PREPARE_FULL_EXIT` intent without live execution authority.
- Ran watchdog once; the token checked `SAFE` on market/liquidity/mechanics, but still produced a priority simulated full-exit intent because the user requested immediate exit alert.

Findings:

- MemeTraderPro did not buy this token and had no prior record of it in state, logs, paper trades, candidate ledger, or SQLite.
- Only the Streamlit dashboard was running; the bot/scanner loop was offline.
- Direct RPC postmortem found at least one MemeTraderPro tracked wallet in recent transaction account keys for the mint (`ray` / `5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1`), but no token-balance owner hit for that wallet in the sampled recent transactions.
- That means the miss has two layers:
  1. scanner offline, so nothing could be detected live;
  2. current parser only records tracked wallets when they are token-balance owners, so some Axiom-style tracked-wallet bubbles can still be missed even if a tracked wallet appears elsewhere in transaction accounts.

Verification:

- `python3 -m py_compile core/protection_exit.py core/rug_watchdog.py execution/jupiter_quote.py`
- `trading_env/bin/python -m core.rug_watchdog_once`
- `python3` safety gate check confirmed `live_allowed: False`, `live_enabled: False`, and no key material configured.
- Read-only Helius RPC mint postmortem compared recent mint transactions against `data/tracked_wallets.json`.

Next steps:

1. Add dashboard red-alert when bot/websocket/scanner heartbeat is missing or stale.
2. Make launcher/system start verify fresh bot/scanner heartbeats and visible `bot.log`.
3. Add global pump/new-runner discovery beyond wallet mentions.
4. Add parser diagnostics for tracked-wallet account-key hits that do not become token-owner delta events.
5. Add postmortem mint lookup tool that reports scanner-offline vs wallet-list miss vs parser miss.
6. Extend normal exit strategy for external/manual positions: entry basis, peak tracking, trailing drawdown, quote feasibility, and alert-only exit signals.

### 2026-04-29 - Rohun Vora Repo Research

Changed files:

- `research/OPEN_SOURCE_REPO_REVIEW.md`
- `WORK_LOG.md`

What changed:

- Reviewed `https://github.com/rohunvora` from the perspective of MemeTraderPro.
- User later confirmed directly with Rohun Vora that MemeTraderPro may use anything needed from his repos and that they are completely open source.
- Identified the strongest references:
  - `paste-trade` for signal-to-thesis-to-P&L lifecycle,
  - `walletdoctor` for Solana wallet analytics/backfill discipline,
  - `tweet-price-charts` for social-to-price alignment,
  - `x-research-skill` for cheap X/social pulse checks,
  - `why-pump` for explainable catalyst cards.
- Updated reuse guidance: direct adaptation is allowed by permission, while attribution and selective integration are still preferred.

Verification:

- Repos were cloned to `/tmp/rohunvora-mtp-review` for inspection only.
- No external repo code was copied into MemeTraderPro.

Next steps:

- Convert the Rohun review into build tickets:
  1. candidate/catalyst card ledger,
  2. wallet analytics backfill metrics,
  3. social signal price alignment,
  4. cached X watchlist pulse checks,
  5. dashboard catalyst cards.

### 2026-04-29 - Prepared Protection Exit Intents

Changed files:

- `core/protection_exit.py`
- `core/rug_watchdog.py`
- `dashboard/dashboard.py`
- `research/BUILD_PLAN.md`
- `WORK_LOG.md`

What changed:

- Added simulation-only prepared exit intents for manually protected positions.
- Watchdog now attaches `prepared_exit` to protected tokens after market/mechanics checks.
- Emergency/danger protected positions can now produce `PREPARE_FULL_EXIT` or `PREPARE_PARTIAL_EXIT` guidance without executing trades.
- Prepared exits explicitly record `execution_mode: SIMULATION_ONLY` and `live_action_allowed: false`.
- Dashboard now shows prepared simulation exit action, urgency, suggested sell percentage, quote status, and reasons.
- Watchdog writes a durable `protection_exit_intent` event when a simulated sell percentage is suggested.

Verification:

- `python3 -m py_compile core/protection_exit.py core/rug_watchdog.py dashboard/dashboard.py core/holder_concentration.py`
- `python3 core/protection_exit.py`
- `python3 core/holder_concentration.py`
- `curl -I --max-time 5 http://127.0.0.1:8501/`
- `trading_env/bin/python -m core.rug_watchdog_once`
- Confirmed current protected token has `PREPARE_FULL_EXIT`, `100`, `SIMULATION_ONLY`.

Blockers:

- The watchdog one-shot completed successfully, but took roughly two minutes in this run. Timeout hardening remains important.
- Prepared exits do not yet check live sell-route/quote feasibility.

Next steps:

- Add quote/sell-route feasibility to prepared exits.
- Add per-token timeout handling in watchdog network calls.
- Wire holder concentration into risk snapshots.

### 2026-04-29 - Helper Holder Concentration Analyzer

Changed files:

- `core/holder_concentration.py`
- `WORK_LOG.md`

What changed:

- Added a pure local holder concentration analyzer for supplied holder rows.
- Computes holder count, top holder concentration percentages, top holder address, total amount, warnings, and PASS/WARNING/DANGER/UNKNOWN risk labels.
- Keeps `hard_block` false by default and performs no network, trading, execution, or runtime-state changes.

Verification:

- `python3 -m py_compile core/holder_concentration.py`
- `python3 core/holder_concentration.py`
- ASCII scan of `core/holder_concentration.py`

Blockers:

- None.

Next steps:

- Lead agent can integrate the analyzer into future token risk snapshots or dashboard views when ready.

### 2026-04-29 - Lead Agent Operating Rules

Changed files:

- `AGENT_WORKFLOW.md`
- `WORK_LOG.md`

What changed:

- Added permanent lead-agent mandate.
- Added helper-agent assignment rules.
- Added helper ownership and non-overlap rules.
- Added hard limits against live trading, spending money, deleting data, resetting git history, exposing secrets, or irreversible changes.
- Clarified branch/commit expectations for meaningful completed work.

Verification:

- Confirmed repo is a git repository at `/Users/dianeposs/Desktop/Jordan 2/meme_trader_pro`.
- Confirmed workflow docs render as Markdown.

Remaining:

- Use the new helper-agent rules for future parallel work.
- Create commits for meaningful completed chunks after review and verification.

### 2026-04-29 - Agent Coordination Docs

Changed files:

- `AGENT_WORKFLOW.md`
- `WORK_LOG.md`

What changed:

- Added permanent agent workflow instructions.
- Converted this file into the running project diary.
- Documented current work, blockers, completed work, and next actions.

Verification:

- Confirmed both root-level docs exist and render as Markdown.

Remaining:

- Keep this file updated after every meaningful work chunk.

### 2026-04-29 - Marketing Side Task

Changed files:

- `research/OPEN_SOURCE_REPO_REVIEW.md`
- Generated marketing assets under the Codex generated-images folder.

What changed:

- Spun up a marketing agent.
- Created brand direction for MemeTraderPro.
- Generated a logo concept and three ad images inspired by the TrustLayer visual style.

Verification:

- Generated images were produced successfully.

Remaining:

- Organize final selected marketing assets under the project `marketing/` folder.

### 2026-04-29 - Open Source Research

Changed files:

- `research/OPEN_SOURCE_REPO_REVIEW.md`
- `research/BUILD_PLAN.md`

What changed:

- Reviewed related Solana meme trading repositories.
- Identified Chainstack `pump-fun-bot` as the strongest near-term open-source reference.
- Identified useful future ideas:
  - holder concentration checks,
  - token risk/performance snapshots,
  - job/progress tracking,
  - prepared simulation exits,
  - direct listener comparisons,
  - gRPC parser examples.

Verification:

- Repos were cloned to `/tmp` for inspection only.
- No external repo code was copied into the project.

Remaining:

- Use open-source projects as references for clean-room implementation.

### 2026-04-29 - Manual Protection / Watchdog Visibility

Changed files:

- `core/rug_watchdog.py`
- `dashboard/dashboard.py`
- `research/BUILD_PLAN.md`

What changed:

- Added explicit watchdog alert levels:
  - `info`
  - `warning`
  - `danger`
  - `emergency`
- Improved protected-position dashboard cards with:
  - alert counts,
  - last check age,
  - last update timestamp,
  - token mechanics risk,
  - Token-2022 extensions,
  - auto-sell lock state,
  - price/liquidity metrics.
- Raised dashboard protection-check timeout from `30s` to `90s`.

Verification:

- `python3 -m py_compile dashboard/dashboard.py core/rug_watchdog.py`
- `trading_env/bin/python -m core.rug_watchdog_once`
- Dashboard returned HTTP 200.

Remaining:

- Add prepared paper/simulation exits.
- Add durable protection event logging.
- Add holder concentration checks.

### 2026-04-29 - Runtime And Data Freshness

Changed files:

- `core/data_freshness.py`
- `dashboard/dashboard.py`
- `research/DATA_SOURCE_MAP.md`
- `research/BUILD_PLAN.md`

What changed:

- Added reusable data freshness reporting.
- Surfaced per-source freshness in the Data Store panel.
- Surfaced per-source freshness in Runtime Health.

Verification:

- `python3 -m py_compile core/data_freshness.py dashboard/dashboard.py`
- Freshness report ran successfully.
- Dashboard returned HTTP 200.

Remaining:

- Decide canonical live-state source.
- Continue consolidating JSON and SQLite roles.

### 2026-04-29 - Token-2022 And Token Mechanics Risk

Changed files:

- `core/token_inspector.py`
- `core/dev_analyzer.py`
- `core/anti_rug.py`
- `core/scanner.py`
- `core/token_console.py`
- `core/rug_watchdog.py`
- `dashboard/dashboard.py`
- `research/BUILD_PLAN.md`

What changed:

- Added Token-2022 mechanics inspection.
- Integrated token mechanics risk into scanner and anti-rug decisioning.
- Kept Token-2022 itself allowed unless dangerous mechanics are present.
- Added hard-block logic for clearly dangerous mechanics.
- Added caution logic for risky/unknown mechanics.
- Added dev bonded-token reputation heuristic.
- Added mechanics snapshots for protected manual mints.

Verification:

- `python3 -m py_compile core/token_inspector.py core/dev_analyzer.py core/anti_rug.py core/scanner.py core/token_console.py core/rug_watchdog.py dashboard/dashboard.py`
- Sample token-inspector checks passed.

Remaining:

- Store full token risk/mechanics snapshots with every paper trade and skipped candidate.
- Add holder concentration checks.

### 2026-04-29 - Project Documentation

Changed files:

- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `research/SAFE_EDITING_ZONES.md`

What changed:

- Added living build plan.
- Added highlighted current working section.
- Added data source map.
- Added safe editing zones.

Verification:

- Confirmed docs exist under `research/`.

Remaining:

- Keep docs current after meaningful work.

## Notes

- Current local dashboard URL: `http://127.0.0.1:8501/`
- Current repo path: `/Users/dianeposs/Desktop/Jordan 2/meme_trader_pro`
- Current product lane: confirmation trading and protection cockpit, not blind launch sniping.

### 2026-05-06 - Native Scanner Tape Visibility

Changed files:

- `desktop_api.py`
- `tests/test_desktop_api.py`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/lib/api.test.ts`
- `apps/desktop/src/App.tsx`
- `apps/desktop/src/styles.css`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`

What changed:

- Added read-only `/api/events` endpoint backed by SQLite `events`.
- Compacted raw tracked-wallet activity into mint, wallet, buy/sell type, amount, age, and wallet score fields.
- Added native desktop "Scanner Tape" panels in Cockpit and Signals so the app shows raw wallet movement even when no token qualifies as a candidate or paper position.
- Updated hero empty-state copy to distinguish active scanner movement from missing local state.

Verification:

- `trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests.test_event_feed_compacts_recent_wallet_events tests.test_desktop_api.DesktopApiTests.test_event_feed_route_is_read_only`
- `trading_env/bin/python -m unittest discover`
- `npm test -- --run src/lib/api.test.ts`
- `npm run check`
- `npm test`
- `npm run build`
- Restarted rebuilt native app and desktop API.
- `curl http://127.0.0.1:8765/api/events?limit=3`

Remaining:

- Tune the candidate threshold separately; raw scanner activity is now visible even when no token qualifies for paper entry.

### 2026-05-06 - Scanner Tape Token Metadata

Changed files:

- `desktop_api.py`
- `tests/test_desktop_api.py`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/App.tsx`
- `apps/desktop/src/styles.css`

What changed:

- Enriched `/api/events` scanner tape rows with known token metadata from latest SQLite `token_snapshots`.
- Added a cached read-only Helius `getAsset` fallback for fresh raw wallet-event mints before they have scanner market snapshots.
- Added token name, symbol, image URL, market cap, liquidity, tx count, and holder count fields when those values are known locally.
- Updated the native scanner tape to render token images/placeholders and token names/symbols instead of only mint abbreviations.
- Kept unsafe image URLs blocked.

Verification:

- `trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests.test_event_feed_compacts_recent_wallet_events tests.test_desktop_api.DesktopApiTests.test_event_feed_rejects_unsafe_metadata_images`
- `trading_env/bin/python -m unittest discover`
- `npm run check`
- `npm test`
- `npm run build`
- Live `/api/events?limit=8` returned recent rows with symbols, names, and image URLs from metadata lookup.
- Restarted rebuilt native app; desktop API is listening on `127.0.0.1:8765`.

Remaining:

- Market cap/liquidity for very fresh raw events still depends on Dexscreener/market snapshots; Helius asset metadata covers name/symbol/image only.

### 2026-05-08 - Desktop Portfolio PnL View

Changed files:

- `apps/desktop/src/lib/trades.ts`
- `apps/desktop/src/lib/trades.test.ts`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/App.tsx`
- `apps/desktop/src/styles.css`
- `desktop_gui/index.html`
- `desktop_gui/assets/app.js`
- `desktop_gui/assets/render.js`
- `desktop_gui/assets/styles.css`
- `docs/OWNERS_MANUAL.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`

What changed:

- Added trade PnL normalization and paper-trade summary helpers.
- Added a native React Portfolio tab with total PnL, open PnL, closed PnL, trade counts, open positions, closed trades, and failed attempts.
- Added the same Portfolio-first panel to the static desktop shell served at `127.0.0.1:8765`.
- Updated owner and data-source docs so the PnL view is easy to find.

Verification:

- `npm test -- --run src/lib/trades.test.ts`
- `npm run check`
- `node --check desktop_gui/assets/render.js && node --check desktop_gui/assets/app.js`
- `npm test`
- `npm run build:web`
- `curl http://127.0.0.1:8765/` shows the Portfolio nav/button.
- `curl http://127.0.0.1:8765/assets/render.js` shows the Portfolio renderer.

Remaining:

- Refresh or reopen the desktop app/browser to load the new Portfolio panel.
- Future improvement: add filters by lane, wallet, and date range once the ledger gets large.

### 2026-05-08 - Portfolio Trade Detail Drilldown

Changed files:

- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/lib/trades.ts`
- `apps/desktop/src/lib/trades.test.ts`
- `apps/desktop/src/App.tsx`
- `apps/desktop/src/styles.css`
- `desktop_gui/assets/render.js`
- `desktop_gui/assets/styles.css`
- `docs/OWNERS_MANUAL.md`
- `research/BUILD_PLAN.md`
- `WORK_LOG.md`

What changed:

- Portfolio trade rows are now selectable.
- Added a selected-trade detail card showing MC in, MC out/current MC, entry/exit prices, liquidity, size, PnL, fees, times, reasons, wallets, and sell-event count.
- Added the same detail behavior to the static desktop shell served at `127.0.0.1:8765`.
- Added tested helpers for normalizing trade entry and exit market caps.

Verification:

- Added failing market-cap normalizer test first, then implemented helpers.
- `npm test -- --run src/lib/trades.test.ts`
- `npm run check`
- `npm test`
- `npm run build:web`
- `node --check desktop_gui/assets/render.js && node --check desktop_gui/assets/app.js`
- `curl http://127.0.0.1:8765/assets/render.js` shows the trade detail renderer and market-cap fields.

Remaining:

- Refresh the desktop browser/app to load the updated static Portfolio click behavior.

### 2026-05-08 - Winner Pattern Review And Desktop Protected Token Add

Changed files:

- `desktop_api.py`
- `tests/test_desktop_api.py`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/lib/api.test.ts`
- `apps/desktop/src/App.tsx`
- `apps/desktop/src/components/ProtectionDrilldown.tsx`
- `apps/desktop/src/styles.css`
- `desktop_gui/assets/api.js`
- `desktop_gui/assets/app.js`
- `desktop_gui/assets/render.js`
- `desktop_gui/assets/styles.css`
- `docs/OWNERS_MANUAL.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`

What changed:

- Added read-only `/api/winner-patterns` for comparing closed winners against closed losers.
- Portfolio now shows Winner Pattern Review with repeatable traits, top winners, wallet leaders, and paper-tuning actions.
- Added watch-only `POST /api/watchlist/protected-token` for adding/updating manual protected token mints from the desktop Protection tab.
- React desktop Protection tab now has an Add Protected Token form.
- Static desktop shell now has an Add Protected Token form and uses the desktop session token when present in the URL.
- Live execution and auto-sell remain locked.

Verification:

- Added failing backend tests first for winner-pattern extraction and protected-token add.
- Added failing frontend API helper tests first for the new endpoints.
- `trading_env/bin/python -m unittest tests.test_desktop_api`
- `trading_env/bin/python -m py_compile desktop_api.py`
- `npm test`
- `npm run check`
- `npm run build:web`
- `node --check desktop_gui/assets/render.js && node --check desktop_gui/assets/app.js && node --check desktop_gui/assets/api.js`
- Restarted the local desktop API on `127.0.0.1:8765` with session-token protection preserved.
- `curl http://127.0.0.1:8765/api/winner-patterns` returns the review payload.

Remaining:

- The static browser form can save only when opened with the launcher-provided `api_token` URL; otherwise the desktop API correctly rejects metadata writes.
- Future improvement: add date/lane filters to Winner Pattern Review once there are enough closed trades.

### 2026-05-08 - Desktop UI Cleanup TODOs Made Explicit

Changed files:

- `research/BUILD_PLAN.md`
- `WORK_LOG.md`

What changed:

- Added explicit Phase 9 TODOs for removing/replacing the static-shell `D/T/P/R/S` placeholder rail buttons.
- Added explicit TODOs for moving Add Social Signal / Tweet entry into the desktop Signals tab.
- Added explicit TODO to eliminate or clearly mark remaining Streamlit-only workflows as legacy/admin.

Verification:

- Documentation-only update reviewed in `research/BUILD_PLAN.md`.

Remaining:

- Implement the desktop social/tweet form and clean static-shell navigation.
### 2026-05-08 - Active GUI Revamp Plan

Current focus:

- Clean up the desktop GUI so it feels like one coherent trading cockpit instead of a mix of old prototype controls.
- Use the Axiom-style reference as the interaction target: clear top navigation, useful chart controls, readable trade/position context, no dead buttons.
- Add a working Social / Tweet input flow.
- Add real candle interval controls for selected-token monitoring: 1s, 5s, 30s, 1m.
- Keep live execution locked; this is GUI/data-entry/charting work only.

Work split:

- Lead agent: backend/API support, integration, tests, final review.
- Helper agent 1: user-level GUI audit only, no edits.
- Helper agent 2: static `desktop_gui/` shell cleanup for the browser app at `127.0.0.1:8765`.
- Helper agent 3: React/Tauri GUI parity cleanup under `apps/desktop/`.

Open risks:

- Frontend can refresh every second, but candle movement still depends on how often backend market snapshots are written for the selected token.
- Social input should save local research metadata only; it must not trigger live trading.

### 2026-05-08 - Desktop GUI Cleanup, Candle Intervals, And Social Import

Changed files:

- `desktop_api.py`
- `tests/test_desktop_api.py`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/lib/api.test.ts`
- `apps/desktop/src/App.tsx`
- `apps/desktop/src/components/LockedActions.tsx`
- `apps/desktop/src/styles.css`
- `desktop_gui/index.html`
- `desktop_gui/assets/api.js`
- `desktop_gui/assets/app.js`
- `desktop_gui/assets/render.js`
- `desktop_gui/assets/styles.css`
- `docs/OWNERS_MANUAL.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`

What changed:

- Removed static-shell placeholder rail buttons and duplicate bottom tabs.
- Replaced static-shell dead buy/sell controls with an execution-state panel that clearly says live trading is locked.
- Added 1s, 5s, 30s, and 1m chart interval controls in both static desktop shell and React/Tauri shell.
- Static shell now renders price as red/green candlesticks and liquidity as a line chart.
- Selected-token refresh is labeled and run as Auto 1s in the static shell.
- Added `POST /api/social/import` for local social/tweet research imports. It writes only to `data/social_state.json` and never triggers trades.
- Added Social / Tweet Import forms in both the static Pulse panel and React/Tauri Signals panel.
- Converted React locked action controls from disabled action buttons into status-style locked chips.
- Fixed selected-token price formatting in React so tiny prices use the token price formatter.

Verification:

- Added failing backend test first for `/api/social/import`, then implemented the endpoint.
- `trading_env/bin/python -m unittest tests.test_desktop_api`
- `trading_env/bin/python -m py_compile desktop_api.py`
- `node --check desktop_gui/assets/api.js && node --check desktop_gui/assets/app.js && node --check desktop_gui/assets/render.js`
- `npm test -- --run src/lib/api.test.ts` in `apps/desktop`
- `npm run check` in `apps/desktop`
- `npm test` in `apps/desktop`
- `npm run build:web` in `apps/desktop`
- `curl http://127.0.0.1:8765/api/health` reports execution locked with metadata token protection active.
- `curl http://127.0.0.1:8765/` shows interval controls, Auto 1s, and Execution State; old placeholder rail/bottom controls are absent.
- Restarted the local desktop API on `127.0.0.1:8765` so the new social import route is live.
- Smoked `POST /api/social/import` with the session token and confirmed `live_execution_locked=true` and `trade_triggered=false`; removed the temporary smoke row afterward.

Remaining:

- The UI now polls the selected token every second, but visible candle movement still depends on backend market snapshots being written frequently enough for the selected mint.
- Next GUI pass should keep removing or converting any remaining controls that look actionable before their backend workflows are real.
- Future social panel should show whether imported social text matched by mint, ticker, or keyword.

### 2026-05-08 - Static Desktop File-Open Guard

Changed files:

- `desktop_gui/index.html`
- `WORK_LOG.md`

What changed:

- Fixed the broken raw `file://.../desktop_gui/index.html` view by redirecting direct file opens to the served local app at `http://127.0.0.1:8765/`.
- Changed static asset references from root-absolute paths to project-relative paths so the shell does not fall back to unstyled HTML when inspected locally.

Verification:

- `node --check desktop_gui/assets/app.js && node --check desktop_gui/assets/render.js && node --check desktop_gui/assets/api.js && trading_env/bin/python -m py_compile desktop_api.py`
- Browser verification confirmed `file:///Users/dianeposs/Desktop/Jordan 2/meme_trader_pro/desktop_gui/index.html` redirects to `http://127.0.0.1:8765/`.
- Browser verification confirmed the served app shows the styled workstation, connected status, current position, axes, snapshots, and PnL.

Remaining:

- Use `http://127.0.0.1:8765/` or the double-click launcher as the app entry point; direct file opens are no longer a supported app mode.

### 2026-05-08 - Axiom-Style Chart Renderer Pass

Changed files:

- `desktop_api.py`
- `desktop_gui/index.html`
- `desktop_gui/assets/api.js`
- `desktop_gui/assets/app.js`
- `desktop_gui/assets/render.js`
- `desktop_gui/assets/styles.css`
- `desktop_gui/vendor/lightweight-charts.standalone.production.js`
- `tests/test_desktop_api.py`
- `tests/test_desktop_gui_chart.mjs`
- `docs/OWNERS_MANUAL.md`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `WORK_LOG.md`

What changed:

- Replaced the static shell's custom SVG price chart with TradingView `lightweight-charts` when available.
- Added Market Cap as the default chart metric so the selected-token chart reads more like Axiom's MarketCap/Price view.
- Kept Price and Liquidity chart modes; liquidity renders as a line and market cap/price render as real candlesticks.
- Removed the misleading close-connector line that made the chart look like random bars connected by a dotted path.
- Widened the default visible history to 500 local snapshots.
- Restarted the desktop API on `127.0.0.1:8765` with session-token protection still active.

Verification:

- Added failing tests first for `metric=market_cap` candle payloads and for the static chart using the financial chart renderer.
- `trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests.test_candles_payload_can_use_market_cap_metric tests.test_desktop_api.DesktopApiTests.test_candles_payload_can_use_liquidity_metric tests.test_desktop_api.DesktopApiTests.test_invalid_candle_metric_falls_back_to_price`
- `trading_env/bin/python -m py_compile desktop_api.py core/position_cockpit.py`
- `node tests/test_desktop_gui_chart.mjs`
- `node --check desktop_gui/assets/api.js && node --check desktop_gui/assets/app.js && node --check desktop_gui/assets/render.js && node --check desktop_gui/vendor/lightweight-charts.standalone.production.js`
- Browser verification confirmed the app is connected, using Market Cap by default, reading 500 snapshots, and rendering chart canvases without console errors.

Remaining:

- This is now a real chart renderer, but the candle quality is still limited by the backend snapshot feed. Matching Axiom exactly requires trade-stream or pool-event candles, not only periodic market snapshots.

### 2026-05-08 - Protection Form Submit Fix

Changed files:

- `desktop_api.py`
- `desktop_gui/assets/api.js`
- `desktop_gui/assets/app.js`
- `desktop_gui/assets/render.js`
- `tests/test_desktop_api.py`
- `tests/test_desktop_gui_chart.mjs`
- `WORK_LOG.md`

What changed:

- Fixed the Protection tab form being rebuilt during the 1-second selected-token refresh while the operator is typing or has pasted a CA.
- Added dirty-form detection so pasted CA text is preserved even if focus moves briefly.
- Forced form status/error rendering after submit so Add button results are visible.
- Embedded the local desktop API session token into the same-origin served HTML so `http://127.0.0.1:8765/` can save protected-token metadata without requiring a token in the visible URL.

Verification:

- `node tests/test_desktop_gui_chart.mjs && node --check desktop_gui/assets/api.js && node --check desktop_gui/assets/app.js && node --check desktop_gui/assets/render.js`
- `trading_env/bin/python -m unittest tests.test_desktop_api.DesktopApiTests.test_static_index_embeds_session_token_for_same_origin_app tests.test_desktop_api.DesktopApiTests.test_metadata_post_requires_session_token_when_configured`
- `trading_env/bin/python -m py_compile desktop_api.py`
- Browser verification confirmed pasted CA text remains after multiple auto-refresh cycles.
- Browser verification confirmed the Add button now submits and displays validation errors without a session-token failure.

Remaining:

- The broader GUI still needs a dedicated user-workflow audit pass; the Protection add flow is now fixed for the current static desktop shell.

### 2026-05-08 - GUI Stabilization Sprint: Chart And Workflow Pass

Changed files:

- `core/position_cockpit.py`
- `desktop_api.py`
- `desktop_gui/index.html`
- `desktop_gui/assets/app.js`
- `desktop_gui/assets/render.js`
- `tests/test_core_logic.py`
- `tests/test_desktop_api.py`
- `tests/test_desktop_gui_chart.mjs`
- `WORK_LOG.md`

What changed:

- Fixed `build_candles()` so the backend no longer truncates chart output to 120 candles when the GUI requests a wider 500-snapshot window.
- Fixed market-cap sparse candles to carry the previous close into the next candle open, so sampled quote movement renders as red/green movement instead of mostly flat ticks.
- Added chart-quality metadata to `/api/candles`: `sample_kind`, `quality.source_contexts`, `quality.distinct_value_count`, warning text, and `trade_stream_active=false`.
- Updated the chart label to clearly say `sampled quotes` and show a warning when the chart is not backed by a swap/tick stream.
- Fixed chart auto-refresh so the `lightweight-charts` instance is reused instead of destroyed/recreated every second; manual pan/zoom is no longer reset by normal refresh.
- Added Replay to the lower tab row so top and lower navigation match.
- Refreshed the selected-token header from fresh detail data after selected-token loads, reducing stale header/detail mismatches.
- Fixed Social/Catalysts catalyst cards so object outcomes do not render as `[object Object]`.
- Changed the Protection add form so manual amount entries are not marked simulated by default.

Helper audit findings integrated:

- Runtime helper confirmed launcher/session lifecycle can strand the GUI on an old API/token pair.
- Chart helper confirmed current local data is sampled quote/snapshot data, not swap/tick data.
- GUI helper confirmed the chart reset, stale header, duplicate nav, `[object Object]`, and Protection default issues.

Verification:

- Added failing tests first for candle output limits, sampled quote quality payloads, market-cap sparse opens, and chart refresh reuse.
- `trading_env/bin/python -m unittest tests.test_core_logic.PositionCockpitTests.test_build_candles_respects_requested_output_limit tests.test_desktop_api.DesktopApiTests.test_candles_payload_reports_sampled_quote_quality tests.test_desktop_api.DesktopApiTests.test_market_cap_candles_infer_sparse_opens_from_previous_close`
- `node tests/test_desktop_gui_chart.mjs && node --check desktop_gui/assets/app.js && node --check desktop_gui/assets/render.js && node --check desktop_gui/assets/api.js`
- Restarted the desktop API on `127.0.0.1:8765`.
- Browser smoke test confirmed the app is connected, Replay is visible in both nav areas, chart quality warning is visible, and pasted Protection CA survives refresh.

Remaining:

- True Axiom-style candles require a new `swap_ticks` pipeline from parsed pool/swap events. Existing wallet events do not include enough price/quote/signature/slot economics to reconstruct real OHLCV candles.
- Desktop launcher/session ownership needs a stabilization pass so repeated launches cannot connect the GUI to an old API process or stale token.

### 2026-05-08 - Swap Tick Execution-Price Upgrade

Changed files:

- `core/scanner.py`
- `tests/test_core_logic.py`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `docs/OWNERS_MANUAL.md`
- `WORK_LOG.md`

What changed:

- Upgraded scanner tick writes so token events now preserve same-transaction SOL/USDC/USDT quote-side deltas when available.
- `record_swap_tick_from_event()` now computes execution-price ticks from quote balance deltas first, native SOL deltas second, and market-enriched quote snapshots only as fallback.
- Pump-token tick market cap is estimated from execution price when the mint ends in `pump`, so tick-derived candles have real vertical movement instead of repeated market snapshot values.
- Restarted the paper bot/scanner in a detached `screen` session and confirmed it is writing `wallet_event_balance_delta`, `wallet_event_native_delta`, and fallback `wallet_event_market_enriched` rows.
- Confirmed the desktop API remains up on `http://127.0.0.1:8765/` and runtime is online with live execution locked.

Verification:

- `trading_env/bin/python -m unittest discover` passed 153 tests.
- `trading_env/bin/python -m py_compile core/scanner.py core/storage.py desktop_api.py` passed.
- `node --check desktop_gui/assets/api.js && node --check desktop_gui/assets/app.js && node --check desktop_gui/assets/render.js && node tests/test_desktop_gui_chart.mjs` passed.
- Live DB check confirmed recent swap ticks include balance-derived rows, for example `wallet_event_balance_delta` rows with SOL/USDC quote amounts.

Remaining:

- This is a major improvement over sampled quotes, but it is still balance-delta based. The next accuracy step is a DEX route/instruction parser so non-swap balance changes can be filtered more aggressively and pool attribution can be shown.

### 2026-05-09 - Desktop Runtime And SQLite Read Optimization

Changed files:

- `desktop_api.py`
- `core/storage.py`
- `tests/test_desktop_api.py`
- `WORK_LOG.md`

What changed:

- Added a short-lived desktop API state cache so concurrent UI panels do not repeatedly reread the same paper-trade, wallet, runtime, and settings JSON files.
- Added cache invalidation after local metadata mutations such as protected-token updates, wallet-review decisions, wallet-review apply, and social imports.
- Added SQLite read indexes for latest rows by mint/time:
  - `idx_token_snapshots_mint_time_desc`
  - `idx_swap_ticks_mint_time_id_desc`
- Applied those indexes to the existing local database after waiting for the active paper bot write lock.
- Fixed runtime summary logic so a fresh scanner heartbeat can prove websocket coverage is active. This prevents the GUI from showing `STALE` because of an old websocket keepalive detail while scanner events are actively flowing.
- Suppressed old `last_error` text for currently healthy runtime components unless the component is stale or in an error/reconnect state.
- Restarted the desktop API on `127.0.0.1:8765`; paper bot/scanner stayed running.

Verification:

- `trading_env/bin/python -m unittest discover` passed 155 tests.
- `trading_env/bin/python -m py_compile desktop_api.py core/storage.py core/scanner.py` passed.
- `node --check desktop_gui/assets/api.js && node --check desktop_gui/assets/app.js && node --check desktop_gui/assets/render.js && node tests/test_desktop_gui_chart.mjs` passed.
- API health check confirms live execution remains locked.
- Runtime overview now reports `online` with no stale components.
- Desktop API CPU dropped from roughly 88% before the SQLite/index/cache pass to roughly 6-7% afterward during the same local app/runtime workload.

Remaining:

- Keep watching CPU while the app is open for longer sessions. If it climbs again, add endpoint-level request counters and response timing to identify the next hot path.
- The next product step remains exact DEX route/instruction parsing for stronger chart and tick quality.

### 2026-05-09 - DEX Route-Gated Tick Parser

Changed files:

- `core/scanner.py`
- `tests/test_core_logic.py`
- `research/BUILD_PLAN.md`
- `research/DATA_SOURCE_MAP.md`
- `docs/OWNERS_MANUAL.md`
- `WORK_LOG.md`

What changed:

- Added known swap route program detection for Jupiter, Pump.fun/PumpSwap, Raydium AMM/CPMM/CLMM, Orca Whirlpool, Meteora DLMM, OpenBook, and Phoenix.
- Scanner token-change events now carry `dex_route_detected`, `dex_route_programs`, and `dex_route_program_ids`.
- Same-transaction SOL/USDC/USDT balance deltas are now promoted to execution-price ticks only when a known route program is present.
- Route-backed execution ticks now use `wallet_event_dex_route_delta`.
- Native SOL route-backed ticks use `wallet_event_dex_route_native_delta`.
- Events with quote deltas but no route evidence now fall back to `wallet_event_market_enriched` instead of pretending the balance movement is an exact swap execution.
- Restarted the paper bot/scanner so live ticks use the route-gated parser.

Verification:

- Added failing tests first for route metadata extraction, route-backed tick pricing, and non-route quote-delta fallback.
- `trading_env/bin/python -m unittest discover` passed 158 tests.
- `trading_env/bin/python -m py_compile core/scanner.py core/storage.py desktop_api.py` passed.
- `node --check desktop_gui/assets/api.js && node --check desktop_gui/assets/app.js && node --check desktop_gui/assets/render.js && node tests/test_desktop_gui_chart.mjs` passed.
- Runtime overview reports `online` with no stale components after scanner restart.
- Live scanner log shows route detection for Jupiter v6 and Meteora DLMM.
- Live DB check confirmed recent `wallet_event_dex_route_delta` rows, including Jupiter v6, PumpSwap, and USDC quote-side examples.

Remaining:

- Route detection is now safer than raw balance deltas, but it is still not full pool attribution. Next step is decoding route/pool accounts enough to show venue/pair attribution and filter non-swap side effects more aggressively.

### 2026-05-10 - Paper Activity Lane Trigger

Changed files:

- `core/scanner.py`
- `core/settings_manager.py`
- `tests/test_core_logic.py`
- `research/BUILD_PLAN.md`
- `research/PROJECT_STATE.md`
- `WORK_LOG.md`

What changed:

- Added a setting-backed paper activity evaluation trigger so mid-quality wallet buys can be evaluated and recorded instead of waiting only for full cluster or strong weighted-wallet triggers.
- Kept low-quality single-wallet noise out with a minimum combined-wallet score gate.
- The change only increases paper/decision visibility. Main strategy thresholds, hard-risk blocks, route feasibility checks, and live execution gating remain unchanged.
- Runtime tuning intended for the current paper run:
  - `paper_activity_evaluation_enabled=true`
  - `paper_activity_evaluation_weighted_trigger=0.8`
  - `paper_activity_evaluation_min_combined_wallet_score=45`
  - `paper_exploration_score_threshold=45`
  - `paper_exploration_min_edge_score=45`
  - `paper_exploration_size_usd=5`

Verification:

- Added failing tests first for the new scanner trigger and setting persistence.
- `trading_env/bin/python -m unittest tests.test_core_logic.ScannerCandidateFilterTests tests.test_core_logic.SettingsManagerTests tests.test_core_logic.ScannerRuntimeTests` passed 37 tests.

Remaining:

- Watch the next 30-60 minutes of paper data. The expected result is more decision-ledger activity and some small exploration samples, without claiming the main strategy is proven.

### 2026-05-10 - Swap Quote Budget Gate

Changed files:

- `core/scanner.py`
- `core/settings_manager.py`
- `core/paper_exploration.py`
- `execution/jupiter_quote.py`
- `tests/test_core_logic.py`
- `WORK_LOG.md`
- `research/BUILD_PLAN.md`

What changed:

- Added a scanner-side Swap quote quality gate so weak/mid candidates are still recorded as decisions but do not spend Jupiter Swap API calls.
- Added a per-window Swap quote request budget. The current paper run is capped at 8 Swap requests per 60 seconds.
- Saved runtime quote-gate thresholds:
  - `swap_quote_score_threshold=68`
  - `swap_quote_min_edge_score=65`
  - `swap_quote_max_requests_per_minute=8`
  - `swap_quote_budget_window_seconds=60`
- Extended Jupiter Swap cooldown after `429` from the old short default to `MEMETRADER_JUPITER_SWAP_COOLDOWN_SECONDS`, defaulting to 180 seconds.
- Prevented quote-budget/cooldown skips from being mislabeled as route-failed exploration samples. Route-failed exploration now requires an actual quote attempt, not a skipped quote.

Verification:

- Added failing tests first for setting persistence, quote quality gating, quote-budget exhaustion, scanner recording without quote calls, and exploration not sampling budget-skipped quotes.
- `./trading_env/bin/python -m unittest tests.test_core_logic tests.test_desktop_api tests.test_market_checker` passed 253 tests.
- `./trading_env/bin/python -m py_compile core/scanner.py core/settings_manager.py core/paper_exploration.py execution/jupiter_quote.py` passed.

Expected effect:

- Decision activity should remain high.
- Jupiter Swap API request rate and 429s should fall.
- Paper trades may still stay low until high-quality candidates arrive, but the bot should stop burning Swap quotes on candidates that are only useful as ledger observations.

### 2026-05-10 - Exploration Activity Threshold Tuning

Changed runtime settings:

- `swap_quote_score_threshold=58`
- `swap_quote_min_edge_score=52`
- `swap_quote_max_requests_per_minute=8`
- `paper_exploration_confirmation_score_threshold=54`
- `paper_exploration_confirmation_min_edge_score=54`
- `paper_exploration_route_failed_score_threshold=58`
- `paper_exploration_route_failed_min_edge_score=52`

What changed:

- Lowered only the exploration/quote-quality gates so near-miss candidates can generate more small paper samples.
- Left the main paper/live-quality threshold unchanged.
- Kept hard-risk, market-sanity, confirmation, route feasibility, and quote-budget protections active.

Early runtime result:

- The scanner began producing exploration-lane attempts after the change.
- At least one early exploration attempt failed at simulated buy execution, confirming the lower gate is active while still requiring execution feasibility.

### 2026-05-10 - Exploration Collection Pace Tuning

Changed runtime settings:

- `swap_quote_score_threshold=45`
- `swap_quote_min_edge_score=45`
- `paper_exploration_score_threshold=45`
- `paper_exploration_min_edge_score=45`
- `paper_exploration_confirmation_score_threshold=45`
- `paper_exploration_confirmation_min_edge_score=45`
- `paper_exploration_route_failed_score_threshold=50`
- `paper_exploration_route_failed_min_edge_score=45`

Why:

- Recent decision analysis showed the collection bottleneck was the confirmation/quote gate, not the main strategy score.
- The previous exploration settings still left nearly all near-miss candidates as skipped decisions.

Guardrails kept:

- Main-lane and live-quality thresholds were not lowered.
- Hard-risk, market-sanity, strategy-guard, route feasibility, and quote-budget controls remain active.
- Exploration samples remain tiny `$5` paper-only observations.

### 2026-05-13 - Reddit Social Collector Run

Changed files:

- `data/catalyst_cards.json`
- `data/social_state.json`
- `data/runtime_status.json`
- `/Users/dianeposs/.codex/automations/reddit-social-collector/memory.md`

What ran:

- Ran `python3 -m social.reddit_collector --subreddit SolanaMemeCoins --subreddit memecoins --limit 5`.
- Rebuilt catalyst cards with `python3 -m core.catalyst_cards`.
- Queried the desktop API helper for social freshness and lock status.

Results:

- Fetched count: `0`
- Stored count: `0`
- Collector errors: `2`
- Error detail: both subreddits hit Reddit DNS resolution failure (`nodename nor servname provided, or not known`).
- Catalyst cards rebuilt to `12` cards.
- Freshness overall: `FAIL`
- Freshness rows: `Manual Social Import = OLD`, `Catalyst Cards = FRESH`, `Reddit Collector = ERROR`
- Live execution stayed locked: `true`
- Trade triggering stayed false: `false`

Verification:

- Confirmed the collector summary reported `trade_triggered: false`.
- Confirmed `build_social_freshness_payload()` and `build_health_payload()` both still report `live_execution_locked: true`.

Remaining risk:

- Reddit collection is still blocked by local DNS resolution, so no new social events were imported this run.

### 2026-05-13 - Dock App Launcher Corrected

Changed files:

- `apps/desktop/src-tauri/src/main.rs`
- `WORK_LOG.md`

What changed:

- Confirmed `/Applications/MemeTraderPro.app` could attach to an API process whose session did not match the expected desktop app session.
- Found `/Users/dianeposs/Desktop/Jordan/meme_trader_pro` is currently a symlink to `/Users/dianeposs/Desktop/Jordan 2/meme_trader_pro`, which is why process tools show the physical `Jordan 2` path.
- Patched the Tauri launcher so it prefers the canonical project path and rejects a running API when the session token/process identity does not match.
- If a mismatched API owns `127.0.0.1:8765`, the dock app now terminates that API and starts its own matching desktop API from the project repo.
- Rebuilt the Tauri desktop app and replaced `/Applications/MemeTraderPro.app`.

Verification:

- `cargo test` in `apps/desktop/src-tauri` passed 5 tests.
- `npm run check` passed.
- `npm test` passed 47 React/TypeScript tests.
- `npm run build` produced a new `MemeTraderPro.app`.
- Relaunched `/Applications/MemeTraderPro.app`; the app is running and `http://127.0.0.1:8765/api/runtime` reports `online`.

Remaining:

- The project path should be cleaned up later so there is one clear real folder instead of a symlinked `Jordan/meme_trader_pro` path pointing to `Jordan 2/meme_trader_pro`.
