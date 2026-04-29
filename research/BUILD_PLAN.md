# MemeTraderPro Build Plan

Last updated: 2026-04-29

## Legend

- [x] Done and usable in the current repo.
- [~] Partially done, needs hardening, wiring, or validation.
- [ ] Not started or still only a design target.

## Current Working Section

<mark>Active roadmap area: Phase 6 - Manual Protection And Watchdog.</mark>

<mark>Current focus: prepared paper/simulation exits for protected manual positions. Next: holder concentration and token risk/performance snapshots.</mark>

## Product Goal

Turn this repo into a competitive local Solana meme trading workstation focused on safer decision-making, confirmation-mode paper trading, wallet intelligence, token risk/mechanics inspection, manual protection/watchdog flows, gated live execution, and a polished local GUI.

The strategic lane is confirmation trading, not 3-second launch sniping. MemeTraderPro should help the operator understand what it would do, why, and how those decisions perform before any live SOL is at risk.

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
- [ ] Pro GUI is still future work.

## Operating Principles

- Paper mode first. Live execution is gated and earned through observed performance.
- Local-first memory. Alerts, tokens, wallets, paper trades, skipped candidates, protected positions, and postmortems should persist.
- Explain every action. The user should see why a token passed, failed, entered paper mode, exited, or triggered protection.
- Favor exits and risk control over raw entry speed.
- Do not trust stale state. Runtime health and data freshness must be visible.
- Treat Token-2022 mechanics and authority controls as pre-entry risk inputs, not afterthoughts.

## Phase 0 - Repo Control And Documentation

Goal: make the project understandable and handoff-safe while multiple builders work in the repo.

Deliverables:

- [x] `research/` folder for state, strategy, product, and token-risk notes.
- [x] Living project state note.
- [x] Living build plan.
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
- [~] Preflight checks for env, required files, Python environment, and ports.
- [x] Runtime health view for bot/dashboard/watchdog state and source freshness.
- [ ] Single command that starts backend, dashboard, and watchdog with clear logging.
- [ ] Graceful stop/restart controls.

Acceptance criteria:

- User can launch without terminal knowledge.
- Dashboard clearly shows whether backend loops are alive and when each feed last updated.
- Startup failures are actionable, not silent.

Next actions:

- Harden launcher preflight and status reporting.
- Add process health checks for backend loop, dashboard, quote API, wallet feed, and watchdog.

## Phase 2 - Data Store And Event Memory

Goal: centralize durable state so the workstation can learn from every signal and decision.

Deliverables:

- [x] JSON state files for live state, paper trades, wallet performance, social state, settings, manual watchlist, and runtime status.
- [x] SQLite database exists.
- [~] Storage utilities and sync/backfill scripts.
- [x] Data freshness indicators per source.
- [ ] Canonical event schema for alerts, candidates, wallet actions, quote checks, paper entries/exits, watchdog triggers, and postmortems.
- [ ] Migration/backfill routine from JSON into SQLite as the source of truth.

Acceptance criteria:

- No important decision exists only in memory.
- Dashboard and analysis tools read from known canonical sources.
- Stale, missing, or malformed state files are surfaced in the UI.

Next actions:

- Keep tightening runtime/process controls after watchdog loop and backend lifecycle work.
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
- [ ] Paper engine records skipped candidates and reasons, not only entered trades.

Acceptance criteria:

- Every paper trade includes entry reason, source wallets/signals, token risk result, quote result, size, simulated fill assumptions, and exit reason.
- The bot can run for a meaningful sample without live execution.
- The user can inspect why a promising candidate was rejected.

Next actions:

- Audit paper trade fields and ensure the dashboard can render entry/current values, PnL, reason, and raw trade data.
- Add skipped-candidate ledger if not already complete.
- Backtest confirmation rules from `research/STRATEGY_RESEARCH.md`.

## Phase 4 - Wallet Intelligence

