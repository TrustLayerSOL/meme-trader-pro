# MemeTraderPro Build Plan

Last updated: 2026-05-19

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
| Stage 1 | Live Signal Foundation | Complete as a read-only foundation gate. Signal context and historical replay artifacts now cross-check at `/api/live-signal-foundation`: `6,042` signal records, `6,042` persisted replay events, `1,000` wallet observation records, `37` accepted trades, `5` failed trades, `6,000` rejected signals, `100%` source consistency, and `0` unsafe replay events. Decision-time market context coverage remains `17%`, which is a proof/data-quality blocker, not a Stage 1 foundation blocker. | 100% |
| Stage 2 | Signal Context Layer | Complete as a decision-time context contract. Rejected signals, accepted paper trades, failed paper attempts, and wallet observation records now normalize into one comparable signal outcome schema; new paper entries attach `signal_context` at entry/fail time. Historical market-context coverage remains partial and is explicitly reported as data readiness, not Stage 2 contract completion. | 100% |
| Stage 3 | Wallet Evidence Engine | Complete as review infrastructure. The 46-wallet collection queue has been processed, evidence persistence is idempotent, current forward wallet activity can now be merged into the same evidence file, and Stage 3 reports cover readiness, recommendation buckets, lifecycle behavior, and one integrated wallet evidence scorecard. Wallet score readiness is now `16%`: outcome coverage and score-ready market context have improved, but still remain too thin for trust. | 100% |
| Stage 4 | Wallet Promotion/Demotion System | Complete as a review-only promotion/demotion workflow. The scorecard consumer feeds the guarded human review/apply evidence layer, is visible through the local API/Obsidian review surface, prepares draft-only decision records, summarizes review buckets, converts non-actionable rows into an evidence collection plan, refreshes the read-only evidence chain, reduces blocker reasons, targets the largest context-recovery bucket, links local artifacts, closes out exact next actions, and now has a Stage 4 completion gate at `/api/wallet-promotion-demotion-system`. It can classify wallets, expose the queue, draft non-approved proposed decisions, separate review buckets, explain why wallets are still blocked, and prove that no auto-apply/trust mutation occurred. Automatic trust evolution remains future work. | 100% |
| Stage 5 | Wallet Ecosystem Intelligence | Complete as a review-only ecosystem intelligence layer. Repeated co-entry pairs now compile into wallet nodes, ranked relationship edges, cluster candidates, explicit relationship-source status, and a Stage 5 completion gate at `/api/wallet-ecosystem-intelligence`. Funding-overlap and deployer-linked data remain explicitly blocked until real source artifacts exist; wallet trust/list mutation remains disabled. | 100% |
| Stage 6 | Replay Realism Layer | Complete as a conservative replay-realism contract. Replay now models latency, slippage, liquidity floors, partial-fill limits, failed-fill states, exit slippage, fixed outcome windows, and a trusted market-context gate. Native-SOL pool reserve reconstruction, quote coverage, and bounded archival-supply reconstruction raised Stage 6 data score-readiness to `16%`, but historical supply/market-cap evidence remains the dominant blocker. | 100% |
| Stage 7 | Regime Detection | Complete as a review-only regime segmentation layer. Historical replay events now compile into regime rows, decision-type separation, 15m outcome breakdowns, fillability context, unknown-regime visibility, and a Stage 7 completion gate at `/api/market-regime-detection`. Current data is mostly `unknown`, so regime data readiness remains low and regime labels cannot drive wallet trust yet. | 100% |
| Stage 8 | Replay Validation + Forward Testing | Complete as a validation-loop contract. The replay summary, Stage 6 realism gate, wallet replay scorecard, wallet outcome ledger, and candidate backfill queue now cross-check each other. Proof readiness is now `11%`: known 15m outcome density is above the minimum, and the fillability evidence target is now met at `81%` vs `70%` required. Positive fills remain `52%`; the extra `29%` is useful failed-liquidity evidence, not successful execution. Market-context and archival supply coverage remain the dominant blockers. | 100% |
| Stage 9 | Behavioral Intelligence Layer | Complete as a review-only behavioral pattern layer. Stage 5 ecosystem clusters, Stage 7 regime context, and Validation / Proof limitations now join into behavioral pattern candidates at `/api/behavioral-intelligence-layer`. Behavioral trust validation checks those candidates against replay-safe proof readiness at `/api/behavioral-trust-validation`, and the Discord intelligence layer now prepares sparse review-only messages at `/api/discord-intelligence-layer` without sending by default. Current local validation marks `7` patterns reviewed, `0` trust-ready patterns, and `behavioral_trust_justified=false`. | 100% |
| Stage 10 | Semi-Autonomous Risk Engine | Intentionally deferred. Do not automate risk/trust changes until evidence, replay, relationship intelligence, and validation are trustworthy. | 0% |

Current active milestone for the next implementation step:

- <mark>Proof-readiness blocker reduction after Stage 9. Current queue is remaining decision-time market context and archival supply evidence. Known 15m outcome density has cleared the current minimum, and fillability evidence coverage is now `81%` vs the `70%` target. Positive fill rate remains `52%`, so this is evidence coverage, not profitability or desired-size execution proof. Stage 10 - Semi-Autonomous Risk Engine remains 0% and deferred.</mark>

Current wallet trust validation readiness snapshot:

- The behavioral trust validation machinery is complete as a report gate, but the current result is still negative.
- Current local report state: `behavioral_trust_justified=false`, `trust_ready_patterns=0`, `proof_readiness_pct=11`, `wallet_score_readiness_pct=16`, `score_ready_market_context_records=101`, `supply_recovered_records=60`, and `531` near-score-ready rows still blocked on missing archival supply snapshots.
- Wallet trust decisions remain blocked until replay-safe decision-time market-cap / supply evidence improves materially. This is an evidence blocker, not an infrastructure blocker.

Reason:

