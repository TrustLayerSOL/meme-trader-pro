# MemeTraderPro Data Source Map

Last updated: 2026-05-12

This map explains where the dashboard and bot state comes from. Use it before changing a panel, parser, storage schema, or strategy rule.

## Primary State Files

| Source | Purpose | Main Readers | Main Writers |
| --- | --- | --- | --- |
| `live_state.json` | Root live signal snapshot used by the dashboard. | `dashboard/dashboard.py`, analyzers | scanner / bot runtime |
| `data/live_state.json` | Data-folder live state snapshot. | storage sync, health checks | runtime utilities |
| `data/paper_trades.json` | Open, closed, and failed paper trades, including `paper_lane=main` or `paper_lane=exploration` when known. | dashboard, performance analyzer, postmortem, replay, native Portfolio/PnL view, native Paper Profitability Review | `paper_trader.py`, bot runtime |
| `data/manual_watchlist.json` | Manually protected mints, watchdog state, and protected-position amount metadata. Operator-owned fields are preserved during watchdog updates; `auto_sell` remains locked off. | dashboard, desktop GUI, watchdog, SQLite sync | dashboard, desktop protected-token add form, desktop protected amount editor, `core/rug_watchdog.py` |
| `data/wallet_performance.json` | Wallet stats, paper-copy evidence, and wallet scores. | dashboard, wallet labeler, copy engine | wallet performance backfill/runtime |
| `data/wallet_behavior.json` | Rolling 7d/30d wallet behavior report, behavior labels, and per-wallet postmortem rollups with best/worst paper outcomes, exit reasons, failure reasons, and average hold time. Advisory only. | native Wallets tab, wallet lifecycle review | `core/wallet_behavior.py`, `core/wallet_discovery_scheduler.py` |
| `data/candidate_wallets.json` | Watch-only candidate wallets discovered from local scanner history and optional read-only early-buyer chain evidence. This file is review-only and must not execute trades or auto-promote wallets. | future native Wallets review panel, lead-agent review | `utils/discover_candidate_wallets.py` |
| `data/paper_watch_wallets.json` | Lower-trust wallet lane created from reviewed candidates. Runtime can observe these wallets and collect paper outcomes, but they are not live-trade drivers and do not mutate `data/tracked_wallets.json`. | bot startup, scanner, wallet lifecycle review | `utils/sync_paper_watch_wallets.py`, `core/wallet_lifecycle.py` |
| `data/wallet_discovery_status.json` | Latest wallet discovery scheduler cycle summary, including candidate count, paper-watch count, and dry-run apply preview. Does not contain raw tracked wallet lists. | Ops/System freshness, operator review | `core/wallet_discovery_scheduler.py`, `utils/run_wallet_discovery_scheduler.py` |
| `data/wallet_review_decisions.json` | Operator approvals for wallet promotions/demotions. Only approved decisions are eligible for the apply tool. | wallet apply utility, native Wallets review actions | operator/manual edit, `POST /api/wallet-review-decision` |
| `data/wallet_list_update_audit.json` | Recent wallet-list apply audit trail with changes, skipped decisions, summary, and backup directory. | operator review, future Ops/System panel | `utils/apply_wallet_review.py` |
| `data/desktop_api_session.json` | Local desktop API session token, process id, and start-time metadata for scoped metadata POST routes. Runtime secret; ignored by git. | native desktop shell, desktop API metadata POSTs | `desktop_api.py`, Tauri/fallback launcher |
| `data/candidate_ledger.json` | Operator decisions on candidates, ignored tokens, and protection adds. | dashboard Candidate Workbench | dashboard |
| `data/runtime_status.json` | Component heartbeat and freshness state, including `wallet_discovery` scheduler health. | dashboard Runtime Health, health report, native Ops/System | `core/runtime_status.py` callers |
| `data/process_locks/*.lock` | Launcher-only per-component start locks to avoid duplicate service spawns. | launcher | `launcher.py` |
| `data/bot_settings.json` | Strategy mode, thresholds, sizing, and confirmation settings. | dashboard Strategy Settings, scanner/scoring | dashboard settings form |
| `data/social_state.json` | Structured local social/sentiment events with account, platform, keywords, tickers, mints, sentiment, expiry, and raw/engagement fields. | dashboard Social Catalyst Tracker, scanner social matching, catalyst cards | `social/social_signal.py`, dashboard import form |
| `data/catalyst_cards.json` | Generated token thesis/outcome cards from snapshots, social matches, wallet confirmation, risk, and paper results. | dashboard Data Store Catalyst Cards tab, future Candidate Workbench | `core/catalyst_cards.py`, dashboard refresh |
| `data/position_action_intents.json` | Simulation-only prepared add-position and exit-early intents from Position Cockpit. This file must not execute live orders. | dashboard Position Cockpit | `core/position_cockpit.py`, dashboard buttons |
| `data/elite_wallets.json` | Wallet allow/promote list. | wallet intelligence, copy engine | manual edits/tools |
| `data/bad_wallets.json` | Wallet avoid/fade list. Current-compatible shape is a list of wallet address strings. | wallet intelligence, copy engine | manual edits/tools, `utils/apply_wallet_review.py` |
| `data/tracked_wallets.json` | Wallets watched by the tracker. | wallet tracker/runtime | manual edits/tools |
| `dev_reputation.json` | Optional dev reputation data, including bonded/migrated token counts. | `core/dev_analyzer.py` | manual imports/future Axiom import |