Goal: turn wallet tracking into a private intelligence database, not a raw follow list.

Deliverables:

- [x] Wallet tracking and real-time transaction parsing foundations.
- [x] Wallet performance file and backfill utility.
- [x] Wallet quality scoring foundations.
- [x] Wallet labeler foundation.
- [~] Elite/bad wallet lists.
- [~] Paper-copy performance tracking.
- [ ] Rolling 7d/30d wallet stats.
- [ ] Wallet behavior labels: early buyer, late buyer, rug-exit-fast, late-exit, copy-bait, dev-adjacent, paper-profitable, high-fee churner, follower trap.
- [ ] Wallet detail page in GUI/dashboard.

Acceptance criteria:

- A wallet is not promoted to copy/live consideration without paper sample evidence.
- Wallet stats include win rate, median hold time, drawdown after entry, realized/paper PnL, and exit behavior.
- The UI explains whether the wallet is a leader, exit signal, trap, or unproven source.

Next actions:

- Define wallet promotion/demotion thresholds.
- Add per-wallet postmortem rollups from paper trades.
- Surface wallet labels and confidence in Token Console and Operator Brief.

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

- Store full token risk/mechanics snapshot with every paper trade and skipped candidate.
- Add holder/cluster checks where reliable data is available.

## Phase 6 - Manual Protection And Watchdog

Goal: protect manual Axiom or external trades by watching the token after the user pastes a mint.

Deliverables:

- [x] Manual watchlist data file.
- [~] Dashboard input/panel for token mint protection.
- [~] Alert-only protection concept.
- [~] Rug watchdog modules.
- [x] Watchdog stores Token-2022/token mechanics risk snapshots for protected mints.
- [x] Protected mints have explicit alert levels: info, warning, danger, emergency.
- [x] Dashboard protected-position cards show alert counts, last-check age, mechanics risk, extensions, auto-sell lock state, and metrics.
- [~] Real watchdog loop with visible status and last-check timestamps.
- [ ] Exit advisor for protected positions.
- [ ] Prepared sell intent in paper/simulation mode.
- [ ] Auto-sell remains disabled until live execution gates are passed.

Acceptance criteria:

- User can paste a token mint, see it appear in the watchlist, and see current risk/protection state.
- Watchdog evaluates liquidity drain, dev/top-holder sells, route degradation, price impact explosion, and severe drawdown.
- Alerts are written to durable state and visible in the dashboard.
- Auto-sell controls are clearly gated and cannot fire accidentally.

Next actions:

- Add prepared paper/simulation exits for protected manual positions before any live sell wiring.
- Harden the continuous watchdog process and make its lifecycle easier to start/stop from the launcher.

## Phase 7 - Operator Review, Postmortems, And Replay

Goal: make the system improve from its own decisions.

Deliverables:

- [x] Operator Brief.
- [x] Trade Postmortem.
- [~] Performance analyzer and replay analyzer modules.
- [ ] Candidate review queue.
- [ ] Replay lab for passed/skipped/entered tokens.
- [ ] Strategy comparison report for confirmation rules.
- [ ] Daily operator summary.

Acceptance criteria:

- User can review what the bot saw, what it did, and what happened afterward.
- Postmortems include entry quality, risk flags, wallet source quality, exit quality, and missed-exit notes.
- Replay can compare current rules against historical candidates without touching live state.

Next actions:

- Add candidate ledger views to dashboard.
- Build daily summary from alerts, trades, watchdog events, and wallet performance.
- Define replay input/output schema.

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
- Every live order passes execution safety, token risk, quote, slippage, price impact, and size gates.
- Live mode requires deliberate user confirmation and visible armed/disarmed state.
- Kill switch can stop new buys immediately.
- Manual protection auto-sell cannot activate unless explicitly armed and logged.

Next actions:

- Keep live execution disabled by default.
- Define exact paper-performance thresholds required before live mode can be considered.
- Add audit log fields now, even while trades remain paper-only.

