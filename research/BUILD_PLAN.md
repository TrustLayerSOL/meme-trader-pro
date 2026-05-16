# MemeTraderPro Build Plan

Last updated: 2026-05-16

## Legend

- [x] Done and usable in the current repo.
- [~] Partially done, needs hardening, wiring, or validation.
- [ ] Not started or still only a design target.

## Current Working Section

<mark>Active roadmap area: Quant Wallet Tracker V2.</mark>

<mark>Current focus: Maximize information captured from every wallet signal, no-trade decision, and paper outcome so the system becomes explainable, replayable, and measurable before adding complexity.</mark>

## Major Milestone Map

All progress reports should use this 10-stage format. Percentages are stage-level completion estimates, not whole-project completion estimates.

| Stage | Milestone | Current status | Current estimate |
| --- | --- | --- | --- |
| Stage 1 | Live Signal Foundation | Mostly completed. Wallet activity can flow into normalized events, token context, signal generation, event persistence, and replay-safe storage. | 90% |
| Stage 2 | Signal Context Layer | Underway. Rejected-signal context and decision-time safety are partially wired; accepted paper entries still need complete matching context. | 65% |
| Stage 3 | Wallet Evidence Engine | Complete as review infrastructure. The 46-wallet collection queue has been processed, evidence persistence is idempotent, and Stage 3 reports now cover readiness, recommendation buckets, lifecycle behavior, and one integrated wallet evidence scorecard. Wallet score readiness remains `0%` because outcome coverage and score-ready market context are still too thin; that is now the next data-quality queue, not a missing Stage 3 engine artifact. | 100% |
| Stage 4 | Wallet Promotion/Demotion System | Review-only scorecard consumer now exists, feeds the guarded human review/apply evidence layer, is visible through the local API/Obsidian review surface, can prepare draft-only decision records, summarizes review buckets, converts non-actionable rows into an evidence collection plan, has a read-only batch runner/API report to refresh the evidence chain, and now reduces blocker reasons into one operator-readable report. Stage 4 can classify wallets, expose the queue, draft non-approved proposed decisions, separate review buckets, identify exact next evidence steps, rerun supporting evidence reports, and explain why wallets are still blocked without auto-applying changes. Automatic trust evolution remains future work. | 85% |
| Stage 5 | Wallet Ecosystem Intelligence | Early foundation. Replay scorecards expose repeated co-entry pairs, but relationship graphs, funding overlap, and deployer-linked ecosystems are not mature yet. | 15% |
| Stage 6 | Replay Realism Layer | Complete as a conservative replay-realism contract. Replay now models latency, slippage, liquidity floors, partial-fill limits, failed-fill states, exit slippage, fixed outcome windows, and a trusted market-context gate. Data score-readiness is still blocked where historical price/liquidity/supply is missing; that is a Stage 8 validation/data-coverage problem, not permission to fake context. | 100% |
| Stage 7 | Regime Detection | Minimal foundation. Market-regime fields exist in some schemas, but regime classification is not validated or score-driving yet. | 10% |
| Stage 8 | Replay Validation + Forward Testing | Complete as a validation-loop contract. The replay summary, Stage 6 realism gate, wallet replay scorecard, wallet outcome ledger, and candidate backfill queue now cross-check each other. Proof readiness remains `0%` because known outcome, fillability, and score-ready market-context coverage are still too thin. | 100% |
| Stage 9 | Behavioral Intelligence Layer | Long-term moat, mostly future. Some co-entry evidence exists, but repeatable behavioral structures are not deeply modeled yet. | 10% |
| Stage 10 | Semi-Autonomous Risk Engine | Intentionally deferred. Do not automate risk/trust changes until evidence, replay, relationship intelligence, and validation are trustworthy. | 0% |

Current active milestone for the next implementation step:

- <mark>Stage 4 - Wallet Promotion/Demotion System: 85%</mark>

Reason:

- Stage 8 now has a complete validation-loop contract and refuses to treat incomplete evidence as proof.
- Historical replay currently has `6,042` events and `0` decision-time leakage flags.
- Stage 3 is complete as a wallet evidence engine. Stage 4 now consumes the scorecard conservatively, feeds the human decision/apply guard through `data/wallet_candidate_audit.json`, exposes that review queue through `/api/wallet-candidate-audit`, prepares draft-only review decisions through `/api/wallet-candidate-decision-prep`, summarizes the remaining review buckets through `/api/wallet-candidate-review-summary`, converts them into `/api/wallet-candidate-collection-plan`, refreshes the supporting report chain through `/api/wallet-candidate-collection-batch`, and explains the current blockers through `/api/wallet-candidate-blockers`. Current local blocker view covers `49` blocked wallets: `36` need outcomes plus market context, `9` need outcome labels, `4` need manual risk review, `5` resolved rows are excluded, `16/16` report-refresh steps passed, and `0` wallet-list changes are auto-applied. The next grounded step is targeted evidence recovery for the `36` wallets blocked on both outcome and market context.

## Layer Status Snapshot

Operator-facing layer status snapshot as of 2026-05-16:

| Layer | Status |
| --- | ---: |
| Live Data Foundation | 92% |
| Evidence Layer | 82% |
| Wallet Graph / Funding Intelligence | 96% |
| Replayable Token Timelines | 35% |
| Similar-Rug Pattern Matching | 10% |
| Alerting / Dashboard Layer | 35% |
| Validation / Proof Layer | 15% |
| Productization | 5% |

This layer view is separate from the 10-stage roadmap. Use the 10-stage roadmap for step-completion reporting, and use this layer view for product health snapshots.

## Product Goal

Turn this repo into a competitive local Solana meme wallet intelligence system focused on discovering, measuring, ranking, promoting, and demoting wallets from repeatable evidence.

The strategic lane is quant wallet tracking, not a broad trading cockpit. MemeTraderPro should help the operator understand which wallets are worth following, which wallets are noise, and which wallet behaviors actually repeat.

## Quant Wallet Tracker Refocus

The project has intentionally narrowed. The wallet tracking system is now the product center because it is the cleanest feedback loop:

- wallets are repeat actors,
- wallet behavior can be measured across many tokens,
- paper-watch outcomes can be tied back to specific wallets,
- promotion/demotion can be evidence-based,
- poor wallets can be removed without changing strategy logic.

Primary next iteration:

1. Govern research changes with `RESEARCH_RULES.md`, `SIGNAL_REGISTRY.md`, and `EXPERIMENT_LOG.md`.
2. Unify accepted-trade and rejected-signal records around one outcome schema.
3. Build a wallet-outcome ledger from unified records.
4. Define canonical wallet metrics.
5. Build `data/wallet_quant_report.json`.
6. Add a wallet quant endpoint and operator view.
7. Use runner-token discovery only as wallet intake.
8. Freeze unrelated lanes until wallet edge is measured.
9. Store replayable signal contexts for triggered and rejected signals.
10. Build no-trade/rejection reports that show whether filters protect the system or block winners.
11. Tag market regime so wallet performance can be compared across dead, runner-heavy, rug-heavy, and volatile periods.
12. Build a historical replay dataset contract so older signals and future paper signals can be compared under the same decision-time-safe schema.

PnL is useful but not the main proof yet. The first proof is a clean data loop: discovery -> observation -> outcome -> score -> tier change.

Historical testing is relevant, but only if it is treated as causal replay instead of hindsight backtesting. Historical rows must separate data known at signal time from later outcome labels, model slippage/latency/liquidity/failed-fill assumptions, and use the same schema as forward paper signals.

## Frozen Until Wallet Edge Is Measured

These lanes should receive no new feature work unless they directly support wallet evaluation:

- chart polish and Axiom-style visual work,
- broad GUI expansion,
- social/catalyst automation,
- AI decision explanations,
- Market Radar as a separate co-main strategy,
- manual protected-token workflow expansion,
- marketing assets,
- live execution wiring.

Existing code can remain in place while the project refocuses. Do not delete useful data paths until wallet quant reports and source maps replace them.

## Current Status