## SQLite Store

SQLite file: `data/memetrader.db`

Managed by: `core/storage.py`

Security note: `.env` and SQLite database/WAL/SHM files should remain owner-only mode `600`; System Readiness reports unsafe private-file permissions.

| Table | Purpose | Notes |
| --- | --- | --- |
| `events` | Durable feed of raw wallet/signal events. | Unique index on time, event type, wallet, mint. |
| `alerts` | Durable alert and scoring records. | Stores score, edge verdict, should-trade, risk label, and raw payload JSON. |
| `decision_records` | Canonical candidate decision ledger. | Foundation started. Stores scanned candidate decision records: signal inputs, rule outcomes, risk/quote checks, final action, lane, and later paper result. UI and postmortem work should keep moving toward this table instead of reconstructing decisions from scattered JSON/files. |
| `trades` | Durable paper/live trade snapshots. | Stores summary columns plus full payload JSON. |
| `watchlist` | Durable protected-mint snapshots. | Mirrors manual watchlist entries. |
| `token_snapshots` | Durable token risk/performance snapshots. | Stores watchdog, scanner, and paper-trade lifecycle contexts, market data, risk label, full payload JSON, and candidate-feed display fields when captured. |
| `swap_ticks` | Durable trade-stream tick rows for Axiom-style candles. | Stores time, mint, signature, wallet, side, price, market cap, liquidity, token amount, SOL amount, source, and raw payload. Quote mint/amount and route program details are stored in the raw payload. Scanner writes `wallet_event_dex_route_delta` ticks when known DEX/Jupiter/Pump/Raydium/Meteora/Orca/OpenBook/Phoenix route programs are present and same-transaction SOL/USDC/USDT deltas allow execution-price math. It uses `wallet_event_dex_route_native_delta` when native SOL delta is usable, and `wallet_event_market_enriched` fallback ticks when route evidence is absent or market price is the only reliable price. Exact pool attribution remains future work. |

Desktop read-path indexes:

- `idx_token_snapshots_mint_time_desc` supports selected-token snapshot/candle reads ordered by latest mint/time.
- `idx_swap_ticks_mint_time_id_desc` supports selected-token swap-tick candle reads ordered by latest mint/time/id.

Backfill/sync utility: `utils/sync_state_to_sqlite.py`

Current stance: JSON files remain the practical runtime source for several panels, while SQLite is the durable query layer. Future work should consolidate more read paths onto SQLite once schemas are stable.

Known `token_snapshots.context` values:

| Context | Writer | Meaning |
| --- | --- | --- |
| `watchdog_check` | `core/rug_watchdog.py` | Protected-token check result with market, mechanics, holder, and prepared-exit status. |
| `scanner_skip` | `core/scanner.py` | Scanner evaluated a signal and rejected or skipped it before paper entry. |
| `scanner_entry_candidate` | `core/scanner.py` | Scanner evaluated a signal as trade-worthy before paper-entry prechecks/fill simulation. |
| `scanner_runtime_skip` | `core/scanner.py` | Scanner wanted to trade, but runtime prerequisites failed, such as no paper trader, missing market data, or invalid entry price. |
| `paper_entry_opened` | `paper_trader.py` | Paper trade opened successfully. |
| `paper_entry_failed` | `paper_trader.py` | Simulated paper buy fill failed. |
| `paper_partial_exit` | `paper_trader.py` | Paper trade took a partial exit. |
| `paper_exit_closed` | `paper_trader.py` | Paper trade closed. |

