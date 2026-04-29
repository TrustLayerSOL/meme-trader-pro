# MemeTraderPro Data Source Map

Last updated: 2026-04-29

This map explains where the dashboard and bot state comes from. Use it before changing a panel, parser, storage schema, or strategy rule.

## Primary State Files

| Source | Purpose | Main Readers | Main Writers |
| --- | --- | --- | --- |
| `live_state.json` | Root live signal snapshot used by the dashboard. | `dashboard/dashboard.py`, analyzers | scanner / bot runtime |
| `data/live_state.json` | Data-folder live state snapshot. | storage sync, health checks | runtime utilities |
| `data/paper_trades.json` | Open, closed, and failed paper trades. | dashboard, performance analyzer, postmortem, replay | `paper_trader.py`, bot runtime |
| `data/manual_watchlist.json` | Manually protected mints and watchdog state. | dashboard, watchdog, SQLite sync | dashboard, `core/rug_watchdog.py` |
| `data/wallet_performance.json` | Wallet stats, paper-copy evidence, and wallet scores. | dashboard, wallet labeler, copy engine | wallet performance backfill/runtime |
| `data/candidate_ledger.json` | Operator decisions on candidates, ignored tokens, and protection adds. | dashboard Candidate Workbench | dashboard |
| `data/runtime_status.json` | Component heartbeat and freshness state. | dashboard Runtime Health, health report | `core/runtime_status.py` callers |
| `data/bot_settings.json` | Strategy mode, thresholds, sizing, and confirmation settings. | dashboard Strategy Settings, scanner/scoring | dashboard settings form |
| `data/social_state.json` | Social/sentiment signal state. | dashboard samples, social modules | social modules |
| `data/elite_wallets.json` | Wallet allow/promote list. | wallet intelligence, copy engine | manual edits/tools |
| `data/bad_wallets.json` | Wallet avoid/fade list. | wallet intelligence, copy engine | manual edits/tools |
| `data/tracked_wallets.json` | Wallets watched by the tracker. | wallet tracker/runtime | manual edits/tools |
| `dev_reputation.json` | Optional dev reputation data, including bonded/migrated token counts. | `core/dev_analyzer.py` | manual imports/future Axiom import |

## SQLite Store

SQLite file: `data/memetrader.db`

Managed by: `core/storage.py`

| Table | Purpose | Notes |
| --- | --- | --- |
| `events` | Durable feed of raw wallet/signal events. | Unique index on time, event type, wallet, mint. |
| `alerts` | Durable alert and scoring records. | Stores score, edge verdict, should-trade, risk label, and raw payload JSON. |
| `trades` | Durable paper/live trade snapshots. | Stores summary columns plus full payload JSON. |
| `watchlist` | Durable protected-mint snapshots. | Mirrors manual watchlist entries. |

Backfill/sync utility: `utils/sync_state_to_sqlite.py`

Current stance: JSON files remain the practical runtime source for several panels, while SQLite is the durable query layer. Future work should consolidate more read paths onto SQLite once schemas are stable.

## Dashboard Panel Map

Dashboard file: `dashboard/dashboard.py`

| Panel | Backing Sources | Core Helpers |
| --- | --- | --- |
| Operator Brief | `live_state.json`, `data/paper_trades.json`, `data/manual_watchlist.json`, runtime state | `core/operator_brief.py` |
| Signal Pipeline | `live_state.json` alerts/signals | local dashboard aggregations |
| Command Center | process state, logs, candidate ledger | `core/process_guard.py`, `data/candidate_ledger.json` |
| Opportunity Inbox | `live_state.json` alerts | dashboard filters |
| Candidate Workbench | `live_state.json`, `data/candidate_ledger.json`, `data/manual_watchlist.json` | dashboard update helpers |
| Token Console | `live_state.json`, paper trades, manual watchlist, candidate ledger | `core/token_console.py` |
| Wallet Intelligence | `data/wallet_performance.json`, elite/bad wallet files | `core/wallet_labeler.py` |
| Paper Copy Engine | wallet performance and paper trade state | `core/wallet_copy_engine.py` |
| Performance Intelligence | `data/paper_trades.json`, `live_state.json` | `core/performance_analyzer.py` |
| Trade Postmortem | `data/paper_trades.json` | `core/trade_postmortem.py` |
| Replay Lab | `live_state.json`, `data/paper_trades.json` | `core/replay_analyzer.py` |
| Runtime Health | `data/runtime_status.json`, process table, logs | `core/runtime_status.py`, `core/process_guard.py` |
| System Readiness | env, files, imports, runtime status | `core/system_health.py` |
| Execution Safety | env/config/safety state | `core/execution_safety.py` |
| Data Store | `data/memetrader.db`, state files freshness | `core/storage.py`, `core/data_freshness.py` |
| Strategy Settings | `data/bot_settings.json` | `core/settings_manager.py` |
| Manual Trade Protection | `data/manual_watchlist.json` | dashboard helpers, `core/rug_watchdog.py` |
| Open/Closed/Failed Trades | `data/paper_trades.json` | dashboard trade rendering helpers |
| Alerts | `live_state.json` | dashboard rendering |
| Raw Debug Expanders | JSON state files | dashboard rendering |

## Decision Path Map

| Decision | Inputs | Modules |
| --- | --- | --- |
| Candidate scoring | wallet signal, market/liquidity, token age, launch age, dev reputation, token mechanics | `core/scanner.py`, `core/scoring_engine.py`, `core/confirmation_filter.py` |
| Anti-rug decision | liquidity, token age, dev score, token mechanics, sell quote feasibility | `core/anti_rug.py`, `core/dev_analyzer.py`, `core/token_inspector.py` |
| Token-2022 risk | mint account owner, parsed extensions, authority fields, default account state | `core/token_inspector.py` |
| Dev reputation | developer wallet metadata, bonded/migrated token count, known bad/suspicious flags | `core/dev_analyzer.py`, `dev_reputation.json` |
| Paper entry | candidate score, risk result, quote result, settings, position sizing | `paper_trader.py`, scanner/runtime |
| Paper exit | trade state, partial profit rules, stops, exit advisor | `paper_trader.py`, `core/exit_advisor.py` |
| Protected mint status | current price/liquidity, peak/baseline drawdown, token mechanics | `core/rug_watchdog.py` |
| Live execution permission | environment, safety flags, wallet/config, explicit arming | `core/execution_safety.py`, `execution/*` |

## Freshness And Reliability Notes

- `data/runtime_status.json` is the heartbeat file. If a component is stale there, the dashboard should treat related data as stale too.
- `core/data_freshness.py` classifies important state sources as fresh, stale, old, missing, or broken and renders those results in the Data Store panel.
- `live_state.json` and `data/live_state.json` can diverge. Future work should pick a canonical live-state file and make the other a compatibility alias or remove it.
- SQLite is useful for querying and persistence, but several panels still read JSON directly. Treat SQLite as durable memory, not yet the only source of truth.
- Any future live execution feature must write an audit record before and after every attempted order.

## When Adding A New Feature

1. Decide the runtime source file/table.
2. Decide the durable history table or JSON ledger.
3. Add a freshness/last-updated field.
4. Add the dashboard panel or Token Console field.
5. Update this map and `research/BUILD_PLAN.md`.