The project already has the core shape of a local trading cockpit:

- [x] Local launcher and double-click command entry point.
- [x] Streamlit dashboard.
- [x] Token Console.
- [x] Operator Brief.
- [x] Research folder with product, strategy, Token-2022, and state notes.
- [x] Open-source repo review for related Solana meme trading projects.
- [x] Data Store / persistence layer, including JSON state and SQLite storage support.
- [x] Paper Copy Engine foundations.
- [x] Trade Postmortem.
- [x] Execution Safety gate.
- [x] Confirmation mode.
- [x] Token-2022 mechanics inspector.
- [x] Token-2022 mechanics wired into scanner / anti-rug decisioning.
- [x] Dev bonded-token reputation heuristic integrated into dev analysis.
- [x] Per-source data freshness report surfaced in the Data Store panel.
- [x] Runtime Health includes per-source freshness summary and stale/old/missing/broken source table.
- [~] Manual protection/watchlist has alert levels and richer status cards, but paper exits, continuous lifecycle, and live auto-sell gates remain.
- [~] Wallet intelligence exists in pieces, but needs stronger scoring, labeling, and review workflows.
- [~] Live execution modules exist behind safety gates, but the product should remain paper-first until acceptance criteria are met.
- [~] Pro double-click GUI target is defined; Streamlit has the first Position Cockpit prototype, and a separate execution-locked desktop GUI foundation now exists with selected-token charting, protection detail, raw scanner tape, live scanner candidate feed, and local social import.
- [x] Native/static desktop Portfolio view surfaces total paper PnL plus readable open, closed, and failed trade ledgers with clickable trade detail cards.
- [x] Native/static desktop Portfolio view includes Winner Pattern Review for comparing big winners against losers.
- [~] Native GUI/API hardening has started: arbitrary localhost browser origins are blocked, unsafe token image URLs are rejected, desktop metadata POSTs require the session token when active, double-click now opens the packaged Tauri app when available, and the desktop shell now verifies the saved session token belongs to the currently running API process.

Current strategic correction:

- [~] The next leverage point is wallet measurement, not more feature breadth. The decision ledger remains useful only where it connects wallet signals to outcomes.
- [ ] Live/rug protection, charting, and broad GUI work are frozen unless they directly improve wallet-quality measurement.

## Operating Principles

- Paper mode first. Live execution is gated and earned through observed performance.
- Local-first memory. Alerts, tokens, wallets, paper trades, skipped candidates, protected positions, and postmortems should persist.
- Explain every action. The user should see why a token passed, failed, entered paper mode, exited, or triggered protection.
- Wallet evidence first. A wallet is promoted or demoted by repeatable behavior, not reputation or one lucky trade.
- Runner discovery is an intake source for wallets, not a separate strategy center.
- Favor exits and risk control over raw entry speed.
- Do not trust stale state. Runtime health and data freshness must be visible.
- Treat Token-2022 mechanics and authority controls as pre-entry risk inputs, not afterthoughts.

## Phase 0 - Repo Control And Documentation

Goal: make the project understandable and handoff-safe while multiple builders work in the repo.

Deliverables:

- [x] `research/` folder for state, strategy, product, and token-risk notes.
- [x] Living project state note.
- [x] Living build plan.
- [x] Root roadmap for Quant Wallet Tracker V2 governance.
- [x] Research rules for signal/filter/replay promotion.
- [x] Signal registry with decision-time safety notes.
- [x] Experiment log template and first schema experiment entry.
- [x] Add a lightweight "where data lives" reference that maps each UI panel to its source files/tables.
- [x] Add a "safe editing zones" note for future builders.

Acceptance criteria:

- A new builder can understand the current product goal, current state, and next actions in under 10 minutes.
- Build plan checkboxes are updated whenever meaningful work lands.
- Documentation clearly separates completed code from future intentions.

Next actions:

- Keep this file current after each major change.
- Keep `research/DATA_SOURCE_MAP.md` current as panels, ledgers, and tables change.

## Phase 1 - Local Launcher And Command Center

Goal: make MemeTraderPro easy to start and inspect locally.

Deliverables:

- [x] Double-click launcher command.
- [x] Streamlit dashboard entry point.
- [~] Preflight checks for env, required files, Python environment, ports, private-file permissions, and desktop API session ownership.
- [x] Runtime health view for bot/dashboard/watchdog state and source freshness.
- [x] Per-component launcher start locks to reduce duplicate service spawn races.
- [ ] Single command that starts backend, dashboard, and watchdog with clear logging.
- [ ] Graceful stop/restart controls.

Acceptance criteria:

- User can launch without terminal knowledge.
- Dashboard clearly shows whether backend loops are alive and when each feed last updated.
- Startup failures are actionable, not silent.

Next actions:

- Harden launcher preflight and status reporting.
- Add supervisor ownership for backend bot, scanner, watchdog, and wallet-discovery loops so the native app can start/stop the full paper system cleanly.
- Add process health checks for backend loop, dashboard, quote API, wallet feed, and watchdog.

## Phase 2 - Data Store And Event Memory

Goal: centralize durable state so the workstation can learn from every signal and decision.

Deliverables:

- [x] JSON state files for live state, paper trades, wallet performance, social state, settings, manual watchlist, and runtime status.
- [x] SQLite database exists.
- [~] Storage utilities and sync/backfill scripts.
- [x] Data freshness indicators per source.
- [x] Owner-only permission enforcement for `.env` and SQLite DB/WAL/SHM files.
- [~] Lock-backed JSON writes for key runtime state; paper trades, wallet performance, settings, candidate ledger, social imports, runtime status, and watchlist now use locked/atomic paths.
- [x] Open paper trades dedupe by active mint during locked state merges to reduce duplicate bot-instance opens.
- [~] Canonical decision ledger schema for every candidate: detected token, wallet/social inputs, token/holder/mechanics risk, quote/liquidity checks, rule outcomes, final action, and later paper/live-safe result.
- [~] Canonical signal context schema for wallet-triggered candidates and no-trade rows. `core/signal_context.py` now builds review-only V2 contexts for scanner/Market Radar skip paths; successful paper entries still need the same schema wired end-to-end.
- [~] Unified signal outcome schema for accepted trades, failed trades, rejected signals, skipped signals, and future replay evaluations. `research/signal_schema.py` creates comparable records but runtime persistence is not wired yet.
- [~] Wallet-outcome ledger. `wallets/wallet_outcome_ledger.py` and `utils/build_wallet_outcome_ledger.py` generate a review-only JSON ledger from current paper trades, rejection rows, and wallet-performance signal observations. `research/outcome_labeler.py` now classifies later outcomes, `research/outcome_linker.py` links signal observations to later token snapshots inside an evaluation window, and `wallets/wallet_promotion_engine.py` owns review-only promotion/demotion recommendations. Runtime persistence still needs hardening.
- [~] Wallet baseline comparison. `wallets/wallet_baseline_comparison.py` and `utils/build_wallet_baseline_comparison.py` compare `data/wallet_quant_report.json` against `data/wallet_outcome_ledger.json` and identify agreement, conflict, unconfirmed quant signals, quant-only wallets, and ledger-only wallets. Coverage improved from `28` to `251` ledger wallets; known outcome labels now exist for `1,617` wallet signal/trade observations from local snapshot evidence.
- [~] Wallet candidate audit. `wallets/wallet_candidate_audit.py` and `utils/build_wallet_candidate_audit.py` generate `data/wallet_candidate_audit.json` for snapshot-linked, replay-review, and Stage 4 promotion/demotion candidates. Current active queue has `0` promotion-review candidates, `0` demotion-review candidates, `4` risk-review-required rows, `45` insufficient-evidence rows, and `5` resolved rows. It is review-only and blocks wallet-list apply unless an explicit approved decision maps cleanly to current audit evidence. `/api/wallet-candidate-audit` exposes this queue as read-only local API data, `wallets/wallet_candidate_decision_prep.py` can prepare draft-only approval records without approving or applying them, `wallets/wallet_candidate_review_summary.py` summarizes the current review buckets, `wallets/wallet_candidate_collection_plan.py` turns the non-actionable rows into exact evidence collection steps, `utils/run_wallet_candidate_collection_batch.py` refreshes the Stage 4 evidence report chain as a read-only batch, and `wallets/wallet_candidate_blocker_reducer.py` explains the remaining blocker categories.
- [x] Historical replay dataset contract. `research/historical_replay_dataset.py` and `utils/build_historical_replay_dataset.py` create `data/historical_replay/replay_events.jsonl` from accepted trades, rejected signals, wallet observations, and later outcome labels while keeping future/outcome data outside decision context. Events declare fixed `30s`, `2m`, `5m`, and `15m` evaluation windows plus realistic slippage, latency, liquidity-floor, partial-fill, failed-fill, and exit-slippage assumptions. Current local summary has `6,042` events, `0` unsafe/leakage flags, `353` fillable-with-assumptions events, `165` liquidity-floor failures, and `5,524` unknown-liquidity events. Window outcome counts exist for each fixed horizon but remain mostly unknown after migration. This is review-only and must not feed live execution.
- [~] Wallet replay scorecard. `wallets/wallet_replay_scorecard.py` and `utils/build_wallet_replay_scorecard.py` generate `data/wallet_replay_scorecard.json` from historical replay events. The scorecard ranks wallets by fixed-window outcome coverage/performance, separates coverage from outcome quality, surfaces fillability, tracks market-regime exposure, and exposes repeated co-entry partners/pairs. `wallets/wallet_replay_review.py`, `/api/wallet-replay-review`, the Obsidian `Wallet Replay Ecosystem Review` dashboard, and `utils/sync_replay_wallet_decisions.py` now turn that scorecard into a read-only review queue with conservative machine recommendations that can be saved into `data/wallet_review_decisions.json`. Replay recommendations can now flow through `data/wallet_candidate_audit.json` and the guarded wallet-list apply tool. Current local scorecard covers `261` wallets across `6,042` replay events and reports `50` top co-entry pairs.
- [~] Wallet cycle report. `wallets/wallet_cycle_report.py` and `utils/build_wallet_cycle_report.py` generate `data/wallet_cycle_report.json` from tracked wallets, paper-watch rows, bad wallets, candidate audit, replay scorecard, review decisions, and wallet-apply audit. It gives one operator-facing summary of promoted, active, blocked, demoted, and pending-review wallet state. `/api/wallet-cycle` now exposes it as a read-only local API payload, and the Obsidian exporter renders it as `MemeTraderPro/Dashboards/Wallet Cycle Report.md`.
- [~] Wallet candidate quality report. `wallets/wallet_candidate_quality.py` and `utils/build_wallet_candidate_quality_report.py` generate `data/wallet_candidate_quality_report.json` from candidate wallets, paper-watch rows, bad wallets, and wallet behavior labels. It ranks active candidate wallets by review-only evidence quality, keeps bad-listed/blocked candidates visible but out of ranked observation, exposes `/api/wallet-candidate-quality`, and renders `MemeTraderPro/Dashboards/Wallet Candidate Quality.md` in Obsidian.
- [~] Wallet candidate quality review. `wallets/wallet_candidate_quality_review.py` and `utils/build_wallet_candidate_quality_review.py` generate `data/wallet_candidate_quality_review.json` by cross-checking top candidate-quality wallets against replay scorecard and outcome-ledger evidence. It exposes `/api/wallet-candidate-quality-review` and renders `MemeTraderPro/Dashboards/Wallet Candidate Quality Review.md`. This is review-only and cannot approve or apply wallet-list changes.
- [~] Stage 4 wallet promotion/demotion review. `wallets/wallet_stage4_review.py` and `utils/build_wallet_stage4_review.py` generate `data/reports/wallet_backfills/wallet_stage4_review_report.json` from the integrated Stage 3 wallet evidence scorecard. Current local report reviews `50` wallets: `0` promotion-review-ready, `45` hold-more-data, `4` risk-review-required, `1` demotion/block review, and `0` auto-applied changes. `wallets/wallet_candidate_audit.py` now consumes this report so Stage 4 rows can flow into the existing human decision/apply guard without auto-apply, and Obsidian candidate review notes expose Stage 4 source/action fields.
- [~] Wallet candidate evidence plan. `wallets/wallet_candidate_evidence_plan.py` and `utils/build_wallet_candidate_evidence_plan.py` generate `data/wallet_candidate_evidence_plan.json` from the candidate-quality review shortlist. It shows missing replay-known, fillable, and outcome-label counts for each high-quality candidate wallet, exposes `/api/wallet-candidate-evidence-plan`, and renders `MemeTraderPro/Dashboards/Wallet Candidate Evidence Plan.md`.
- [~] Wallet candidate backfill targets. `wallets/wallet_candidate_backfill_targets.py` and `utils/build_wallet_candidate_backfill_targets.py` generate `data/wallet_candidate_backfill_targets.json` from the evidence plan plus local historical replay events. It separates wallets that need wallet-history collection, existing replay events that need outcome labels, risk-review-first rows, and hold-for-review rows; exposes `/api/wallet-candidate-backfill-targets`; and renders `MemeTraderPro/Dashboards/Wallet Candidate Backfill Targets.md`.
- [~] Read-only wallet-history backfill. `wallets/wallet_history_backfill.py`, `wallets/wallet_history_parser.py`, `wallets/wallet_evidence_models.py`, `wallets/wallet_evidence_reporter.py`, and `utils/run_wallet_history_backfill.py` process `COLLECT_WALLET_HISTORY` candidate targets into structured wallet evidence records. Current local run processed all `46` wallet-history targets, fully collected `2`, partially collected `44`, blocked `0`, produced `745` evidence rows in the run, preserved `890` raw transactions, wrote `700` new unique evidence rows after skipping `45` duplicates, and left `39` wallets ready for candidate review under current evidence thresholds. Evidence persistence is now idempotent so repeated runs do not inflate wallet quality. It remains review-only.
- [~] Wallet evidence enrichment. `wallets/wallet_evidence_enrichment.py` and `utils/enrich_wallet_history_evidence.py` enrich wallet-history evidence with prior-only decision-time market context from SQLite `token_snapshots`/`swap_ticks` plus separate later outcome windows. Current local run processed `1,033` deduped evidence rows across `46` wallets and `91` mints, added entry context to `324`, found `24` rows with known outcomes, marked `709` rows missing market context, exposed `/api/wallet-evidence-enrichment`, and rendered `MemeTraderPro/Dashboards/Wallet Evidence Enrichment.md`. It remains review-only and cannot promote, demote, or trade.
- [~] Missing market-context targets. `wallets/wallet_missing_market_context.py` and `utils/build_wallet_missing_market_context_targets.py` generate `data/wallet_backfills/wallet_missing_market_context_report.json` from enriched wallet evidence. Current local queue has `77` target mints, `643` deduped missing-context evidence rows, and `33` affected wallets after excluding quote mints. It exposes `/api/wallet-missing-market-context` and renders `MemeTraderPro/Dashboards/Wallet Missing Market Context.md`. It remains review-only.
- [x] Migration-safe market-context recovery. `utils/recover_market_context_from_json.py` rebuilds review-only SQLite `token_snapshots` from surviving JSON/JSONL artifacts after local DB loss. Current recovered store has `1,906` recovered snapshots across `739` mints. It does not fabricate missing prices, create `swap_ticks`, promote wallets, or alter trading logic.
- [x] Historical market-context backfill checkpoint. `wallets/historical_market_context_backfill.py`, `utils/backfill_historical_market_context.py`, `wallets/missing_raw_transaction_recovery.py`, and `utils/recover_missing_raw_transactions.py` classify the remaining missing evidence against preserved raw transactions and recover exact missing raw signatures with read-only RPC. Current local run scanned `194` missing-context rows, recovered all `100` missing raw transactions, removed the missing-transaction blocker, partially recovered `108` rows from paired token/quote raw transaction deltas, and left `86` rows blocked because the transaction evidence still lacks usable quote-price deltas. This is the 100% checkpoint for the recovered-repo historical backfill lane: raw artifact recovery and honest classification are complete, but trusted USD price/liquidity snapshots and lost `swap_ticks` still cannot be assumed.
- [x] Trusted historical snapshot gate. `wallets/trusted_historical_market_snapshot_provider.py` and `utils/build_trusted_historical_market_snapshot_report.py` classify every historical backfill row for wallet-score readiness. Current local report scanned `194` rows, marked `108` as partial quote-context not score-ready, marked `86` as needing external historical market snapshots, and marked `0` as score-ready. This completes the trust-gate milestone at `100%`: unresolved rows are explicitly blocked from wallet scoring until a real historical price/liquidity/market-cap source or richer on-chain parser is added.
- [x] Historical quote-price enrichment. `wallets/historical_quote_price_enrichment.py` and `utils/enrich_historical_quote_prices.py` convert WSOL quote-per-token context into USD token price using a decision-time-safe historical SOL/USD series. Current local run used CoinGecko SOL market-chart range data and recovered USD entry price for all `108` WSOL-quoted rows. These rows remain blocked from wallet scoring because liquidity and market cap are still missing.
- [x] Home-built on-chain market-context recovery foundation. `wallets/onchain_market_context_recovery.py` and `utils/recover_onchain_market_context.py` recover historical liquidity candidates from local raw transaction token-balance evidence when a non-wallet owner has both target-token and quote-token reserves in the same transaction. Current local run scanned `194` historical rows, recovered price for `157`, recovered liquidity for `65`, and marked `65` as price+liquidity recovered but not score-ready. Market cap remains `0` because decision-time token supply is not yet present. Provider snapshots are now documented as validation/fallback only, not the long-term source of truth.
- [x] On-chain supply evidence classification. `wallets/onchain_supply_evidence.py` and `utils/build_onchain_supply_evidence.py` classify whether historical rows have decision-time token supply evidence. Current local run scanned `194` rows, recovered decimals for all `36` affected tokens, recovered supply for `0`, and marked all rows as `needs_archival_supply`. This prevents current-only or inferred supply from polluting replay scoring.
- [x] Stage 6 replay realism readiness gate. `research/replay_realism_readiness.py` and `utils/build_replay_realism_readiness.py` generate `data/reports/historical_backfill/replay_realism_readiness_report.json`. Current local report marks the Stage 6 realism contract at `100%`, with `0` unsafe replay events, live execution locked, fixed windows present, fillability classified, trusted market-context gate complete, and unsafe current-only supply rejected. It also reports `0%` data score readiness because `0/194` historical market-context rows are score-ready and historical supply remains missing. This is the intended conservative behavior: Stage 6 is complete as a realism/safety gate, while Stage 8 must improve actual historical data coverage.
- [x] Stage 8 replay validation readiness gate. `research/replay_validation_readiness.py` and `utils/build_replay_validation_readiness.py` generate `data/reports/replay_validation/stage8_validation_readiness_report.json`. Current local report marks the Stage 8 validation contract at `100%` because the replay summary, Stage 6 realism gate, wallet replay scorecard, wallet outcome ledger, and candidate backfill queue are aligned, review-only, and live-execution locked. It also reports `0%` proof readiness because only `2` known 15m outcomes exist, fillable coverage is `6%`, and score-ready historical market context remains `0%`. This is the intended conservative behavior: Stage 8 is complete as a validation loop, while Stage 3 must collect stronger wallet evidence before scores can be trusted.
- [x] Stage 3 wallet evidence readiness gate. `research/wallet_evidence_readiness.py` and `utils/build_wallet_evidence_readiness.py` generate `data/reports/wallet_backfills/wallet_evidence_readiness_report.json`. Current local report marks the Stage 3 evidence collection contract at `100%`, with all `46` wallet-history targets processed, `0` blocked wallets, `0` duplicate evidence rows, enrichment rebuilt from `1,033` evidence rows, and `39` wallets ready for candidate review. It also reports `0%` wallet score readiness because only `24` rows have known outcomes, `643` rows still need market context, `4` targets still need risk review, and trusted market-context score-ready rows remain `0`.
- [~] Wallet evidence recommendation buckets. `wallets/wallet_evidence_recommendations.py` and `utils/build_wallet_evidence_recommendations.py` generate `data/reports/wallet_backfills/wallet_evidence_recommendations_report.json` from candidate targets, wallet-history backfill results, and the Stage 3 readiness gate. Current local report reviews `50` wallets: `38` paper-watch candidates, `7` observe-more wallets, `4` risk-review wallets, and `1` hold-no-edge wallet. It auto-applies `0` changes and keeps all `50` under `do_not_promote_yet` because wallet score readiness remains `0%`.
- [~] Wallet evidence lifecycle report. `wallets/wallet_evidence_lifecycle.py` and `utils/build_wallet_evidence_lifecycle.py` generate `data/reports/wallet_backfills/wallet_evidence_lifecycle_report.json` from wallet-history evidence. Current local report processes `1,033` evidence rows into `102` wallet-token lifecycles, with `66` round trips, `17` buy-only/open-or-unseen-exit lifecycles, `19` sell-only/missing-entry lifecycles, `44` wallets with round trips, median observed hold duration of `488` seconds, and average observed hold duration of `4,335.73` seconds. It is behavioral evidence only: no PnL, price, liquidity, promotion, demotion, or execution inference.
- [x] Stage 3 wallet evidence scorecard. `wallets/wallet_evidence_scorecard.py` and `utils/build_wallet_evidence_scorecard.py` generate `data/reports/wallet_backfills/wallet_evidence_scorecard_report.json` from readiness, recommendation, lifecycle, and enrichment reports. Current local scorecard marks `stage3_engine_completion_pct` at `100`, reviews `50` wallets, allows `0` trusted promotions, keeps wallet score readiness at `0%`, and assigns explicit next actions: `36` collect outcomes plus market context, `9` collect outcome labels, `4` manual risk review, and `1` hold out of paper-watch.
- [ ] Canonical event schema for alerts, candidates, wallet actions, quote checks, paper entries/exits, watchdog triggers, and postmortems.
- [ ] Migration/backfill routine from JSON into SQLite as the source of truth.