## Dashboard Panel Map

Dashboard file: `dashboard/dashboard.py`

| Panel | Backing Sources | Core Helpers |
| --- | --- | --- |
| Operator Brief | `live_state.json`, `data/paper_trades.json`, `data/manual_watchlist.json`, runtime state | `core/operator_brief.py` |
| Signal Pipeline | `live_state.json` alerts/signals | local dashboard aggregations |
| Command Center | process state, logs, candidate ledger | `core/process_guard.py`, `data/candidate_ledger.json` |
| Opportunity Inbox | `live_state.json` alerts | dashboard filters |
| Candidate Workbench | `live_state.json`, `data/candidate_ledger.json`, `data/manual_watchlist.json` | dashboard update helpers |
| Token Console | `live_state.json`, paper trades, manual watchlist, candidate ledger, `data/catalyst_cards.json` | `core/token_console.py`, dashboard catalyst-card helpers |
| Social Catalyst Tracker | `data/social_state.json`, `data/catalyst_cards.json` refresh | `social/social_signal.py`, `core/catalyst_cards.py` |
| Wallet Intelligence | `data/wallet_performance.json`, `data/wallet_behavior.json`, `data/candidate_wallets.json`, `data/paper_watch_wallets.json`, elite/bad wallet files | `core/wallet_labeler.py`, `core/wallet_lifecycle.py`, `core/wallet_behavior.py`, native Wallets tab |
| Paper Copy Engine | wallet performance and paper trade state | `core/wallet_copy_engine.py` |
| Performance Intelligence | `data/paper_trades.json`, `live_state.json` | `core/performance_analyzer.py` |
| Trade Postmortem | `data/paper_trades.json` | `core/trade_postmortem.py` |
| Replay Lab | `live_state.json`, `data/paper_trades.json` | `core/replay_analyzer.py` |
| Runtime Health | `data/runtime_status.json`, process table, logs | `core/runtime_status.py`, `core/process_guard.py` |
| System Readiness | env, files, imports, runtime status | `core/system_health.py` |
| Execution Safety | env/config/safety state | `core/execution_safety.py` |
| Data Store | `data/memetrader.db`, state files freshness, token snapshot context/source filters, `data/catalyst_cards.json` | `core/storage.py`, `core/data_freshness.py`, `core/catalyst_cards.py` |
| Strategy Settings | `data/bot_settings.json` | `core/settings_manager.py` |
| Manual Trade Protection | `data/manual_watchlist.json`, SQLite `events` for prepared exit intents | dashboard helpers, `core/rug_watchdog.py`, `core/protection_exit.py` |
| Position Cockpit | `data/paper_trades.json`, `data/manual_watchlist.json`, SQLite `token_snapshots`, `data/position_action_intents.json`, `data/runtime_status.json` | `core/position_cockpit.py`, dashboard helpers |
| Open/Closed/Failed Trades | `data/paper_trades.json` | dashboard trade rendering helpers |
| Alerts | `live_state.json` | dashboard rendering |
| Raw Debug Expanders | JSON state files | dashboard rendering |

## Desktop GUI Map

Desktop API file: `desktop_api.py`

Static GUI folder: `desktop_gui/`

Double-click launcher: `Start MemeTraderPro Desktop.command`

The desktop GUI is primarily a local presentation layer. It binds to `127.0.0.1`, serves static files, and exposes GET/HEAD read routes. The scoped mutation routes are protected-position amount metadata, protected-token watch entries, social research imports, wallet review decision metadata, and guarded wallet-list apply; token protection is required when the API is launched with a desktop session token. Buy, sell, auto-sell, and live execution routes remain unavailable.