- Stage 8 now has a complete validation-loop contract and refuses to treat incomplete evidence as proof.
- Historical replay currently has `6,042` events and `0` decision-time leakage flags.
- Stage 2 is now complete as a context integrity contract. `research/signal_context_layer.py` and `utils/build_signal_context_layer.py` generate `data/reports/signal_context/signal_context_layer_report.json`, and `/api/signal-context-layer` exposes it read-only. Current local report normalizes `6,042` unified records: `37` accepted trades, `5` failed paper attempts, `6,000` rejected signals, and `1,000` wallet observation records. It reports `100%` Stage 2 completion, `17%` canonical context-field coverage, and `17%` decision-time market-context coverage. The low market-context coverage remains a data-quality blocker for proof, not a missing Stage 2 adapter.
- Stage 3 is complete as a wallet evidence engine. Stage 4 now consumes the scorecard conservatively, feeds the human decision/apply guard through `data/wallet_candidate_audit.json`, exposes that review queue through `/api/wallet-candidate-audit`, prepares draft-only review decisions through `/api/wallet-candidate-decision-prep`, summarizes the remaining review buckets through `/api/wallet-candidate-review-summary`, converts them into `/api/wallet-candidate-collection-plan`, refreshes the supporting report chain through `/api/wallet-candidate-collection-batch`, explains the current blockers through `/api/wallet-candidate-blockers`, targets the largest blocker through `/api/wallet-candidate-context-recovery`, links existing local artifacts for that lane through `/api/wallet-candidate-context-recovery-runner`, converts the result into exact next-action buckets through `/api/wallet-candidate-context-recovery-closeout`, and closes the whole workflow through `/api/wallet-promotion-demotion-system`. The current Stage 4 completion report is `100%`, with `54` wallets in the review pipeline, `49` collection targets, `36` remaining blocked wallets, `0` auto-applied changes, and `0` trusted promotions allowed. The Evidence Layer completion gate is now `100%` as a capture, dedupe, classification, and routing layer, with wallet score readiness at `16%`. Replayable Token Timelines are now `100%` as an inventory, classification, and routing layer: `77` target mints, `643` missing-context rows, `36` blocked wallets routed, `634` price-recovered records, `632` liquidity-recovered records, `41` prior market-cap rows, `60` recovered archival supply rows, and `101` score-ready rows. Similar-Rug Pattern Matching is now `100%` as a review/control layer: `22` confirmed rug rows, `3` confirmed rug mints, `5` rug-exposed wallets, and `643` unknown rows explicitly excluded from rug labels. Alerting / Dashboard Layer is now `100%` as an operator-status layer. Validation / Proof Layer is now `100%` as a proof-readiness checklist: it exposes `11` criteria, `11` blocked criteria, `662` known 15m outcomes, `52%` fillable rate, and `11%` proof readiness. Productization remains a read-only operator workflow and does not claim edge.
- Stage 5 is now complete as a review-only co-entry ecosystem graph. Current local report indexes `261` wallet nodes, `50` co-entry edges, `50` repeated co-entry edges, and `7` cluster candidates while keeping funding/deployer relationship sources explicitly blocked and preventing trust/list mutation.
- Stage 7 is now complete as a review-only regime segmentation layer. Current local report indexes `6,042` replay events, `1` regime row, `6,042` unknown-regime events, and `2` known 15m outcomes; regime data readiness is still `0%`, so regime labels remain blocked from wallet-trust scoring.
- Stage 9 is now complete as a review-only behavioral pattern layer. Current local report joins `7` ecosystem cluster candidates to regime/proof context, keeps dominant regime as `unknown`, and blocks behavioral score-driving, auto trust mutation, wallet-list mutation, and live execution.
- Behavioral trust validation now confirms those Stage 9 patterns are not justified for wallet trust. Current local report validates `7` behavioral pattern candidates, marks `0` trust-ready, keeps `behavioral_trust_justified=false`, and blocks trust changes because proof readiness is `11%`, wallet score readiness is still limited at `16%`, and market-context / archival-supply evidence is incomplete. Fillability evidence coverage is `81%` vs the `70%` target, but positive fills remain `52%`.
- Discord intelligence now sits inside Stage 9 as a sparse research-review layer. `research/discord_intelligence_layer.py`, `utils/build_discord_intelligence_layer.py`, `utils/dispatch_discord_intelligence.py`, and `/api/discord-intelligence-layer` prepare high-signal wallet-review, behavioral-pattern, replay-validation, regime-monitor, and evidence-milestone messages while keeping dispatch disabled by default. Dispatch now supports channel-specific local webhook routing through ignored config or env vars, requires `--send`, and records sent event IDs in an ignored local ledger to prevent duplicate reposts. The local report currently prepares `5` events, touches `5` channels, suppresses `18` raw wallet rows, highlights `81%` fillability evidence coverage, and keeps live execution locked.
- Proof-readiness blocker reduction now ranks the exact next queue at `/api/proof-readiness-blocker-reduction`: `101` score-ready market-context records, `662` known 15m outcomes vs `30` required, `81%` fillability evidence coverage vs `70%` required, `52%` positive fill rate, and `643` historical wallet-evidence context rows still needing final supply/market-cap proof. This is a queue, not trust permission.
- Score-ready market-context classification now narrows the first queue item at `/api/score-ready-market-context`: `643` rows scanned, `101` score-ready rows, `531` near-score-ready archival-supply candidates, `64` tokens needing archival supply, `30` wallets affected, `9` rows still missing price, and `2` rows still missing liquidity. This is classification/recovery only, not proof of edge.
- Archival supply recovery planning turns near-score-ready rows into `/api/archival-supply-recovery-plan` and request bundles. Current score-ready classification leaves `531` rows needing archival supply / market-cap proof, with `0` wallet trust/list mutations. This is an evidence shopping list only; it does not fetch supply, infer supply, substitute current supply, or change trust.
- Archival mint history collection now exposes `/api/archival-mint-history-collection` and prepares the `75` mint accounts for complete-history collection. The collector supports bounded execute batches, resumable signature checkpoints, raw transaction dedupe, and prior-completeness preservation so deeper runs do not erase earlier evidence. Current local pagination has checkpointed all `75` token requirements, proven `11` complete histories, preserved additional raw mint-account transactions, and left all trust/list mutation disabled. It only marks a mint complete when signature pagination reaches the end of account history or a same-mint initialization boundary is proven and all eligible decision-time transactions are preserved.
- Archival mint history progress now exposes `/api/archival-mint-history-progress`: `75` requirements scanned, `75` checkpointed tokens, `54` tokens reached their decision slot, `43` reached decision slot but not account-history start, `21` remain before decision slot, and `11` have complete histories. This is progress visibility only, not supply proof.
- Archival mint pagination planning now exposes `/api/archival-mint-pagination-plan`: `75` tokens planned, `21` continue-pagination tokens, `43` provider-recommended / history-start-not-proven tokens, and `11` complete-history tokens ready for reconstruction. `utils/run_targeted_archival_mint_pagination.py` can consume that plan, filter continue-pagination targets by min/max estimated page buckets, write a bounded filtered plan, and delegate collection to the existing mint-history collector without mutating trust or execution. The latest bucketed runs processed `20` additional target passes, preserved `3,051` raw mint-account transaction rows, moved `4` tokens from continue-pagination into provider/history-start-not-proven, proved `0` new complete histories, and kept proof readiness at `11%`. This is the next-action planner for whether to keep paginating or evaluate an archival account-state provider.
- Archival account-state provider evaluation now exposes `/api/archival-account-state-provider-evaluation`: `3` provider lanes evaluated, `1` active local lane, `1` candidate provider, `1` rejected current-only provider, and provider probe required. It rejects current account state as historical supply evidence and requires a known-slot probe before any provider import.
- Archival account-state provider probing now exposes `/api/archival-account-state-provider-probe`: `1` manual probe target selected, provider `quicknode_solana_mainnet_archive`, token `4BBPVEzF9AyVwt8Zog1z41ATKbZMVqah738sTYwvpump`, decision slot `419937176`, `0` raw responses evaluated, and `0` supply snapshot imports. It is a dry-run/manual validation harness only.
- Archival provider probe request bundling now exposes `/api/archival-account-state-provider-probe-request`: `1` request bundle prepared, token `4BBPVEzF9AyVwt8Zog1z41ATKbZMVqah738sTYwvpump`, max acceptable context slot `419937176`, `0` provider calls performed, and `0` supply snapshot imports. It provides the manual request and validation handoff without storing secrets.
- Archival mint snapshot collection now exposes `/api/archival-mint-snapshot-collection` and writes a provider-ready dry-run request manifest for the `75` token requirements. Current local dry-run prepares `550` row-level decision-slot requests across `75` tokens, leaves all `550` pending archival provider, collects `0` snapshots, and keeps `0` trust/list mutations. It only accepts provider snapshots whose response slot is at or before each candidate decision slot.
- Archival mint snapshot request bundling now exposes `/api/archival-mint-snapshot-request-bundle`: `550` pending provider requests bundled across `75` target tokens, `0` provider calls, `0` wallet-list mutations, and `0` auto trust mutations. It writes a direct JSON-RPC request packet, `6` chunked request part files capped at `100` requests each, matching response-template part files, a full-batch response template, and post-import rebuild commands without storing provider URLs or secrets.
- Provider-recommended archival request bundling now narrows the provider handoff to the `43` tokens local pagination marked as history-start-not-proven / provider-recommended. Current local run bundles `349` pending provider requests across those `43` tokens, filters out `201` lower-priority requests from the broad batch, writes `4` request chunk files and `4` matching response-template chunk files capped at `100` requests each, performs `0` provider calls, and keeps `0` wallet-list or trust mutations. This is the cheaper focused handoff before paying for or manually validating archival responses.
- Archival mint snapshot response import now exposes `/api/archival-mint-snapshot-response-import`: `550` requests scanned, `0` raw responses scanned, `0` snapshots imported, and `550` rows blocked by missing provider responses. It only imports saved historical mint-account responses with context slots at or before decision slots.
- Focused provider-recommended capture/import now has dedicated wrappers for the `349` focused requests, plus a response-part combiner and workflow status command for chunked saved responses. `python3 main.py provider-response-workflow` now reports the exact focused handoff state, missing response part files, combined raw-response status, focused import status, and next safe operator action. Current local status expects `4` focused response part files, sees `0` present, keeps `349` rows blocked by missing provider responses, and keeps all trust/execution mutation locked.
- Archival mint supply reconstruction now exposes `/api/archival-mint-supply-reconstruction` and can reconstruct supply from complete mint/burn history only. Current local reconstruction coverage has `75` requirements scanned, `11` complete-history tokens, and `64` incomplete-history tokens still blocked from replay proof.
- Current mint supply collection now writes `data/reports/historical_backfill/current_mint_supply_collection_report.json` and `current_mint_supply_snapshots.jsonl`. Current local run collected `75/75` current `getTokenSupply` snapshots after bounded retry/backoff, but current supply remains audit input only.
- Supply stability evidence now writes `data/reports/historical_backfill/supply_stability_evidence_report.json` and `supply_stability_evidence_snapshots.jsonl`. Current local run proved `11` stable-current-supply tokens and blocked `64` tokens because local mint history is not complete enough to prove no post-decision supply changes. The stable tokens overlap with already reconstructed complete-history tokens, so proof readiness did not increase.
- Archival supply evidence import now exposes `/api/archival-supply-evidence` and can consume historical mint-account snapshots, complete-history reconstruction snapshots, and stability-proven current-supply snapshots. Current local run has `591` candidate rows, `60` recovered supply rows across `11` tokens, `531` rows blocked by missing archival snapshots, `75` tokens affected, and `33` wallets affected. Score-ready rows remain limited by missing decision-time supply / market-cap proof.
- Archival supply proof export now generates the operator-facing proof-readiness outputs: `data/reports/replay_validation/archival_supply_proof_readiness_report.md`, `data/reports/historical_backfill/archival_supply_evidence_table.csv`, `data/reports/historical_backfill/archival_supply_rejected_rows.csv`, and `data/reports/replay_validation/archival_supply_proof_readiness_summary.json`. Current local export shows `550` request rows, `0` provider responses, `0` matched provider rows, `60` valid archival supply rows from local complete-history reconstruction and stability-proven supply evidence, `1,081` rejected/quarantined request-or-candidate rows across request and candidate grains, `0` rows newly upgraded from near-score-ready to score-ready, and proof readiness now `11%`.
- Stage 1 is now complete as a read-only live-signal foundation gate. Current local report cross-checks `6,042` signal records against `6,042` replay events, keeps source consistency at `100%`, records `1,000` wallet observations, and reports `0` unsafe replay events.
- Stage 10 is intentionally deferred because proof readiness is still `11%`. The next practical implementation step is not risk automation; it is archival supply / market-cap recovery for the near-score-ready rows that now have price and liquidity but still lack decision-time supply proof.