## Phase 9 - Polished Double-Click GUI

Goal: make the current Streamlit cockpit feel like a dependable desktop workstation.

Deliverables:

- [x] Streamlit dashboard baseline.
- [~] Token Console, Operator Brief, paper trades, wallet performance, and manual protection panels.
- [ ] Clear navigation around Command Center, Tokens, Wallets, Paper Trades, Protection, Replay, and Settings.
- [ ] Consistent visual status language for healthy/warning/danger/stale states.
- [ ] Settings editor with validation.
- [ ] Local logs and export tools.
- [ ] Job/progress monitor for long-running local actions.

Acceptance criteria:

- First screen answers: is the system alive, what needs attention, what is being watched, and what changed recently.
- Operator can inspect a token, wallet, trade, or protected position without hunting through raw files.
- Settings changes are validated and durable.

Next actions:

- Audit current dashboard panels against actual data sources.
- Prioritize dense, operational UI over marketing-style screens.
- Add empty/error/loading states for each data panel.

## Phase 10 - Future Pro GUI

Goal: graduate from Streamlit into a more powerful local workstation UI when the core trading system is trustworthy.

Deliverables:

- [ ] Decide stack: local web app, Electron/Tauri, or native wrapper.
- [ ] Real-time event timeline.
- [ ] Advanced wallet graph and cluster views.
- [ ] Token lifecycle replay with snapshots.
- [ ] Rule editor and strategy comparison.
- [ ] Protected position cockpit with prepared action queue.

Acceptance criteria:

- Pro GUI preserves local-first operation.
- It improves speed of operator decisions without hiding risk reasoning.
- It uses the same canonical data store as the bot and dashboard.

Next actions:

- Defer until data model, paper bot, watchdog, and live gates are mature.
- Capture GUI needs from Streamlit usage before choosing a stack.

## Decisions

- Paper trading remains the default operating mode.
- MemeTraderPro competes as a local intelligence and protection cockpit, not as the fastest Telegram sniper.
- Confirmation mode targets post-launch follow-through rather than blind launch sniping.
- Token-2022 support is required, but unsafe mechanics are rejected or warned based on severity.
- Manual protection starts alert-only/paper-exit-first; real auto-sell is future gated work.
- Live execution must be explicitly armed and safety-gated.
- Open-source Solana/meme bot repos are reference material only; reimplement useful ideas cleanly instead of cloning whole repos.

## Assumptions

- The operator is trading Solana meme tokens and may also use external tools such as Axiom.
- Local machine operation is acceptable and desirable.
- State currently exists across JSON files and SQLite; consolidation can happen incrementally.
- Existing modules should be hardened and wired before major rewrites.
- The user values explainability and risk control over pure execution speed.

## Risks

- Stale or split state can make the dashboard show misleading counts or missing trades.
- Token collapses can happen faster than a polling watchdog can react; high-risk mechanics should be rejected before entry.
- Wallets can be copy-bait or exit into followers; wallet promotion needs paper evidence.
- Live execution before enough paper evidence could lose real funds quickly.
- Overbuilding UI before canonical data is settled can create duplicated logic and confusion.
- External API limits or degraded quote/routing data can make paper/live assumptions inaccurate.

## Near-Term Priority Stack

- [x] Data source map for dashboard and bot state.
- [x] Runtime health and per-source freshness indicators.
- [~] Manual protection watchdog status and alert levels.
- [ ] Prepared paper/simulation exits for protected manual positions.
- [ ] Holder concentration and linked-cluster checks.
- [ ] Token performance snapshots for entries, skips, exits, and watchdog checks.
- [ ] Paper trade field completeness and dashboard rendering.
- [ ] Skipped-candidate ledger with reasons.
- [~] Token mechanics/risk snapshot stored with every decision.
- [ ] Wallet promotion/demotion thresholds.
- [ ] Paper-performance threshold for considering live execution.

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