| Route | Backing Sources | Notes |
| --- | --- | --- |
| `/` | `desktop_gui/index.html`, `desktop_gui/assets/*`, `desktop_gui/vendor/lightweight-charts.standalone.production.js` | Static Axiom-style cockpit shell with TradingView `lightweight-charts` rendering for selected-token charts. |
| `/api/health` | server process metadata | Reports read-only mode and live lock state. |
| `/api/overview` | `data/paper_trades.json`, `data/manual_watchlist.json`, `data/runtime_status.json`, social/catalyst/settings JSON, `data/wallet_performance.json`, `data/wallet_behavior.json` | Summary counts, runtime state, and cockpit wallet-confidence summary. |
| `/api/runtime` | `data/runtime_status.json` | Normalized runtime heartbeat summary plus raw runtime state. |
| `/api/readiness` | required state files, runtime status, read-only SQLite counts | Avoids live execution and reports degraded state as warnings/failures. |
| `/api/freshness` | `core.data_freshness.DataFreshness` | Source freshness report used for stale-state visibility. |
| `/api/positions` | `data/paper_trades.json`, `data/manual_watchlist.json` | Uses `core.position_cockpit.build_position_rows`. |
| `/api/positions/{mint}` | positions plus SQLite `token_snapshots`, `data/social_state.json`, `data/catalyst_cards.json`, `data/wallet_performance.json`, `data/wallet_behavior.json`, `data/paper_trades.json` | Selected-position detail payload with snapshot trend metrics, read-only protection summary, local signal/catalyst matches, and wallet confidence context. |
| `/api/candidates` | SQLite `token_snapshots` scanner contexts | Read-only live launch feed. Dedupes recent scanner candidates by mint and exposes image URL, name/symbol, market cap, liquidity, tx count, holder count, wallet score, risk, and pass/skip/block reasons when available. |
| `/api/decisions` | SQLite `decision_records` | Read-only canonical decision feed. Exposes recent candidate decisions, action, lane, score, risk, quote pass/fail flags, paper outcome fields, and compact payload/result JSON. Supports filters such as `filter=quote_failed` and `lane=main`. Feeds the static desktop Replay tab and the React/Tauri Replay Decision Ledger. |
| `/api/candidate-wallets` | `data/candidate_wallets.json` | Watch-only discovered wallets for manual review. Read-only; does not promote wallets or execute trades. |
| `/api/wallet-lifecycle` | `data/tracked_wallets.json`, `data/paper_watch_wallets.json`, `data/candidate_wallets.json`, `data/wallet_performance.json`, `data/wallet_behavior.json` | Read-only promotion/demotion queue with trade count, win/loss record, win rate, total PnL, average PnL, score, behavior labels, rolling windows, postmortem summary, and lifecycle recommendation. |
| `POST /api/wallet-review-decision` | `data/wallet_review_decisions.json` | Scoped local metadata update for operator wallet review decisions: approve promotion, approve demotion, hold, or reject. Does not apply changes to tracked/bad wallet lists and does not execute trades. |
| `/api/wallet-review-apply` | `data/wallet_review_decisions.json`, `data/tracked_wallets.json`, `data/paper_watch_wallets.json`, `data/bad_wallets.json`, `data/wallet_list_update_audit.json` | GET returns dry-run preview without raw wallet lists. POST requires exact confirmation `APPLY_WALLET_REVIEW`, runs the controlled apply tool, creates backups/audit records, and still does not execute trades. |
| `/api/events` | SQLite `events` | Read-only scanner tape for raw tracked-wallet buy/sell events before strategy filters promote them into launch candidates. Exposes mint, wallet, age, amount, and wallet score fields when present in payload JSON. |
| `/api/candles`, `/api/tokens/{mint}/candles` | SQLite `swap_ticks`, fallback SQLite `token_snapshots` | Uses `core.position_cockpit.build_candles`; supports strict read-only `metric=market_cap`, `metric=price`, or `metric=liquidity` plus `interval=1`, `5`, `30`, or `60`. Prefers tick-derived candles when `swap_ticks` exist for the mint and reports `sample_kind=swap_tick`, `tick_count`, and `trade_stream_active=true`. Falls back to sampled quote/snapshot candles with `sample_kind=sampled_quote` when tick rows are absent. |
| `/api/tokens/{mint}/snapshots` | SQLite `token_snapshots` | Oldest-to-newest token snapshot rows. |
| `/api/trades` | `data/paper_trades.json` | Open/closed/failed trade state. Feeds the desktop Portfolio view, static desktop Portfolio panel, paper replay, and selected-token trade lifecycle. |
| `/api/paper-review` | `data/paper_trades.json`, `data/wallet_behavior.json` | Read-only paper profitability review with readiness gaps, paper metrics, main-vs-exploration lane metrics, entry/exit/failure reasons, and wallet-label exposure. |
| `/api/winner-patterns` | `data/paper_trades.json` | Read-only winner-pattern review comparing closed winners against closed losers. Used for paper tuning only; live execution remains locked. |
| `/api/watchlist` | `data/manual_watchlist.json` | Protected manual positions. |
| `POST /api/watchlist/protected-token` | `data/manual_watchlist.json` | Scoped local metadata update for adding/updating a manual protected token from the desktop Protection tab. Watch/alert only; live execution and auto-sell remain locked. |
| `POST /api/watchlist/protected-amount` | `data/manual_watchlist.json` | Scoped local metadata update for protected-position amount/decimals/raw/test flag only. Live execution and auto-sell remain locked. |
| `/api/alerts` | SQLite `alerts`, fallback `live_state.json` alerts | Canonical read path now prefers durable SQLite alerts and falls back to root live-state compatibility alerts only when SQLite has no alert rows. |
| `/api/social` | `data/social_state.json` | Local social events/signals; supports both `events` and legacy `signals` keys. |
| `POST /api/social/import` | `data/social_state.json` | Scoped local metadata update for importing a tweet/social signal from the desktop Signals/Pulse panel. Local research only; does not trigger trades. |
| `/api/catalyst-cards` | `data/catalyst_cards.json` | Generated catalyst cards. |
| `/api/settings` | `data/bot_settings.json` | Read-only settings snapshot. |