## Layer Status Snapshot

Operator-facing layer status snapshot as of 2026-05-17:

| Layer | Status |
| --- | ---: |
| Live Data Foundation | 100% |
| Evidence Layer | 100% |
| Wallet Graph / Funding Intelligence | 96% |
| Replayable Token Timelines | 100% |
| Similar-Rug Pattern Matching | 100% |
| Alerting / Dashboard Layer | 100% |
| Validation / Proof Layer | 100% |
| Productization | 100% |
| Behavioral Intelligence Layer | 100% |
| Behavioral Trust Validation Gate | 100% |
| Discord Behavioral Intelligence Layer | 100% |
| Proof Readiness Blocker Reduction Queue | 100% |
| Score-Ready Market Context Classifier | 100% |
| Archival Supply Recovery Plan | 100% |
| Archival Supply Evidence Import | 100% |

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
- [x] Signal Context Layer completion gate. `research/signal_context_layer.py` and `utils/build_signal_context_layer.py` generate `data/reports/signal_context/signal_context_layer_report.json` from unified accepted-trade, failed-trade, rejected-signal, and wallet-observation records. Current local report marks Stage 2 at `100%` as a decision-time context contract: `6,042` total records, `37` accepted trades, `5` failed paper attempts, `6,000` rejected signals, `1,000` wallet observation records, `6,042` shared-schema records, and `6,042` decision-time-safe records. New paper trades now attach `signal_context` directly at paper entry/fail time. Decision-time market-context coverage is still `17%`, so this is not proof readiness or permission to trust wallet scores.
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
- [x] Stage 1 live signal foundation gate. `research/live_signal_foundation.py` and `utils/build_live_signal_foundation.py` generate `data/reports/live_signal/live_signal_foundation_report.json` from the Signal Context Layer report and historical replay summary. Current local report marks Stage 1 at `100%` as a read-only foundation gate: `6,042` signal records, `6,042` persisted replay events, `1,000` wallet observation records, `37` accepted trade records, `5` failed trade records, `6,000` rejected signal records, `100%` source consistency, `17%` decision-time market-context coverage, `0` unsafe replay events, `0` wallet-list mutations, and `0` auto trust mutations. `/api/live-signal-foundation` exposes it as read-only. This completes Stage 1 infrastructure without claiming proof readiness or enabling execution.
- [~] Wallet-outcome ledger. `wallets/wallet_outcome_ledger.py` and `utils/build_wallet_outcome_ledger.py` generate a review-only JSON ledger from current paper trades, rejection rows, and wallet-performance signal observations. `research/outcome_labeler.py` now classifies later outcomes, `research/outcome_linker.py` links signal observations to later token snapshots inside an evaluation window, and `wallets/wallet_promotion_engine.py` owns review-only promotion/demotion recommendations. Runtime persistence still needs hardening.
- [~] Wallet baseline comparison. `wallets/wallet_baseline_comparison.py` and `utils/build_wallet_baseline_comparison.py` compare `data/wallet_quant_report.json` against `data/wallet_outcome_ledger.json` and identify agreement, conflict, unconfirmed quant signals, quant-only wallets, and ledger-only wallets. Coverage improved from `28` to `251` ledger wallets; known outcome labels now exist for `1,617` wallet signal/trade observations from local snapshot evidence.
- [~] Wallet candidate audit. `wallets/wallet_candidate_audit.py` and `utils/build_wallet_candidate_audit.py` generate `data/wallet_candidate_audit.json` for snapshot-linked, replay-review, and Stage 4 promotion/demotion candidates. Current active queue has `0` promotion-review candidates, `0` demotion-review candidates, `4` risk-review-required rows, `45` insufficient-evidence rows, and `5` resolved rows. It is review-only and blocks wallet-list apply unless an explicit approved decision maps cleanly to current audit evidence. `/api/wallet-candidate-audit` exposes this queue as read-only local API data, `wallets/wallet_candidate_decision_prep.py` can prepare draft-only approval records without approving or applying them, `wallets/wallet_candidate_review_summary.py` summarizes the current review buckets, `wallets/wallet_candidate_collection_plan.py` turns the non-actionable rows into exact evidence collection steps, `utils/run_wallet_candidate_collection_batch.py` refreshes the Stage 4 evidence report chain as a read-only batch, `wallets/wallet_candidate_blocker_reducer.py` explains the remaining blocker categories, `wallets/wallet_candidate_context_recovery_queue.py` targets the outcome/market-context recovery lane, `wallets/wallet_candidate_context_recovery_runner.py` links existing local artifacts for that lane without trust mutation, and `wallets/wallet_candidate_context_recovery_closeout.py` turns the result into exact next-action buckets.
- [x] Historical replay dataset contract. `research/historical_replay_dataset.py` and `utils/build_historical_replay_dataset.py` create `data/historical_replay/replay_events.jsonl` from accepted trades, rejected signals, wallet observations, and later outcome labels while keeping future/outcome data outside decision context. Events declare fixed `30s`, `2m`, `5m`, and `15m` evaluation windows plus realistic slippage, latency, liquidity-floor, partial-fill, failed-fill, and exit-slippage assumptions. Current local summary has `6,042` events, `0` unsafe/leakage flags, `353` fillable-with-assumptions events, `165` liquidity-floor failures, and `5,524` unknown-liquidity events. Window outcome counts exist for each fixed horizon but remain mostly unknown after migration. This is review-only and must not feed live execution.
- [~] Wallet replay scorecard. `wallets/wallet_replay_scorecard.py` and `utils/build_wallet_replay_scorecard.py` generate `data/wallet_replay_scorecard.json` from historical replay events. The scorecard ranks wallets by fixed-window outcome coverage/performance, separates coverage from outcome quality, surfaces fillability, tracks market-regime exposure, and exposes repeated co-entry partners/pairs. `wallets/wallet_replay_review.py`, `/api/wallet-replay-review`, the Obsidian `Wallet Replay Ecosystem Review` dashboard, and `utils/sync_replay_wallet_decisions.py` now turn that scorecard into a read-only review queue with conservative machine recommendations that can be saved into `data/wallet_review_decisions.json`. Replay recommendations can now flow through `data/wallet_candidate_audit.json` and the guarded wallet-list apply tool. Current local scorecard covers `261` wallets across `6,042` replay events and reports `50` top co-entry pairs.
- [x] Stage 5 wallet ecosystem intelligence. `research/wallet_ecosystem_intelligence.py` and `utils/build_wallet_ecosystem_intelligence.py` generate `data/reports/wallet_ecosystems/wallet_ecosystem_intelligence_report.json` from the wallet replay scorecard. Current local report marks Stage 5 at `100%` as a review-only ecosystem layer: `261` wallet nodes, `50` co-entry edges, `50` repeated co-entry edges, `7` cluster candidates, `33%` relationship data readiness, `0` funding-overlap records, `0` deployer-link records, `0` wallet-list mutations, and `0` auto trust mutations. `/api/wallet-ecosystem-intelligence` exposes it as read-only. This completes Stage 5 infrastructure without claiming funding/deployer intelligence exists yet.
- [x] Stage 7 market regime detection. `research/market_regime_detection.py` and `utils/build_market_regime_detection.py` generate `data/reports/market_regimes/market_regime_detection_report.json` from the historical replay dataset. Current local report marks Stage 7 at `100%` as a review-only segmentation layer: `6,042` replay events analyzed, `1` regime tag observed, `6,042` unknown-regime events, `2` known 15m outcomes, `0%` regime data readiness, and `0` wallet-list or trust mutations. `/api/market-regime-detection` exposes it as read-only. This completes Stage 7 infrastructure without allowing regime labels to drive wallet trust.
- [~] Wallet cycle report. `wallets/wallet_cycle_report.py` and `utils/build_wallet_cycle_report.py` generate `data/wallet_cycle_report.json` from tracked wallets, paper-watch rows, bad wallets, candidate audit, replay scorecard, review decisions, and wallet-apply audit. It gives one operator-facing summary of promoted, active, blocked, demoted, and pending-review wallet state. `/api/wallet-cycle` now exposes it as a read-only local API payload, and the Obsidian exporter renders it as `MemeTraderPro/Dashboards/Wallet Cycle Report.md`.
- [~] Wallet candidate quality report. `wallets/wallet_candidate_quality.py` and `utils/build_wallet_candidate_quality_report.py` generate `data/wallet_candidate_quality_report.json` from candidate wallets, paper-watch rows, bad wallets, and wallet behavior labels. It ranks active candidate wallets by review-only evidence quality, keeps bad-listed/blocked candidates visible but out of ranked observation, exposes `/api/wallet-candidate-quality`, and renders `MemeTraderPro/Dashboards/Wallet Candidate Quality.md` in Obsidian.
- [~] Wallet candidate quality review. `wallets/wallet_candidate_quality_review.py` and `utils/build_wallet_candidate_quality_review.py` generate `data/wallet_candidate_quality_review.json` by cross-checking top candidate-quality wallets against replay scorecard and outcome-ledger evidence. It exposes `/api/wallet-candidate-quality-review` and renders `MemeTraderPro/Dashboards/Wallet Candidate Quality Review.md`. This is review-only and cannot approve or apply wallet-list changes.
- [x] Stage 4 wallet promotion/demotion review. `wallets/wallet_stage4_review.py` and `utils/build_wallet_stage4_review.py` generate `data/reports/wallet_backfills/wallet_stage4_review_report.json` from the integrated Stage 3 wallet evidence scorecard. Current local report reviews `50` wallets: `0` promotion-review-ready, `45` hold-more-data, `4` risk-review-required, `1` demotion/block review, and `0` auto-applied changes. `wallets/wallet_candidate_audit.py` now consumes this report so Stage 4 rows can flow into the existing human decision/apply guard without auto-apply, and Obsidian candidate review notes expose Stage 4 source/action fields.
- [x] Stage 4 promotion/demotion completion gate. `research/wallet_promotion_demotion_system.py` and `utils/build_wallet_promotion_demotion_system.py` generate `data/reports/wallet_reviews/wallet_promotion_demotion_system_report.json` from the Stage 4 review chain. Current local report marks Stage 4 at `100%` as a review-only workflow: `54` wallets in the review pipeline, `49` collection targets, `36` context-recovery targets, `36` remaining blocked wallets, `0` auto-applied changes, and `0` trusted promotions allowed. `/api/wallet-promotion-demotion-system` exposes it as read-only. This completes the Stage 4 infrastructure without enabling automatic trust mutation.
- [~] Wallet candidate evidence plan. `wallets/wallet_candidate_evidence_plan.py` and `utils/build_wallet_candidate_evidence_plan.py` generate `data/wallet_candidate_evidence_plan.json` from the candidate-quality review shortlist. It shows missing replay-known, fillable, and outcome-label counts for each high-quality candidate wallet, exposes `/api/wallet-candidate-evidence-plan`, and renders `MemeTraderPro/Dashboards/Wallet Candidate Evidence Plan.md`.
- [~] Wallet candidate backfill targets. `wallets/wallet_candidate_backfill_targets.py` and `utils/build_wallet_candidate_backfill_targets.py` generate `data/wallet_candidate_backfill_targets.json` from the evidence plan plus local historical replay events. It separates wallets that need wallet-history collection, existing replay events that need outcome labels, risk-review-first rows, and hold-for-review rows; exposes `/api/wallet-candidate-backfill-targets`; and renders `MemeTraderPro/Dashboards/Wallet Candidate Backfill Targets.md`.
- [~] Read-only wallet-history backfill. `wallets/wallet_history_backfill.py`, `wallets/wallet_history_parser.py`, `wallets/wallet_evidence_models.py`, `wallets/wallet_evidence_reporter.py`, and `utils/run_wallet_history_backfill.py` process `COLLECT_WALLET_HISTORY` candidate targets into structured wallet evidence records. Current local run processed all `46` wallet-history targets, fully collected `2`, partially collected `44`, blocked `0`, produced `745` evidence rows in the run, preserved `890` raw transactions, wrote `700` new unique evidence rows after skipping `45` duplicates, and left `39` wallets ready for candidate review under current evidence thresholds. Evidence persistence is now idempotent so repeated runs do not inflate wallet quality. It remains review-only.
- [x] Wallet evidence outcome-density lift. `wallets/wallet_history_parser.py` now preserves same-transaction quote execution context, `utils/refresh_wallet_evidence_from_raw_transactions.py` refreshes existing evidence from preserved raw transactions, and `wallets/wallet_evidence_enrichment.py` can label buy rows from same-wallet/same-mint sell exits when both sides have compatible historical price or quote execution context. Current local reports show `383` evidence rows refreshed with quote execution context, known wallet-evidence outcomes increased from `24` to `121`, wallet score readiness increased from `2%` to `12%`, and top-level proof readiness increased from `2%` to `11%` without live execution, trust mutation, or current-price substitution.
- [~] Wallet evidence enrichment. `wallets/wallet_evidence_enrichment.py` and `utils/enrich_wallet_history_evidence.py` enrich wallet-history evidence with prior-only decision-time market context from SQLite `token_snapshots`/`swap_ticks` plus separate later outcome windows. Current local run processed `1,033` deduped evidence rows across `46` wallets and `91` mints, added entry context to `324`, found `24` rows with known outcomes, marked `709` rows missing market context, exposed `/api/wallet-evidence-enrichment`, and rendered `MemeTraderPro/Dashboards/Wallet Evidence Enrichment.md`. It remains review-only and cannot promote, demote, or trade.
- [~] Missing market-context targets. `wallets/wallet_missing_market_context.py` and `utils/build_wallet_missing_market_context_targets.py` generate `data/wallet_backfills/wallet_missing_market_context_report.json` from enriched wallet evidence. Current local queue has `77` target mints, `643` deduped missing-context evidence rows, and `33` affected wallets after excluding quote mints. It exposes `/api/wallet-missing-market-context` and renders `MemeTraderPro/Dashboards/Wallet Missing Market Context.md`. It remains review-only.
- [x] Migration-safe market-context recovery. `utils/recover_market_context_from_json.py` rebuilds review-only SQLite `token_snapshots` from surviving JSON/JSONL artifacts after local DB loss. Current recovered store has `1,906` recovered snapshots across `739` mints. It does not fabricate missing prices, create `swap_ticks`, promote wallets, or alter trading logic.
- [x] Historical market-context backfill checkpoint. `wallets/historical_market_context_backfill.py`, `utils/backfill_historical_market_context.py`, `wallets/missing_raw_transaction_recovery.py`, and `utils/recover_missing_raw_transactions.py` classify the remaining missing evidence against preserved raw transactions and recover exact missing raw signatures with read-only RPC. Current local run scanned `194` missing-context rows, recovered all `100` missing raw transactions, removed the missing-transaction blocker, partially recovered `108` rows from paired token/quote raw transaction deltas, and left `86` rows blocked because the transaction evidence still lacks usable quote-price deltas. This is the 100% checkpoint for the recovered-repo historical backfill lane: raw artifact recovery and honest classification are complete, but trusted USD price/liquidity snapshots and lost `swap_ticks` still cannot be assumed.
- [x] Trusted historical snapshot gate. `wallets/trusted_historical_market_snapshot_provider.py` and `utils/build_trusted_historical_market_snapshot_report.py` classify every historical backfill row for wallet-score readiness. Current local report scanned `194` rows, marked `108` as partial quote-context not score-ready, marked `86` as needing external historical market snapshots, and marked `0` as score-ready. This completes the trust-gate milestone at `100%`: unresolved rows are explicitly blocked from wallet scoring until a real historical price/liquidity/market-cap source or richer on-chain parser is added.
- [x] Historical quote-price enrichment. `wallets/historical_quote_price_enrichment.py` and `utils/enrich_historical_quote_prices.py` convert WSOL quote-per-token context into USD token price using a decision-time-safe historical SOL/USD series. Current local run used CoinGecko SOL market-chart range data and recovered USD entry price for all `108` WSOL-quoted rows. These rows remain blocked from wallet scoring because liquidity and market cap are still missing.
- [x] Home-built on-chain market-context recovery foundation. `wallets/onchain_market_context_recovery.py` and `utils/recover_onchain_market_context.py` recover historical liquidity candidates from local raw transaction evidence when a non-wallet owner has target-token reserves plus quote reserves in token balances or native-SOL account balances. The recovery lane now also accepts prior local token snapshots for market cap only when the snapshot timestamp is at or before the decision timestamp and inside the bounded age window. Current local run scanned `643` historical rows, recovered price for `634`, recovered liquidity for `632`, recovered market cap for `41`, and marked `41` score-ready candidates. Temporary provider-backed SOL/USD quote coverage was used only as a fallback/validation bridge; provider snapshots remain validation/fallback only, not the long-term source of truth.
- [x] On-chain supply evidence classification. `wallets/onchain_supply_evidence.py` and `utils/build_onchain_supply_evidence.py` classify whether historical rows have decision-time token supply evidence. Current local run scanned `194` rows, recovered decimals for all `36` affected tokens, recovered supply for `0`, and marked all rows as `needs_archival_supply`. This prevents current-only or inferred supply from polluting replay scoring.
- [x] Score-ready market-context classifier. `wallets/score_ready_market_context.py` and `utils/build_score_ready_market_context.py` generate `data/reports/historical_backfill/score_ready_market_context_report.json` and `data/reports/historical_backfill/score_ready_market_context_records.jsonl` from on-chain market-context recovery and archival supply evidence records. Current local report scans `643` rows, marks `101` score-ready after replay-safe mint-supply reconstruction, identifies `531` near-score-ready archival-supply candidates across `64` tokens and `30` wallets, and keeps `9` price-missing rows plus `2` liquidity-missing rows blocked. `/api/score-ready-market-context` exposes it as read-only. This narrows the next proof-readiness work without inventing supply, market cap, or wallet trust.
- [x] Archival supply recovery plan. `wallets/archival_supply_recovery_plan.py` and `utils/build_archival_supply_recovery_plan.py` generate `data/reports/historical_backfill/archival_supply_recovery_plan.json` from score-ready market-context records and preserved raw transaction history. Current local report turns the `591` near-score-ready rows into `75` token-level archival supply requirements, confirms all `591` rows have a decision slot, and affects `33` wallets. `/api/archival-supply-recovery-plan` exposes it as read-only. This is a bounded fetch plan only; it does not fetch current supply, infer supply, mutate wallet trust, or enable execution.
- [x] Archival mint history collector. `wallets/archival_mint_history_collector.py` and `utils/collect_archival_mint_history.py` generate `data/reports/historical_backfill/archival_mint_history_collection_report.json`, `data/wallet_backfills/raw_transactions/archival_mint_history_raw.jsonl`, `data/reports/historical_backfill/archival_mint_history_completeness.json`, and `data/reports/historical_backfill/archival_mint_history_signature_checkpoint.json`. Dry-run now prepares `75` mint-history targets. `--max-targets` caps execute batches, and signature checkpointing resumes deeper pagination from the prior cursor. Prior bounded execution checkpointed `3` sampled mints while correctly keeping them blocked until complete history exists. `/api/archival-mint-history-collection` exposes it as read-only. Execution is opt-in and only marks history complete when `getSignaturesForAddress` pagination reaches the end of the mint account history and every eligible transaction at or before the decision slot is fetched without budget truncation.
- [x] Archival mint history progress report. `wallets/archival_mint_history_progress.py` and `utils/build_archival_mint_history_progress.py` generate `data/reports/historical_backfill/archival_mint_history_progress_report.json` from the archival supply plan and signature checkpoint. Current local report scans `75` requirements, checkpoints all `75`, reaches decision slot for `54`, proves complete mint-account history for `11`, leaves `21` needing deeper pagination toward decision slot, and leaves `43` needing an archival account-state provider or deeper complete-history proof. `/api/archival-mint-history-progress` exposes it as read-only.
- [x] Archival mint pagination planner. `wallets/archival_mint_pagination_planner.py` and `utils/build_archival_mint_pagination_plan.py` generate `data/reports/historical_backfill/archival_mint_pagination_plan_report.json` from mint-history progress. Current local report plans `75` tokens: `11` ready for supply reconstruction, `21` continue pagination toward the decision slot, and `43` consider archival account-state provider because the decision slot was reached without full account-history proof. `/api/archival-mint-pagination-plan` exposes it as read-only. `utils/run_targeted_archival_mint_pagination.py` adds an operator-safe runner for min/max estimated-page continue-pagination subsets; latest bucketed passes processed `20` additional target passes, preserved `3,051` raw mint-account transaction rows, moved `4` tokens into the provider-recommended bucket, and completed `0` additional mint histories.
- [x] Archival account-state provider evaluation. `wallets/archival_account_state_provider_evaluation.py` and `utils/build_archival_account_state_provider_evaluation.py` generate `data/reports/historical_backfill/archival_account_state_provider_evaluation_report.json`. Current local report evaluates `3` lanes: home-built reconstruction active but incomplete, Helius current-account RPC rejected for historical supply import, and QuickNode archive marked as a candidate requiring a manual known-slot probe. `/api/archival-account-state-provider-evaluation` exposes it as read-only.
- [x] Archival account-state provider probe harness. `wallets/archival_account_state_provider_probe.py` and `utils/build_archival_account_state_provider_probe.py` generate `data/reports/historical_backfill/archival_account_state_provider_probe_report.json`. Current local report selects `1` manual probe target, token `4BBPVEzF9AyVwt8Zog1z41ATKbZMVqah738sTYwvpump` at decision slot `419937176`, provider `quicknode_solana_mainnet_archive`, and status `dry_run_probe_target_selected`. `/api/archival-account-state-provider-probe` exposes it as read-only. It preserves saved raw provider responses, rejects future-slot responses, blocks missing supply, and never imports snapshots automatically.
- [x] Archival account-state provider probe request bundle. `wallets/archival_account_state_provider_probe_request.py` and `utils/build_archival_account_state_provider_probe_request.py` generate `data/reports/historical_backfill/archival_account_state_provider_probe_request_report.json`. Current local report prepares `1` manual provider request bundle for token `4BBPVEzF9AyVwt8Zog1z41ATKbZMVqah738sTYwvpump`, decision slot `419937176`, and raw response path `data/reports/historical_backfill/raw_provider_responses/archival_account_state_provider_probe_raw.json`. `/api/archival-account-state-provider-probe-request` exposes it as read-only. It performs no provider call, stores no secret, imports no supply snapshot, and only prepares the operator handoff.
- [x] Archival mint snapshot collection source. `wallets/archival_mint_snapshot_collector.py` and `utils/collect_archival_mint_supply_snapshots.py` generate `data/reports/historical_backfill/archival_mint_supply_snapshot_collection_report.json` and optional `data/reports/historical_backfill/archival_mint_supply_snapshots.jsonl` from the archival supply recovery plan. Current local dry-run prepares `550` row-level archival mint-account requests across `75` tokens, leaves all `550` pending provider evidence, collects `0` snapshots, and exposes `/api/archival-mint-snapshot-collection` as read-only. It rejects current/too-new provider snapshots after each candidate decision slot and never mutates wallet trust, wallet lists, or execution.
- [x] Provider-recommended archival mint snapshot request bundle. `utils/build_provider_recommended_archival_mint_snapshot_request_bundle.py` reuses the archival mint snapshot request bundle with a pagination-plan allow-list. Current local report bundles `349` pending requests across the `43` tokens marked `CONSIDER_ARCHIVAL_ACCOUNT_STATE_PROVIDER`, filters out `201` broad-batch rows, writes `4` focused request chunks and `4` response-template chunks capped at `100`, performs `0` provider calls, and keeps wallet trust/list mutation locked.
- [x] Provider-recommended archival provider capture/import wrappers. `utils/capture_provider_recommended_archival_mint_supply_provider_responses.py` and `utils/import_provider_recommended_archival_mint_supply_snapshots.py` reuse the generic provider capture/import safety gates with focused defaults. Current local capture dry-run sees `4` chunks / `349` requests and performs `0` provider calls. Current focused response-part combiner can merge `provider_recommended_archival_mint_supply_batch_raw.part*.json` files into the main raw response file before import. `wallets/provider_response_workflow.py`, `utils/build_provider_response_workflow.py`, and `python3 main.py provider-response-workflow` now give a single operator status surface for missing/partial/invalid chunk files and the next safe command. Current focused import scans `349` provider-recommended requests, filters out `201` broad-batch requests, imports `0` snapshots, and blocks all rows as `missing_provider_response` until real saved responses exist.
- [x] Archival mint supply reconstruction gate. `wallets/archival_mint_supply_reconstruction.py` and `utils/reconstruct_archival_mint_supply.py` generate `data/reports/historical_backfill/archival_mint_supply_reconstruction_report.json` and optional compatible snapshots from complete mint/burn history. Current local run scans the `75` token requirements, reconstructs compatible supply snapshots for `11` complete-history tokens, and keeps `64` blocked as `incomplete_mint_history`. `/api/archival-mint-supply-reconstruction` exposes it as read-only. This gate prevents partial local raw history from being mistaken for market-cap evidence.
- [x] Current mint supply snapshot collection. `utils/collect_current_mint_supply_snapshots.py` generates `data/reports/historical_backfill/current_mint_supply_collection_report.json` and `data/reports/historical_backfill/current_mint_supply_snapshots.jsonl` from the archival supply recovery plan. Current local run collected `75/75` current `getTokenSupply` snapshots after bounded retry/backoff, but those snapshots remain audit input only until stability proof exists.
- [x] Supply stability evidence gate. `wallets/supply_stability_evidence.py` and `utils/build_supply_stability_evidence.py` generate `data/reports/historical_backfill/supply_stability_evidence_report.json` and `data/reports/historical_backfill/supply_stability_evidence_snapshots.jsonl`. Current local run proved `11` stable-current-supply tokens and blocked `64` tokens because local mint history is not complete enough to prove no post-decision supply changes. This gate allows current supply only when it is proven equivalent to decision-time supply.
- [x] Archival supply evidence import. `wallets/archival_supply_evidence.py` and `utils/build_archival_supply_evidence.py` generate `data/reports/historical_backfill/archival_supply_evidence_report.json` and `data/reports/historical_backfill/archival_supply_evidence_records.jsonl` from the archival supply recovery plan plus optional historical mint-account snapshots, local reconstruction snapshots, and stability-proven current-supply snapshots. Current local report scans `591` candidate rows, recovers `60` replay-safe supply rows across `11` tokens, blocks `531` as `missing_archival_snapshot`, and affects `75` tokens / `33` wallets. `/api/archival-supply-evidence` exposes it as read-only. The score-ready classifier consumes recovered archival supply records when they exist and recomputes market cap from decision-time price times historical supply.
- [x] Stage 6 replay realism readiness gate. `research/replay_realism_readiness.py` and `utils/build_replay_realism_readiness.py` generate `data/reports/historical_backfill/replay_realism_readiness_report.json`. Current local report marks the Stage 6 realism contract at `100%`, with `0` unsafe replay events, live execution locked, fixed windows present, fillability classified, score-ready market-context classification complete, and unsafe current-only supply rejected. It now reports `16%` data score readiness because `101/643` historical market-context rows are score-ready and `60/591` archival supply rows are recovered. This is the intended conservative behavior: Stage 6 is complete as a realism/safety gate, while Stage 8 must improve actual historical data coverage.
- [x] Stage 8 replay validation readiness gate. `research/replay_validation_readiness.py` and `utils/build_replay_validation_readiness.py` generate `data/reports/replay_validation/stage8_validation_readiness_report.json`. Current local report marks the Stage 8 validation contract at `100%` because the replay summary, Stage 6 realism gate, wallet replay scorecard, wallet outcome ledger, and candidate backfill queue are aligned, review-only, and live-execution locked. It now reports `11%` Stage 8 proof readiness with `662` known 15m outcomes, `81%` fillability evidence coverage, `52%` positive fill rate, `29%` failed-liquidity evidence, `19%` unknown-liquidity rows, and `16%` data score readiness. Failed-liquidity rows count as evidence because they prove a trade would not realistically fill; they do not count as positive fills.
- [x] Stage 3 wallet evidence readiness gate. `research/wallet_evidence_readiness.py` and `utils/build_wallet_evidence_readiness.py` generate `data/reports/wallet_backfills/wallet_evidence_readiness_report.json`. Current local report marks the Stage 3 evidence collection contract at `100%`, with all `46` wallet-history targets processed, `0` blocked wallets, `0` duplicate evidence rows, enrichment rebuilt from `1,103` evidence rows, and `39` wallets ready for candidate review. It also reports `16%` wallet score readiness, `191` rows with known outcomes, `324` rows with entry context, `101` score-ready market-context records, `61` unique wallets, and `133` unique mints. Forward/current rows remain review-only until later outcomes mature.
- [~] Wallet evidence recommendation buckets. `wallets/wallet_evidence_recommendations.py` and `utils/build_wallet_evidence_recommendations.py` generate `data/reports/wallet_backfills/wallet_evidence_recommendations_report.json` from candidate targets, wallet-history backfill results, and the Stage 3 readiness gate. Current local report reviews `50` wallets: `38` paper-watch candidates, `7` observe-more wallets, `4` risk-review wallets, and `1` hold-no-edge wallet. It auto-applies `0` changes and keeps all `50` under `do_not_promote_yet` because wallet score readiness remains `0%`.
- [~] Wallet evidence lifecycle report. `wallets/wallet_evidence_lifecycle.py` and `utils/build_wallet_evidence_lifecycle.py` generate `data/reports/wallet_backfills/wallet_evidence_lifecycle_report.json` from wallet-history evidence. Current local report processes `1,033` evidence rows into `102` wallet-token lifecycles, with `66` round trips, `17` buy-only/open-or-unseen-exit lifecycles, `19` sell-only/missing-entry lifecycles, `44` wallets with round trips, median observed hold duration of `488` seconds, and average observed hold duration of `4,335.73` seconds. It is behavioral evidence only: no PnL, price, liquidity, promotion, demotion, or execution inference.
- [x] Stage 3 wallet evidence scorecard. `wallets/wallet_evidence_scorecard.py` and `utils/build_wallet_evidence_scorecard.py` generate `data/reports/wallet_backfills/wallet_evidence_scorecard_report.json` from readiness, recommendation, lifecycle, and enrichment reports. Current local scorecard marks `stage3_engine_completion_pct` at `100`, reviews `50` wallets, allows `0` trusted promotions, keeps wallet score readiness at `16%`, and assigns explicit next actions: `36` collect outcomes plus market context, `9` collect outcome labels, `4` manual risk review, and `1` hold out of paper-watch.
- [x] Evidence Layer completion gate. `research/evidence_layer_completion.py` and `utils/build_evidence_layer_completion.py` generate `data/reports/wallet_backfills/evidence_layer_completion_report.json` from the wallet evidence readiness report, Stage 3 scorecard, and Stage 4 context recovery closeout. Current local report marks the Evidence Layer at `100%` because the evidence rows are present, deduped, classified, and routed into explicit next actions. It also reports `16%` wallet score readiness, `36` remaining blocked wallets, `36` outcome-label blockers, `32` market-context blockers, `0` transaction-linkage blockers, `101` score-ready market-context records, and `0` trusted promotions. This is a measurement/completion gate only; it never promotes, demotes, mutates wallet lists, or trades. `/api/evidence-layer-completion` exposes it as a read-only payload.
- [x] Replayable Token Timelines completion gate. `research/replayable_token_timelines.py` and `utils/build_replayable_token_timelines.py` generate `data/reports/historical_backfill/replayable_token_timelines_report.json` from the Evidence Layer closeout, Stage 4 context-recovery closeout, missing market-context targets, on-chain market-context recovery, score-ready market-context classification, archival supply evidence, Stage 6 readiness, and Stage 8 readiness. Current local report marks Replayable Token Timelines at `100%` as an inventory/classification/routing layer: `77` target mints, `643` missing-context rows, `36` blocked wallets routed, `32` wallets needing market context, `36` wallets needing outcome labels, `0` transaction-linkage blockers, `634` price-recovered rows, `632` liquidity-recovered rows, `41` prior market-cap rows, `60` recovered archival supply rows, `101` score-ready rows, and `11%` timeline data readiness. `/api/replayable-token-timelines` exposes it as read-only. This does not make wallet scores trusted.
- [x] Similar-Rug Pattern Matching gate. `research/similar_rug_patterns.py` and `utils/build_similar_rug_patterns.py` generate `data/reports/historical_backfill/similar_rug_patterns_report.json` from enriched wallet evidence, the wallet outcome ledger, wallet replay scorecard, and replayable token timelines. Current local report marks Similar-Rug Pattern Matching at `100%` as a review/control layer: `22` confirmed rug rows, `3` confirmed rug mints, `5` rug-exposed wallets, and `643` unknown rows explicitly excluded from rug labels. Rug-pattern data readiness remains `0%` because timeline data readiness is still `0%`. `/api/similar-rug-patterns` exposes it as read-only. This cannot auto-demote wallets, mutate wallet lists, or trade.
- [x] Alerting / Dashboard Layer gate. `research/alerting_dashboard_layer.py` and `utils/build_alerting_dashboard_layer.py` generate `data/reports/dashboard/alerting_dashboard_layer_report.json` from Evidence Layer, Replayable Token Timelines, and Similar-Rug Pattern Matching reports. Current local report marks Alerting / Dashboard Layer at `100%` as an operator-status layer: `3` completed upstream gates, `3` status cards, `12` visible blocker categories, and `0%` research data readiness. `/api/alerting-dashboard-layer` exposes it as read-only. This does not add strategy logic, auto-promote wallets, mutate wallet lists, trade, or prove edge.
- [x] Validation / Proof Layer gate. `research/validation_proof_layer.py` and `utils/build_validation_proof_layer.py` generate `data/reports/replay_validation/validation_proof_layer_report.json` from the Alerting / Dashboard Layer report and Stage 8 validation readiness report. Current local report marks Validation / Proof Layer at `100%` as a proof-readiness checklist: `11` proof criteria, blocked criteria remain, `662` known 15m outcomes, `81%` Stage 8 fillability evidence coverage, `52%` positive fill rate, `16%` Stage 8 data score readiness, and `11%` top-level proof readiness. `/api/validation-proof-layer` exposes it as read-only. This does not claim edge, promote wallets, demote wallets, mutate wallet lists, or trade.
- [x] Stage 9 behavioral intelligence layer. `research/behavioral_intelligence_layer.py` and `utils/build_behavioral_intelligence_layer.py` generate `data/reports/behavioral_intelligence/behavioral_intelligence_layer_report.json` from Stage 5 wallet ecosystems, Stage 7 market regimes, and the Validation / Proof Layer. Current local report marks Stage 9 at `100%` as a review-only behavioral pattern layer: `7` pattern candidates, `7` cluster candidates ingested, `1` regime row ingested, dominant regime `unknown`, `2` known 15m outcomes, `0%` behavioral data readiness, `0%` proof readiness, `0` wallet-list mutations, and `0` auto trust mutations. `/api/behavioral-intelligence-layer` exposes it as read-only. This completes Stage 9 infrastructure without allowing behavioral pattern candidates to drive wallet trust or execution.
- [x] Behavioral trust validation gate. `research/behavioral_trust_validation.py` and `utils/build_behavioral_trust_validation.py` generate `data/reports/behavioral_validation/behavioral_trust_validation_report.json` from the Stage 9 behavioral intelligence, Validation / Proof, Stage 8 readiness, and Evidence Layer reports. Current local report marks the gate at `100%` as a read-only validation layer: `7` behavioral pattern candidates validated, `0` trust-ready patterns, `behavioral_trust_justified=false`, `11%` proof readiness, `662` known 15m outcomes vs `30` required, `81%` fillability evidence coverage vs `70%` required, `52%` positive fill rate, `101` score-ready market-context records, `0` wallet-list mutations, and `0` auto trust mutations. `/api/behavioral-trust-validation` exposes it as read-only. This is a negative evidence gate and cannot mutate trust, wallet lists, or execution.
- [x] Discord behavioral intelligence layer. `research/discord_intelligence_layer.py` and `utils/build_discord_intelligence_layer.py` generate `data/reports/notifications/discord_intelligence_layer_report.json` from Stage 4 wallet review, Stage 9 behavioral intelligence, behavioral trust validation, proof-readiness blocker reduction, and Stage 7 regime detection. Current local report marks the layer at `100%` as a sparse review-only notification layer: `5` high-signal events prepared, `5` channels touched, `18` raw wallet rows suppressed, `0%` proof readiness, `0` wallet-list mutations, `0` auto trust mutations, and Discord dispatch disabled by default. `/api/discord-intelligence-layer` exposes it as read-only. `utils/dispatch_discord_intelligence.py` defaults to dry-run, supports per-channel webhook routing through ignored local config or env vars, requires `--send` before posting, and uses `data/discord_dispatch_ledger.local.json` to skip already-sent event IDs.
- [x] Proof-readiness blocker reduction queue. `research/proof_readiness_blocker_reduction.py` and `utils/build_proof_readiness_blocker_reduction.py` generate `data/reports/replay_validation/proof_readiness_blocker_reduction_report.json` from behavioral trust validation, proof, Stage 8, Evidence Layer, timeline, on-chain context, and supply evidence reports. Current local report marks the queue at `100%` as a read-only blocker-reduction layer: `1` next action, `11%` proof readiness, `101` score-ready market-context records, `0` more 15m outcomes needed under the current minimum, `0` fillability-evidence points missing, and `643` historical wallet-evidence context rows still needing final supply / market-cap proof. `/api/proof-readiness-blocker-reduction` exposes it as read-only. This does not fetch, infer, score, trade, or mutate wallet trust.
- [x] Productization operator workflow gate. `research/productization_operator_workflow.py` and `utils/build_productization_operator_workflow.py` generate `data/reports/productization/operator_workflow_report.json` from the Evidence Layer, Replayable Token Timelines, Similar-Rug Pattern Matching, Alerting / Dashboard Layer, and Validation / Proof Layer reports. Current local report marks Productization at `100%` as a read-only operator workflow: `5` ordered report steps, `5` completed report gates, `12` blocker categories, `12` blocked proof criteria, and `0%` proof readiness. `/api/productization-operator-workflow` exposes it as read-only. This does not trade, mutate wallet lists, or claim edge.
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
- Use `data/reports/wallet_backfills/evidence_layer_completion_report.json` or `/api/evidence-layer-completion` as the Evidence Layer closeout. If its layer completion is `100%` but wallet score readiness is `0%`, treat that as a clean handoff to Replayable Token Timelines, not as permission to trust wallet scores.
- Use `data/reports/wallet_backfills/wallet_stage4_review_report.json` as the review-only Stage 4 promotion/demotion gate. It can recommend promotion review, risk review, demotion/block review, or hold-more-data, and `data/wallet_candidate_audit.json` can consume those rows as human-review evidence. It cannot auto-apply wallet-list changes.
- Use `data/reports/wallet_reviews/wallet_promotion_demotion_system_report.json` or `/api/wallet-promotion-demotion-system` as the Stage 4 closeout. If completion is `100%` but `trusted_promotions_allowed` is `0`, the workflow is ready for review and evidence collection, not automatic trust mutation.
- Use `data/reports/wallet_ecosystems/wallet_ecosystem_intelligence_report.json` or `/api/wallet-ecosystem-intelligence` as the Stage 5 closeout. It ranks repeated co-entry relationships and cluster candidates for review, but funding overlap and deployer-linked relationships remain blocked until real source artifacts exist.
- Use `data/reports/market_regimes/market_regime_detection_report.json` or `/api/market-regime-detection` as the Stage 7 closeout. It segments replay events by market regime for review, but current regime data is mostly unknown and cannot drive wallet scoring.
- Use `/api/wallet-candidate-audit` or the Obsidian `WalletCandidateReviews` folder to inspect the current Stage 4-backed review queue before recording any review decision.
- Use `/api/wallet-candidate-decision-prep` or `data/reports/wallet_reviews/wallet_candidate_decision_prep.json` to inspect draft-only approval records. Proposed rows remain `approved=false` until the operator explicitly approves them through the review-decision path.
- Use `/api/wallet-candidate-review-summary` or `data/reports/wallet_reviews/wallet_candidate_review_summary.json` to see whether the current queue has actionable approvals, risk-review blockers, insufficient-evidence rows, or resolved rows.
- Use `/api/wallet-candidate-collection-plan` or `data/reports/wallet_reviews/wallet_candidate_collection_plan.json` to see the exact evidence work needed before the next promotion/demotion cycle.
- Use `/api/wallet-candidate-collection-batch` or `data/reports/wallet_reviews/wallet_candidate_collection_batch_report.json` to verify the latest read-only evidence-chain refresh before acting on Stage 4 review rows.
- Use `/api/wallet-candidate-context-recovery-runner` or `data/reports/wallet_reviews/wallet_candidate_context_recovery_runner.json` to inspect which blocked wallets already have linked local artifacts and why they remain untrusted.
- Use `/api/wallet-candidate-context-recovery-closeout` or `data/reports/wallet_reviews/wallet_candidate_context_recovery_closeout.json` to see exact next actions for blocked recovery wallets.
- Use `/api/wallet-candidate-blockers` or `data/reports/wallet_reviews/wallet_candidate_blocker_reducer.json` to see the current blocker mix before choosing the next evidence collection lane.
- Use `/api/wallet-candidate-context-recovery` or `data/reports/wallet_reviews/wallet_candidate_context_recovery_queue.json` to inspect the `COLLECT_OUTCOMES_AND_MARKET_CONTEXT` target queue before running recovery work.
- Use `data/reports/historical_backfill/historical_market_context_backfill_report.json` to separate partial transaction-derived context from rows that still need trusted historical market snapshots.
- Use `data/reports/historical_backfill/missing_raw_transaction_recovery_report.json` to audit the exact read-only recovery of previously missing raw transaction signatures.
- Use `data/reports/historical_backfill/historical_quote_price_enrichment_report.json` to audit WSOL quote-to-USD conversion coverage.
- Use `data/reports/historical_backfill/onchain_market_context_recovery_report.json` to audit home-built liquidity recovery from raw transaction pool/vault balances.
- Use `data/reports/historical_backfill/onchain_supply_evidence_report.json` to audit decision-time token supply availability. It currently proves decimals are available but total supply is not present in local raw transaction artifacts.
- Use `data/reports/historical_backfill/trusted_historical_market_snapshot_report.json` to keep incomplete historical rows out of wallet scoring and to choose the next on-chain parser/supply requirement. Provider snapshots are temporary validation/fallback sources only.
- Use `data/reports/historical_backfill/replay_realism_readiness_report.json` as the Stage 6 completion gate. If its contract completion is `100%` but data score readiness is `0%`, do not treat that as a failure of the realism layer; treat it as the exact Stage 8 data-coverage queue.
- Use `data/reports/replay_validation/stage8_validation_readiness_report.json` as the Stage 8 validation-loop completion gate. If its contract completion is `100%` but proof readiness is `0%`, do not treat that as proof of strategy edge; treat it as the exact Stage 3 wallet-evidence collection queue.
- Use `data/reports/historical_backfill/replayable_token_timelines_report.json` or `/api/replayable-token-timelines` as the Replayable Token Timelines closeout. If its layer completion is `100%` but timeline data readiness is `0%`, treat that as an honest handoff to pattern classification and deeper supply/market-cap recovery, not as permission to score wallets.
- Use `data/reports/historical_backfill/similar_rug_patterns_report.json` or `/api/similar-rug-patterns` as the Similar-Rug Pattern Matching closeout. If its layer completion is `100%` but rug-pattern data readiness is `0%`, treat confirmed rug exposure as a review queue only and keep unknown outcomes out of rug labels.
- Use `data/reports/dashboard/alerting_dashboard_layer_report.json` or `/api/alerting-dashboard-layer` as the operator-status entry point for the current research gates. If its layer completion is `100%` but research data readiness is `0%`, treat that as a complete visibility layer and continue evidence/proof work before trusting scores.
- Use `data/reports/replay_validation/validation_proof_layer_report.json` or `/api/validation-proof-layer` as the proof-readiness checklist. If its layer completion is `100%` but proof readiness is `0%`, treat that as a complete proof checklist, not as proof that wallet scores are trustworthy.
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
- [x] Archival provider response capture lane: request bundle, optional execute capture, saved raw response validation, raw response preservation, probe validation, batch chunk capture, and secret-free read-only reporting. Current local status is blocked until a real archival account-state endpoint response or saved raw response is supplied.
- [x] Manual Gold Set research lane: ranked proof-candidate CLI, manual research CSV/JSON export, evidence template, manual evidence importer, Solscan historical activity CSV importer, manual-adjusted proof-readiness report, and beginner-friendly operator docs. This is the low-cost path while paid archival providers are unavailable. Solscan/Dexscreener partial evidence can now be preserved without pretending it is Tier A supply proof.
- [ ] Manual Gold Set review pass: operator researches the first exported packet rows, imports only evidence-backed results, and reruns proof-readiness to measure whether Tier A rows reduce the archival supply blocker.

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