Acceptance criteria:

- No important decision exists only in memory.
- Every candidate has one durable decision record with machine-readable reason codes, not only prose.
- Dashboard and analysis tools read from known canonical sources.
- Stale, missing, or malformed state files are surfaced in the UI.

Next actions:

- Continue wiring `core/decision_ledger.py` and SQLite-backed decision records before adding more disconnected GUI panels.
- Harden scanner skips, main paper entries, exploration entries, failed buys, exits, and postmortems around `decision_id`.
- Persist unified signal outcome records for accepted paper trades and rejected signals into a review-only ledger.
- Build the historical replay dataset contract and validator before collecting larger historical slices.
- Backfill historical replay events from local unified records, then expand to larger external historical slices only after leakage checks pass.
- Use the wallet replay scorecard and candidate audit to identify wallets and co-entry pairs with enough known/fillable replay coverage for deeper review.
- Continue cycling weak paper-watch wallets to `demote_review` only through approved decisions plus candidate-audit evidence; do not remove evidence rows silently.
- Keep `data/bad_wallets.json` as a re-entry guard for paper-watch sync so demoted wallets cannot become active observation wallets again without fresh review logic.
- Use `data/wallet_cycle_report.json` as the quick health check before deciding whether to promote, demote, or collect more wallet data.
- Use `data/wallet_candidate_quality_report.json` to triage broad candidate intake into strong observation, paper-watch review, hold review, and reject review buckets before adding more wallets.
- Use `data/wallet_candidate_quality_review.json` to separate quality-only candidates from candidates with enough replay/outcome evidence for human promotion review.
- Use `data/wallet_candidate_evidence_plan.json` as the next collection queue: prioritize high-quality wallets that need replay-known, fillable, or outcome-label coverage.
- Use `data/wallet_candidate_backfill_targets.json` to decide the exact next backfill action per candidate wallet: collect wallet history first, label existing replay outcomes, collect more replay events, or resolve risk flags.
- Use `data/wallet_backfills/wallet_history_backfill_report.json` and `data/wallet_evidence/wallet_history_evidence.jsonl` to inspect which candidate wallets now have structured transaction evidence and which still need outcome labels, price/liquidity context, or broader transaction windows.
- Use `data/wallet_backfills/wallet_evidence_enrichment_report.json` to identify which evidence mints still lack market context before trusting wallet promotion/demotion scores.
- Use `data/wallet_backfills/wallet_missing_market_context_report.json` as the exact queue for the next read-only token snapshot/swap-tick backfill.
- Use `data/reports/wallet_backfills/wallet_evidence_readiness_report.json` as the Stage 3 evidence readiness gate. If its collection contract is `100%` but wallet score readiness is `0%`, do not treat candidate-review readiness as promotion readiness; treat risk review, outcome labels, and score-ready market context as the next blockers.
- Use `data/reports/wallet_backfills/wallet_evidence_recommendations_report.json` as the Stage 3 wallet recommendation bucket report. Treat `paper_watch_candidate` as observation-only, `observe_more` as more evidence needed, `risk_review` as manual/risk blocked, `hold_no_edge` as withheld from paper-watch, and `do_not_promote_yet` as the trust gate until score-ready evidence exists.
- Use `data/reports/wallet_backfills/wallet_evidence_lifecycle_report.json` to inspect wallet buy/sell behavior without price assumptions. Treat round-trip count, hold duration, buy-only rows, sell-only rows, and net accumulation/distribution as behavioral context only until outcome labels and market context are score-ready.
- Use `data/reports/wallet_backfills/wallet_evidence_scorecard_report.json` as the Stage 3 completion artifact and Stage 4 input. It is the integrated wallet review view, but it still cannot promote wallets while `trusted_promotions_allowed` is `0` and wallet score readiness is `0%`.
- Use `data/reports/wallet_backfills/wallet_stage4_review_report.json` as the review-only Stage 4 promotion/demotion gate. It can recommend promotion review, risk review, demotion/block review, or hold-more-data, and `data/wallet_candidate_audit.json` can consume those rows as human-review evidence. It cannot auto-apply wallet-list changes.
- Use `/api/wallet-candidate-audit` or the Obsidian `WalletCandidateReviews` folder to inspect the current Stage 4-backed review queue before recording any review decision.
- Use `/api/wallet-candidate-decision-prep` or `data/reports/wallet_reviews/wallet_candidate_decision_prep.json` to inspect draft-only approval records. Proposed rows remain `approved=false` until the operator explicitly approves them through the review-decision path.
- Use `/api/wallet-candidate-review-summary` or `data/reports/wallet_reviews/wallet_candidate_review_summary.json` to see whether the current queue has actionable approvals, risk-review blockers, insufficient-evidence rows, or resolved rows.
- Use `/api/wallet-candidate-collection-plan` or `data/reports/wallet_reviews/wallet_candidate_collection_plan.json` to see the exact evidence work needed before the next promotion/demotion cycle.
- Use `/api/wallet-candidate-collection-batch` or `data/reports/wallet_reviews/wallet_candidate_collection_batch_report.json` to verify the latest read-only evidence-chain refresh before acting on Stage 4 review rows.
- Use `/api/wallet-candidate-blockers` or `data/reports/wallet_reviews/wallet_candidate_blocker_reducer.json` to see the current blocker mix before choosing the next evidence collection lane.
- Use `data/reports/historical_backfill/historical_market_context_backfill_report.json` to separate partial transaction-derived context from rows that still need trusted historical market snapshots.
- Use `data/reports/historical_backfill/missing_raw_transaction_recovery_report.json` to audit the exact read-only recovery of previously missing raw transaction signatures.
- Use `data/reports/historical_backfill/historical_quote_price_enrichment_report.json` to audit WSOL quote-to-USD conversion coverage.
- Use `data/reports/historical_backfill/onchain_market_context_recovery_report.json` to audit home-built liquidity recovery from raw transaction pool/vault balances.
- Use `data/reports/historical_backfill/onchain_supply_evidence_report.json` to audit decision-time token supply availability. It currently proves decimals are available but total supply is not present in local raw transaction artifacts.
- Use `data/reports/historical_backfill/trusted_historical_market_snapshot_report.json` to keep incomplete historical rows out of wallet scoring and to choose the next on-chain parser/supply requirement. Provider snapshots are temporary validation/fallback sources only.
- Use `data/reports/historical_backfill/replay_realism_readiness_report.json` as the Stage 6 completion gate. If its contract completion is `100%` but data score readiness is `0%`, do not treat that as a failure of the realism layer; treat it as the exact Stage 8 data-coverage queue.
- Use `data/reports/replay_validation/stage8_validation_readiness_report.json` as the Stage 8 validation-loop completion gate. If its contract completion is `100%` but proof readiness is `0%`, do not treat that as proof of strategy edge; treat it as the exact Stage 3 wallet-evidence collection queue.
- Rerun wallet outcome/replay reports after tracked-wallet changes so the next review cycle measures the refreshed wallet set.
- Reduce unknown-liquidity and unknown-window replay events by improving decision-time market context and later snapshot coverage before treating replay results as strategy evidence.
- Choose the canonical source of truth for each data class.
- Define minimum SQLite tables and backfill existing JSON.