## Decision Path Map

| Decision | Inputs | Modules |
| --- | --- | --- |
| Candidate decision ledger | mint, detected time, source event, signal wallets, social matches, risk/holder/mechanics checks, quote/liquidity checks, rule outcomes, final action, lane, later result | `core/decision_ledger.py`, `core/scanner.py`, `paper_trader.py`, `core/storage.py`, `desktop_api.py` |
| Candidate scoring | wallet signal, market/liquidity, token age, launch age, dev reputation, token mechanics | `core/scanner.py`, `core/scoring_engine.py`, `core/confirmation_filter.py` |
| Anti-rug decision | liquidity, token age, dev score, token mechanics, sell quote feasibility | `core/anti_rug.py`, `core/dev_analyzer.py`, `core/token_inspector.py` |
| Token-2022 risk | mint account owner, parsed extensions, authority fields, default account state | `core/token_inspector.py` |
| Dev reputation | developer wallet metadata, bonded/migrated token count, known bad/suspicious flags | `core/dev_analyzer.py`, `dev_reputation.json` |
| Paper entry | candidate score, risk result, quote result, settings, position sizing, paper lane, explicit non-live eligibility for exploration | `paper_trader.py`, `core/scanner.py`, `core/paper_exploration.py` |
| Paper Exploration Lane | near-miss score, edge score, confirmation result, strategy guard, hard-block status, market sanity, buy quote, sell quote, configured exploration size | `core/paper_exploration.py`, `core/scanner.py`, `data/paper_trades.json`, `/api/paper-review` |
| Paper exit | trade state, partial profit rules, stops, exit advisor | `paper_trader.py`, `core/exit_advisor.py` |
| Protected mint status | current price/liquidity, peak/baseline drawdown, token mechanics, wallet token balance, prepared simulation exit intent | `core/rug_watchdog.py`, `core/protection_exit.py`, `core/token_balance.py` |
| Fast open-position monitor | open paper/protected positions, lightweight market snapshots, liquidity/market-cap/price drawdown, quote degradation, exit-rule state | planned boundary; should be separate from `core/rug_watchdog.py` deep inspection |
| Holder concentration risk | largest token accounts, supplied holder rows/account balances | `core/rug_watchdog.py`, `core/holder_concentration.py` |
| Token snapshots | watchdog status, scanner entries/skips, paper entries/exits, market metrics, mechanics, holder concentration, prepared exit quote status | SQLite `token_snapshots`, `core/rug_watchdog.py`, `core/scanner.py`, `paper_trader.py` |
| Trade-stream candles | parsed swap/tick rows grouped into 1s/5s/30s/1m OHLC candles; sampled snapshots only as fallback | SQLite `swap_ticks`, `desktop_api.py`, `core.position_cockpit.build_candles`, `core.scanner.Scanner.record_swap_tick_from_event`, future exact DEX instruction parser |
| Live launch feed | recent `scanner_skip`, `scanner_entry_candidate`, and `scanner_runtime_skip` snapshots, including Dexscreener metadata when present | `desktop_api.py`, SQLite `token_snapshots`, `infra/market_checker.py`, native desktop GUI |
| Scanner tape | raw tracked-wallet buy/sell events before candidate qualification | `desktop_api.py`, SQLite `events`, native desktop GUI |
| Candidate wallet discovery | local scanner buy/sell events, winning paper-trade mints, optional read-only Solana token-owner deltas, existing wallet performance | `core/wallet_discovery.py`, `utils/discover_candidate_wallets.py`, `core/wallet_discovery_scheduler.py`, `data/candidate_wallets.json`, `data/wallet_discovery_status.json` |
| Wallet discovery scheduler | timed local-only discovery cycle by default, paper-watch sync, wallet apply dry-run preview, scheduler heartbeat | `core/wallet_discovery_scheduler.py`, `utils/run_wallet_discovery_scheduler.py`, `launcher.py`, `data/runtime_status.json` |
| Wallet lifecycle | candidate review action, paper-watch membership, tracked-wallet paper performance, win rate, average PnL, score, rolling 7d/30d windows, behavior labels, per-wallet postmortem rollups | `core/wallet_lifecycle.py`, `utils/sync_paper_watch_wallets.py`, `data/paper_watch_wallets.json`, `data/wallet_behavior.json`, native Wallets tab |
| Wallet behavior and postmortem | paper trade outcomes, signal token ages, hold times, signal volume, paper win/loss windows, best/worst wallet outcome, exit/failure reasons | `core/wallet_behavior.py`, `core/wallet_discovery_scheduler.py`, `data/wallet_behavior.json` |
| Selected-token wallet confidence | token-matched wallet signals, paper trade wallet attribution, wallet performance, behavior labels, and postmortem rollups | `desktop_api.py`, native Details tab, `data/wallet_performance.json`, `data/wallet_behavior.json`, `data/paper_trades.json` |
| Cockpit wallet confidence | recent wallet signals, open paper-trade wallet attribution, wallet performance, behavior labels, and postmortem rollups | `desktop_api.py`, native Cockpit tab, `data/wallet_performance.json`, `data/wallet_behavior.json`, `data/paper_trades.json` |
| Wallet review decision | operator approve/hold/reject selection for a lifecycle row | `desktop_api.py`, native Wallets tab, `data/wallet_review_decisions.json` |
| Wallet list apply | approved review decisions, lifecycle report, tracked wallets, paper-watch wallets, bad wallets; promotions require paper-watch evidence and a promotion lifecycle recommendation; apply runs under a local lock with unique backup stamps | `core/wallet_list_apply.py`, `utils/apply_wallet_review.py`, `desktop_api.py`, native Wallets tab, `data/wallet_review_decisions.json`, `data/wallet_list_update_audit.json` |
| Catalyst cards | token snapshots, social matches, wallet confirmation, risk fields, paper outcomes | `core/catalyst_cards.py`, `data/catalyst_cards.json` |
| Social import | pasted account, text, URL, keywords, and optional mint from desktop Signals/Pulse | `desktop_api.py`, `data/social_state.json`, native/static desktop GUI |
| Social event matching | token name/symbol/mint against active social keywords, tickers, and extracted mints | `social/social_signal.py`, `core/scanner.py` |
| Position cockpit action intent | selected paper/protected token, operator button press, live execution lock | `core/position_cockpit.py`, `data/position_action_intents.json` |
| Live execution permission | environment, safety flags, wallet/config, explicit arming | `core/execution_safety.py`, `execution/*` |

## Freshness And Reliability Notes

- `data/runtime_status.json` is the heartbeat file. If a component is stale there, the dashboard should treat related data as stale too.
- `core/data_freshness.py` classifies important state sources as fresh, stale, old, missing, or broken and renders those results in the Data Store panel.
- `live_state.json` and `data/live_state.json` can diverge. Future work should pick a canonical live-state file and make the other a compatibility alias or remove it.
- SQLite is useful for querying and persistence, but several panels still read JSON directly. Treat SQLite as durable memory, not yet the only source of truth. `/api/alerts` now prefers SQLite alert rows with a live-state fallback.
- Candidate decisions are currently reconstructed from scanner snapshots, paper trades, wallet state, social state, and catalyst cards. This should be replaced by `decision_records` as the canonical source before strategy tuning or live-readiness claims.
- Deep watchdog state and fast open-position monitoring should be separate sources. The UI must not label slow deep-inspection freshness as real-time exit protection.
- Any future live execution feature must write an audit record before and after every attempted order.

## When Adding A New Feature

1. Decide the runtime source file/table.
2. Decide the durable history table or JSON ledger.
3. Add a freshness/last-updated field.
4. Add the dashboard panel or Token Console field.
5. Update this map and `research/BUILD_PLAN.md`.