## Phase 3 - Confirmation-Mode Paper Bot

Goal: prove the strategy in paper mode with realistic confirmation-window logic.

Deliverables:

- [x] Confirmation mode exists.
- [x] Paper trading system exists.
- [x] Dynamic position sizing foundations.
- [x] Jupiter quote checks for buy and sell feasibility.
- [~] Entry explanation and attribution to wallet signals.
- [~] Realistic slippage, fees, delay, failed fills, and quote degradation modeling.
- [ ] Confirmation window strategy tuned around roughly 30-180 seconds after launch.
- [~] Paper engine records skipped candidates and reasons, not only entered trades; native GUI now surfaces recent raw tracked-wallet events and scanner candidates from snapshots.
- [x] Native paper profitability review panel with readiness gaps, reason breakdowns, and wallet-label exposure.
- [x] Paper-only Exploration Lane for safe near-miss candidates with smaller simulated size and separate review metrics.
- [x] Exploration Lane is blocked from overriding confirmation, strategy guard, hard-risk, market-sanity, or quote gates and is explicitly marked non-live eligible.

Acceptance criteria:

- Every paper trade includes entry reason, source wallets/signals, token risk result, quote result, size, simulated fill assumptions, and exit reason.
- Every paper trade links back to the candidate decision that created it.
- The bot can run for a meaningful sample without live execution.
- The user can inspect why a promising candidate was rejected.

Next actions:

- Let main paper mode collect at least 50 closed trades, with 100 preferred, before judging profitability.
- Let Exploration Lane collect 50 closed trades for a first signal and 100-150 closed trades for useful wallet-discovery tuning.
- Use lane-specific readiness only; do not let exploration volume make the main strategy look validated.
- Harden native candidate filters for scanner skip/entry and paper lifecycle snapshot contexts.
- Split desktop API routing/projectors into smaller modules before adding more mutation surfaces.
- Build the canonical decision ledger from signal, social, wallet, risk, quote, and paper-result records.
- Add lane-separated paper reports from decision records: main, exploration, protected/manual.
- Backtest confirmation rules from `research/STRATEGY_RESEARCH.md`.

## Phase 4 - Wallet Intelligence

Goal: turn wallet tracking into a private intelligence database, not a raw follow list.

Deliverables:

- [x] Wallet tracking and real-time transaction parsing foundations.
- [x] Wallet performance file and backfill utility.
- [x] Wallet quality scoring foundations.
- [x] Wallet labeler foundation.
- [x] Watch-only candidate wallet discovery file and utility.
- [x] Native candidate-wallet review panel.
- [x] Candidate wallet review-only promotion/demotion policy.
- [~] Elite/bad wallet lists.
- [~] Paper-copy performance tracking.
- [x] Wallet promotion/demotion thresholds.
- [x] Paper-watch wallet lane.
- [x] Controlled wallet-list apply tool with backup/audit.
- [x] Wallet-list apply now requires promotion candidates to have paper-watch evidence and a promotion lifecycle recommendation.
- [x] Manual candidate-wallet review decisions.
- [x] Native guarded dry-run/apply view for approved wallet list changes.
- [x] Always-on wallet discovery scheduler.
- [x] Live paper-watch subscription reload.
- [x] Rolling 7d/30d wallet stats.
- [~] Wallet behavior labels: early buyer, late buyer, rug-exit-fast, late-exit, copy-bait, paper-profitable, high-fee churner, follower trap. Dev-adjacent still needs safer attribution.
- [x] Per-wallet postmortem rollups from paper trades.
- [x] Selected-token wallet confidence surfaced in native Details tab.
- [x] Cockpit wallet-confidence summary surfaced in native Cockpit.
- [x] Fresh wallet evidence can now be expanded through the paper-only Exploration Lane while keeping main strategy stats separate.
- [~] Wallet detail page in GUI/dashboard. Native Wallets tab shows selected wallet outcomes and postmortem summaries; deeper drilldown can still improve.
- [x] Wallet Quant Report V1 foundation.
- [x] Wallet Quant Tracker V2 behavior profile helpers for ROI, win rate, average hold duration, rug association, entry timing quality, average PnL multiple, runner/rug participation, preferred token age, preferred liquidity range, conviction sizing, relationships, coordinated entries, and review-only behavior score.
- [~] Signal context capture for wallet-triggered no-trade paths. Scanner and Market Radar skips now store structured contexts; successful paper entries still need the same schema.
- [~] Market regime tagging. Initial tags exist for strong runner, low liquidity, rug-heavy, dead market, high volatility, and unknown; thresholds should be calibrated after more forward data.

Acceptance criteria:

- A wallet is not promoted to copy/live consideration without paper sample evidence.
- Wallet stats include win rate, median hold time, drawdown after entry, realized/paper PnL, exit behavior, runner/rug participation, entry timing, liquidity preference, and known/unknown data completeness.
- The UI explains whether the wallet is a leader, exit signal, trap, or unproven source.
- Rejected and accepted wallet signals can be compared using the same signal-context schema.

Next actions:

- Wire `core.signal_context.build_signal_context` into successful paper entries and closed paper outcomes.
- Use `research.signal_schema.build_signal_outcome_record` as the comparable accepted/rejected record adapter.
- Harden `data/wallet_outcome_ledger.json`: improve later outcome labels, sample-quality gates, and baseline comparisons.
- Use no-trade rows to find filters that protect the system versus filters that reject later winners.
- Add dev-adjacent behavior attribution only after the data source is reliable enough to avoid false blame.

## Phase 5 - Token Risk And Mechanics Inspection

Goal: reject unsafe tokens before entry and explain risk in plain operator terms.

Deliverables:

- [x] Token Console.
- [x] Token-2022 mechanics inspector.
- [x] Token risk notes.
- [x] Authority and extension results integrated into scanner / anti-rug decisioning.
- [x] Dev bonded-token reputation heuristic added to dev analyzer.
- [~] Anti-rug, dev analyzer, launch age, token age, liquidity, and scoring modules.
- [~] Jupiter sell quote verification.
- [ ] Holder concentration and linked-cluster checks.
- [~] Risk severity model with hard rejects, warnings, and informational flags.

Acceptance criteria:

- Token-2022 is not rejected merely for being Token-2022.
- Permanent Delegate, non-transferable mechanics, default frozen accounts, and hostile transfer restrictions are hard rejects.
- Transfer Hook, Transfer Fee, unknown extensions, mint authority, and freeze authority create clear warnings unless route-specific rules justify them.
- Entry cannot proceed, even in future live mode, without a sell-route feasibility check.

Next actions:

- Use token snapshots to power candidate review, postmortems, and catalyst cards.
- Add holder/cluster checks where reliable data is available.

## Phase 6 - Manual Protection And Watchdog

Goal: protect manual Axiom or external trades by watching the token after the user pastes a mint.

Important architecture split:

- Pre-entry rejection is the primary rug defense. Dangerous mechanics, broken sell route, hostile holder concentration, weak liquidity, and bad dev/wallet behavior should block entry before capital is exposed.
- Fast open-position monitoring should be lightweight and focused on already-owned/paper-open tokens: price, liquidity, market cap, quote degradation, drawdown, and exit-rule state on roughly 1-second cadence when API limits permit.
- Deep watchdog inspection can remain slower because it performs heavier mint, holder, mechanics, balance, and prepared-exit checks. It is useful for context, alerts, manual protection, and postmortems, but it should not be represented as sub-second rug rescue.

Deliverables:

- [x] Manual watchlist data file.
- [~] Dashboard input/panel for token mint protection.
- [~] Alert-only protection concept.
- [~] Rug watchdog modules.
- [x] Watchdog stores Token-2022/token mechanics risk snapshots for protected mints.
- [x] Protected mints have explicit alert levels: info, warning, danger, emergency.
- [x] Dashboard protected-position cards show alert counts, last-check age, mechanics risk, extensions, auto-sell lock state, and metrics.
- [~] Real watchdog loop with visible status, last-check timestamps, and stale-run overwrite protection.
- [ ] Fast open-position monitor separated from deep watchdog inspection.
- [~] Exit advisor for protected positions.
- [x] Prepared sell intent in paper/simulation mode.
- [x] Watchdog preserves operator-owned manual protection fields during background checks.
- [x] Watchdog rejects stale protected-token updates from slower older runs.
- [x] Wallet no-balance lookup preserves manually entered token amounts.
- [x] Manual protected-position amount helper validates decimal/raw amounts and marks prepared exits ready for route checks when amount is present.
- [x] Simulated/test protected amounts are explicitly marked and surfaced separately from wallet-owned balances.
- [x] Native Protection drilldown surfaces token amount, amount source, wallet-balance status, decimals, quote/amount reason, and exit-readiness checklist.
- [x] Manual protection auto-sell persists as locked/off; future interest is stored only as `requested_auto_sell`.
- [ ] Auto-sell remains disabled until live execution gates are passed.

Acceptance criteria:

- User can paste a token mint, see it appear in the watchlist, and see current risk/protection state.
- Watchdog evaluates liquidity drain, dev/top-holder sells, route degradation, price impact explosion, and severe drawdown.
- Open-position monitor handles fast lightweight price/liquidity/quote degradation checks without waiting for deep token inspection.
- Alerts are written to durable state and visible in the dashboard.
- Auto-sell controls are clearly gated and cannot fire accidentally.

Next actions:

- Define and implement the fast monitor vs deep watchdog boundary.
- Continue hardening continuous watchdog lifecycle and launcher/process controls.
- Add locked persistence for paper trade and wallet performance writes.
- Keep auto-sell disabled until explicit live sell gates, audit records, and kill-switch behavior are complete.

## Phase 7 - Operator Review, Postmortems, And Replay

Goal: make the system improve from its own decisions.

Deliverables:

- [x] Operator Brief.
- [x] Trade Postmortem.
- [~] Performance analyzer and replay analyzer modules.
- [~] Candidate review queue. Candidate audit exists and Obsidian export now creates generated review packets; remaining work is stronger reviewed-decision validation before list mutation.
- [~] Replay visibility report for skipped/no-trade rows. `core/replay_visibility.py` and `utils/build_replay_visibility_report.py` expose triggering wallets, wallet scores, cluster composition, liquidity state, execution assumptions, market regime, and replay notes from rejection rows.
- [ ] Replay lab for passed/skipped/entered tokens.
- [ ] Strategy comparison report for confirmation rules.
- [ ] Daily operator summary.

Acceptance criteria:

- User can review what the bot saw, what it did, and what happened afterward.
- Candidate review reads from the canonical decision ledger, not scattered scanner/paper/watchdog files.
- Postmortems include entry quality, risk flags, wallet source quality, exit quality, and missed-exit notes.
- Replay can compare current rules against historical candidates without touching live state.

Next actions:

- Add decision-ledger views to dashboard/desktop GUI.
- Build daily summary from alerts, trades, watchdog events, and wallet performance.
- Wire replay visibility into successful paper entries so passed/skipped/entered tokens can be compared under one schema.
- Add causal replay slices that use only pre-signal data for entry decisions and only later data for labeled outcomes.

## Phase 8 - Execution Safety And Gated Live Trading

Goal: eventually allow live execution only after safety, observability, and paper evidence are strong.

Deliverables:

- [x] Execution Safety gate.
- [x] Execution config.
- [x] Jupiter quote integration foundations.
- [~] Execution engine exists but should remain gated.
- [ ] Dry-run/live toggle with explicit environment state.
- [ ] Max position, max daily loss, max open positions, wallet allowlist, token denylist, and kill switch.
- [ ] Separate approval flow for first live buy and first live sell.
- [ ] Live execution audit log.

Acceptance criteria before live trading:

- Paper strategy has a meaningful sample with acceptable drawdown and failure analysis.
- Paper evidence comes from lane-separated decision-ledger records, not raw trade counts alone.
- Every live order passes execution safety, token risk, quote, slippage, price impact, and size gates.
- Live mode requires deliberate user confirmation and visible armed/disarmed state.
- Kill switch can stop new buys immediately.
- Manual protection auto-sell cannot activate unless explicitly armed and logged.

Next actions:

- Keep live execution disabled by default.
- Define exact paper-performance thresholds required before live mode can be considered.
- Add audit log fields now, even while trades remain paper-only.

## Phase 9 - Pro Double-Click GUI

Goal: build one professional double-click desktop workstation. Streamlit is the current prototype surface, not a separate final GUI track.

Deliverables:

- [x] Streamlit dashboard baseline.
- [~] Token Console, Operator Brief, paper trades, wallet performance, and manual protection panels.
- [x] Axiom-style Position Cockpit foundation for open paper trades and protected manual positions.
- [x] Simulation-only add-position and exit-early action intents from the cockpit.
- [x] Non-Streamlit read-only desktop API/static GUI foundation.
- [x] Desktop GUI double-click launcher.
- [x] Selected-token charting now uses `lightweight-charts` for static/native market-cap candles, price candles, and liquidity lines.
- [~] Selected-token protection rail now surfaces locked exit/protection state in the desktop GUI.
- [~] Selected-token signal rail now surfaces local catalyst and social matches in the desktop GUI.
- [x] Native selected-token candles now use 1-second buckets with sparse-open inference for red/green candle bodies.
- [x] Native selected-token chart preserves manual zoom/pan across 1-second refreshes and supports scroll/drag/axis scaling.
- [~] Clear navigation around Command Center, Tokens, Wallets, Paper Trades, Protection, Replay, and Settings.
- [x] Removed static-shell placeholder rail buttons `D/T/P/R/S` and duplicate bottom tabs.
- [x] Clear Portfolio/PnL view showing total PnL, open PnL, closed PnL, open positions, closed trades, failed attempts, and selected-trade detail.
- [x] Desktop Protection tab can add/update manual protected token mints for watchdog review without enabling live sells.
- [x] Desktop Signals/Pulse tabs have Add Social Signal / Tweet forms backed by `POST /api/social/import`.
- [ ] Desktop should expose social/catalyst refresh status and show whether a pasted tweet matched a mint, ticker, or keyword.
- [x] Static and native selected-token chart controls support 1s, 5s, 30s, and 1m intervals.
- [x] Static desktop shell renders market cap and price as red/green candlesticks and liquidity as a line.
- [ ] Eliminate remaining Streamlit-only workflows or explicitly mark Streamlit as legacy/admin until migrated.
- [~] Consistent visual status language for healthy/warning/danger/stale states.
- [~] Read-only Ops tab now surfaces operator config, strategy thresholds, refresh timing, runtime freshness, and local log tails.
- [x] Native System tab surfaces data freshness source status, age, path, owner, and stale/missing/broken states.
- [x] Native Ops tab surfaces Helius provider health and active fallback provider while keeping live execution locked.
- [x] Helius RPC read calls used by watchdog mint/balance/holder checks now prefer Gatekeeper and fall back to standard Helius mainnet.
- [x] Public Solana RPC is available as an emergency read-only fallback after Helius Gatekeeper and standard Helius.
- [ ] Settings editor with validation.
- [~] Local logs are visible read-only in the native Ops tab; export tools remain future work.
- [ ] Job/progress monitor for long-running local actions.
- [x] Choose final app shell: Tauri + React selected for the first native shell.
- [~] Tauri + React shell exists, builds a macOS `.app`/`.dmg`, and can start/check the local read-only desktop API.
- [~] Native React shell now has selected-token chart, protection, signal/catalyst, and snapshot panels.
- [x] Native selected-token chart/detail/snapshot path refreshes every 1 second with request-overlap protection.
- [~] Native React shell now has top navigation for Cockpit, Details, Protection, Signals, Replay, and System plus readiness, paper-trade replay panels, and a filterable canonical Decision Ledger.
- [x] Native React shell now has a Portfolio tab backed by the paper-trade ledger with total/open/closed PnL, per-trade rows, and selected-trade detail.
- [~] Native React shell now has a Wallets tab backed by read-only wallet performance and tracked-wallet labels.
- [x] Native Wallets tab now supports selected-wallet drilldown with matching signals and attributed paper trades.
- [~] Native React shell now has a denser position table with token, risk, and PnL columns.
- [~] Native React shell now has a selected-position monitor, locked action console, and paper-trade lifecycle panel.
- [~] Native React shell now has a selected-token Details tab covering token mechanics, holder/dev risk, quote feasibility, and decision records.
- [~] Native React shell now has a Protection drilldown tab covering protected-token list, drawdown, quote state, holder/top-10 metrics, token mechanics, exit-readiness checklist, and locked live/auto-sell state.
- [x] Native Protection drilldown rows are selectable and update the active token inspection target.
- [x] Native Protection tab has a controlled protected-position amount editor for local metadata only: amount, decimals, raw amount, and test/simulated marker.
- [x] Desktop API supports scoped `POST /api/watchlist/protected-amount` metadata updates while keeping buys, sells, auto-sell, and live execution locked.
- [x] Native shell can read the local desktop API from local/Tauri origins via restricted read-only CORS/preflight support.
- [x] Desktop API has safe query parsing, decoded path parameters, and locked internal-error responses.
- [x] Native cockpit refresh keeps critical overview/position panels alive when optional endpoints fail.
- [~] Native cockpit layout has been tightened so the chart is the dominant first-screen element; remaining polish should focus on deeper per-wallet drilldowns, settings/logs, and panel ergonomics.
- [~] Empty/loading/error states are now present across Cockpit, Replay, Ops, System, and selected-token desktop panels; broader visual polish remains.
- [x] Replace prototype charting with a real trading chart component such as TradingView/lightweight-charts after the read-only cockpit data model is stable.
- [~] Add real swap/tick candle pipeline. SQLite `swap_ticks` storage, `/api/candles` tick-first rendering, and scanner wallet-event tick writes are now in place. The scanner now identifies known DEX/Jupiter/Pump/Raydium/Meteora/Orca/OpenBook/Phoenix route programs and only promotes same-transaction SOL/USDC/USDT balance deltas to execution-price ticks when a route is detected. Non-route balance deltas fall back to market-enriched quote ticks. Next step is deeper route-level pool attribution and stronger non-swap filtering.

Acceptance criteria:

- First screen answers: is the system alive, what needs attention, what is being watched, and what changed recently.
- Operator can inspect a token, wallet, trade, or protected position without hunting through raw files.
- Settings changes are validated and durable.

Next actions:

- Audit current dashboard panels against actual data sources.
- Visually inspect and iterate on the native Tauri shell against live local state.
- Prioritize dense, operational UI over marketing-style screens.
- Continue adding empty/error/loading states for remaining data panels as they move into the native shell.
- Run a human visual pass in the packaged app and tighten spacing/overflow issues found on real window sizes.
- Refine the native Ops panel after real operator use.
- Upgrade `Scanner.handle_event()` tick parsing from DEX-program route detection to exact route/instruction economics with pool attribution and stronger filtering of non-swap token balance changes.
- Add selected-token live market snapshot sampling if paper/watchdog/scanner snapshots are too sparse for useful 1-second candle movement.
- Continue cleaning redundant/unfinished controls in the native shell until every visible control either works or is clearly status-only.
- Keep provider strategy focused on Helius API + Gatekeeper for now; LaserStream is out of scope due to cost.
- Add per-wallet token outcome charts/hold-time stats after enough paper-trade timing data is structured.
- Later upgrade selected-token polling to WebSocket/event-driven ingestion once the live feed path is ready.
- Treat Streamlit discoveries as requirements for the final desktop GUI.

## Phase 10 - Advanced Workstation Modules

Goal: add advanced workstation modules after the core pro desktop shell is selected.

Deliverables:

- [ ] Real-time event timeline.
- [ ] Advanced wallet graph and cluster views.
- [ ] Token lifecycle replay with snapshots.
- [ ] Rule editor and strategy comparison.
- [ ] Protected position cockpit with prepared action queue.

Acceptance criteria:

- Advanced workstation modules preserve local-first operation.
- It improves speed of operator decisions without hiding risk reasoning.
- It uses the same canonical data store as the bot and dashboard.

Next actions:

- Defer advanced modules until data model, paper bot, watchdog, and live gates are mature.
- Use the Phase 9 cockpit to decide exactly what the advanced modules need.

## Decisions

- Paper trading remains the default operating mode.
- MemeTraderPro competes as a local intelligence and protection cockpit, not as the fastest Telegram sniper.
- Confirmation mode targets post-launch follow-through rather than blind launch sniping.
- Token-2022 support is required, but unsafe mechanics are rejected or warned based on severity.
- Manual protection starts alert-only/paper-exit-first; real auto-sell is future gated work.
- Live execution must be explicitly armed and safety-gated.
- Open-source Solana/meme bot repos are reference material only; reimplement useful ideas cleanly instead of cloning whole repos.
- The watchdog is not the primary defense against instant rugs. Fast rejection before entry and lightweight open-position monitoring are required before any live execution work.
- The GUI should expose the canonical decision pipeline; it should not create separate logic or separate truth.

## Assumptions

- The operator is trading Solana meme tokens and may also use external tools such as Axiom.
- Local machine operation is acceptable and desirable.
- State currently exists across JSON files and SQLite; consolidation can happen incrementally.
- Existing modules should be hardened and wired before major rewrites.
- The user values explainability and risk control over pure execution speed.

## Risks

- Stale or split state can make the dashboard show misleading counts or missing trades.
- Token collapses can happen faster than a polling watchdog can react; high-risk mechanics should be rejected before entry.
- Slow watchdog checks can create false confidence if displayed as real-time protection. Label fast monitor state and deep watchdog state separately.
- Wallets can be copy-bait or exit into followers; wallet promotion needs paper evidence.
- Live execution before enough paper evidence could lose real funds quickly.
- Overbuilding UI before canonical data is settled can create duplicated logic and confusion.
- External API limits or degraded quote/routing data can make paper/live assumptions inaccurate.

## Near-Term Priority Stack

- [ ] Wallet Quant Report V1: one generated artifact with wallet tier, sample size, behavior metrics, paper-watch evidence, recommendation, and reasons.
- [ ] Wallet Quant API endpoint for read-only review.
- [x] Wallet Replay Review API endpoint for read-only scorecard triage.
- [x] Obsidian Wallet Replay Ecosystem Review note for human review.
- [x] Replay recommendation sync into local wallet review decisions.
- [x] Wallet Cycle Report API and Obsidian note for feedback-loop health review.
- [ ] Wallet UI/report cleanup: show funnel, rankings, promotion queue, demotion queue, and wallet detail.
- [~] Runner-based wallet intake hardening: local runner/paper-winner discovery now excludes `data/bad_wallets.json` from active candidate ranking, records excluded rows under `blocked_candidates`, and surfaces `blocked_bad_wallets` in discovery status. Remaining work is stronger ranking based on forward paper outcomes, recency, and co-entry ecosystem quality.
- [ ] Wallet metric definitions: early entry, runner capture, drawdown after entry, hold time, round-trip rate, rug exposure, dead-token rate, sample quality, recency decay.
- [ ] Wallet tier history: candidate, paper-watch, promotion-review, trusted, demotion-review, blocked.
- [ ] Freeze or hide non-wallet GUI lanes so the operator is not distracted by cockpit noise.
- [~] Decision ledger remains useful only for wallet-signal lineage and outcome attribution.
- [x] Runtime health and per-source freshness indicators.
- [x] Existing wallet discovery, paper-watch, lifecycle review, guarded apply, and behavior rollups.

## Change Log

### 2026-04-29

- [x] Initial living build plan created at `research/BUILD_PLAN.md`.
- [x] Updated plan after Token-2022 mechanics wiring, dev bonded-token reputation heuristic, and protected-mint mechanics snapshots landed.
- [x] Added `research/DATA_SOURCE_MAP.md` and `research/SAFE_EDITING_ZONES.md`; Phase 0 documentation deliverables are now complete.
- [x] Added reusable data freshness reporting and surfaced it in the dashboard Data Store panel.
- [x] Surfaced per-source freshness in Runtime Health so component heartbeat and data freshness can be checked together.
- [x] Added protection alert levels and richer protected-position status details in the dashboard.
- [x] Increased dashboard protection-check timeout to fit real RPC/watchdog latency observed during verification.
- [x] Reviewed related open-source Solana meme trading repos and saved integration recommendations in `research/OPEN_SOURCE_REPO_REVIEW.md`.
- [x] Expanded open-source search; identified Chainstack pump.fun bot, transaction parsers, Shyft gRPC examples, and copy-trading stop logic as useful references.
- [x] Added highlighted Current Working Section for Phase 6 focus.
- [x] Added simulation-only prepared exit intents for protected manual positions.

### 2026-04-30

- [x] Added quote-feasibility metadata to prepared protection exits. Unknown manual balances now show `amount_missing` instead of pretending the route was checked.
- [x] Added market, mint-inspection, and quote-check timeouts to the watchdog so slow network calls do not stall the loop indefinitely.
- [x] Added optional protected-token amount, decimals, raw amount, external-position, and exit-priority capture in the dashboard manual protection form.
- [x] Wired holder concentration metrics into protected-token watchdog checks and dashboard cards.
- [x] Added SQLite `token_snapshots` storage and watchdog snapshot writes for protected-token checks.
- [x] Completed first review-remediation pass: atomic JSON helper, watchdog RPC error containment, SQLite WAL/busy timeout, wallet-aware watchlist persistence, secret redaction, stale raw-amount fix, and initial deterministic unit tests.
- [x] Added protected wallet-balance lookup via `getTokenAccountsByOwner` so quote-feasibility checks can use wallet-derived token amounts when a protected entry has a wallet address.
- [x] Extended SQLite `token_snapshots` to scanner skip/entry candidates and paper-trade lifecycle events: opened, failed, partial exit, and closed exit.
- [x] Added Data Store context/source filters for token snapshots so scanner, watchdog, and paper lifecycle records can be reviewed separately.
- [x] Added `core/catalyst_cards.py`, `data/catalyst_cards.json`, Data Store Catalyst Cards tab, freshness tracking, and unit coverage for catalyst-card generation.
- [x] Added Token Console catalyst outcome column and per-token Catalyst detail tab.
- [x] Added structured local social events with ticker/mint extraction, sentiment, bulk import, dashboard Social Catalyst Tracker, and unit coverage.
