# 🚀 MemeTraderPro – Updated Project State & Handoff

## Last Updated
2026-05-09

## Project Location
```bash
~/Desktop/Jordan/meme_trader_pro
```

---

# ⚙️ How To Run

## Backend
```bash
python main.py
```

## Dashboard
```bash
python -m streamlit run dashboard/dashboard.py
```

## Optional Debug Utilities
```bash
python debug_pipeline.py
python find_state_files.py
```

---

# 🧱 Current File Structure

Main folders:
```txt
core/
execution/
infra/
dashboard/
data/
utils/
```

Important root files:
```txt
main.py
paper_trader.py
bot_settings.py
live_state.json
```

Important data files:
```txt
data/paper_trades.json
data/wallet_performance.json
data/social_state.json
data/manual_watchlist.json
data/live_state.json
```

---

# ✅ Current Working System

## 2026-05-09 Roadmap Correction

The active project center is now the canonical Decision Ledger, not another disconnected dashboard panel.

Next build order:

1. Monitor the hourly Reddit collector for clean runs, rate-limit errors, duplicate quality, and noisy keywords before adding more sources.
2. Improve holder/cluster risk with pool/system-account labels and a real owner/funder graph source; current scanner records explicitly mark linked-wallet graph risk as not checked.
3. Continue canonical read-path migration only where a SQLite table, backfill, and parity guard exist.
4. Continue paper collection before strategy judgment: 50 closed main-lane trades minimum, 100 preferred, and 50+ exploration-lane trades before serious wallet promotion/demotion tuning.

Completed on 2026-05-09:

- React/Tauri Replay Decision Ledger parity with the static desktop view: filters, clickable decisions, selected-decision detail, and paper-trade fallback when no decision records exist.
- Backend decision records now carry richer route feasibility, holder/cluster risk, social/catalyst evidence, context-only broader-market/stablecoin regime fields, and paper-outcome details.
- React/Tauri Decision Detail now exposes route feasibility, holder/cluster risk, social/catalyst evidence, market context, and paper outcome from the canonical backend record.
- Social collector freshness/staleness indicators now exist in the desktop API, Signals view, and System view before Reddit automation is added.
- `/api/trades` is now SQLite-first after JSON parity, with JSON fallback and mirror diagnostics. `/api/alerts` is SQLite-first with live-state fallback. `/api/tokens/{mint}/snapshots` and `/api/positions/{mint}` declare their source contracts, and wallet/social payloads now declare JSON source contracts without pretending they are migrated.
- Scanner candidate decisions now run bounded holder concentration checks for quote-worthy or near-entry candidates. Holder `DANGER` becomes a hard block before paper entry; linked-wallet graph risk is recorded as not checked until a real linkage source exists.
- Standalone Reddit collector foundation now exists and is scheduled hourly through Codex automation `reddit-social-collector`. It writes normalized local social evidence into canonical social `events`, updates `runtime_status.social_collectors.reddit`, rebuilds catalyst cards, and remains non-trading. First live observation pass stored 6 posts, rebuilt catalyst cards, and brought social freshness to OK.
- `/api/paper-review` now includes a decision-ledger lane report for main, exploration, and protected/manual lanes. The native Paper Review panel renders this beside trade-state metrics.
- SQLite sync can now backfill decision outcomes from paper trades when `signal_metadata.decision_id` is present. The current local historical paper trades do not have decision IDs, so they remain trade-only history.

Completed on 2026-05-10:

- Fast open-position monitoring now exists separately from the deep watchdog. It uses cheap market quote/liquidity checks to refresh open paper positions more frequently without running holder, wallet-balance, mint-mechanics, or quote-feasibility deep checks.
- Decision outcome analytics now expose grouped canonical outcomes through `/api/decision-analytics` and the Replay/Paper Review surface: social catalyst, wallet-only, quote-failed, hard-risk, lane, and overall summaries.
- Reddit collector hygiene now rejects obvious noisy discussion/mod posts, dedupes repeated Reddit IDs within a run, reports duplicate/rejection counts, and keeps broader source expansion blocked until decision analytics prove social lift.
- Jupiter Price API pressure control is live. Market data now uses a longer cache, provider cooldowns after `429`, serialized provider requests, and Dexscreener cooldown fallback. The Jupiter dashboard recovered to roughly 99.5% success / 0.45% error in the last-hour view after the fix.
- Helius `getTransaction` pressure control is live in the scanner. The runtime now dedupes concurrent same-signature fetches, reuses a 5-minute transaction cache, paces transaction RPC calls at 8 rps by default, drops websocket messages only if backlog exceeds the guard, and surfaces transaction pressure counters in runtime status.
- Deep watchdog RPC pressure control is implemented for mint inspection, owner token balances, holder largest-account checks, and prepared exit quote feasibility. Repeated watchdog loops now reuse short-lived deep-check results and back off after rate-limit responses instead of competing with scanner transaction parsing.
- Scanner websocket subscription ids are now mapped back to wallets, and per-wallet backpressure prevents a single noisy wallet from filling the entire transaction-processing queue.
- Exploration Lane now has a paper-only route-failed observation mode for sample acceleration. Strong signals that fail route feasibility can be tracked as tiny `$5` exploration samples with `route_observation_only=true` and `live_should_trade=false`; main-lane readiness and live execution remain unaffected.

Readiness estimate for a full-week high-quality paper run:

- Current estimate: about 92/100 after SQLite-first trades/alerts, source-contract visibility, live scanner holder-risk decision wiring, hourly Reddit collector scheduling, lane-separated decision-ledger reporting, decision-outcome backfill support, fast open-position monitoring, Reddit hygiene, decision outcome analytics, provider/deep-watchdog pressure controls, and scanner per-wallet queue isolation.
- Still below 95 because enough closed main/exploration paper trades are not collected yet, provider pressure controls need longer live observation, Reddit automation needs clean-run history with low duplicate/noise rates, and historical trades without `decision_id` cannot be joined safely.

Manual social import remains useful for testing, but it is only a bridge. Future social automation must feed the decision ledger as evidence, not become a social-only trade trigger.

Broader crypto and stablecoin inputs should stay context-only for now. They can warn, annotate, or reduce confidence in memecoin candidates, but adding stablecoin or broad-market trading would dilute the first complete iteration.

## 🔌 Data Layer
- Helius WebSocket tracking ~518 wallets
- Real-time transaction parsing
- Token balance delta detection for buys/sells

## 🧠 Signal Layer
- Wallet-based signal detection
- Token clustering by time window
- Weighted wallet signal scoring
- Wallet performance signal tracking

## 🧠 Intelligence Layer
- Wallet quality scoring
- Wallet performance tracking
- Dev wallet detection/scoring exists conceptually
- Anti-rug system exists conceptually with penalties/hard blocks
- Token age tracking from bot-seen time
- Token launch-age tracking for early detection

## 💧 Market Layer
- Dexscreener fallback data
- Liquidity scoring
- Volume scoring

## 💱 Execution Layer
- Jupiter buy quote check
- Jupiter sell quote check for exit liquidity
- Slippage and impact filtering
- Current trading is still paper trading only

## 💰 Trade Layer
- Dynamic position sizing
- Paper trading system
- Trade attribution to wallet signals
- Trade state is saved in:
```txt
data/paper_trades.json
```

## 📊 Dashboard Layer
- Dashboard runs with Streamlit
- Dashboard now needs to read from multiple correct state files, not just `data/live_state.json`
- Correct dashboard data sources are:
```txt
live_state.json                    -> alerts/events
data/paper_trades.json             -> open_trades, closed_trades, failed_trades
data/wallet_performance.json       -> wallet performance signals
data/manual_watchlist.json         -> manual trade protection watchlist
```

---

# 🚨 Important Recent Discovery

The previous dashboard was reading mostly empty/stale state:
```txt
data/live_state.json
```

But the real bot data was found in these files:
```txt
./live_state.json
  - alerts=list[100]
  - events=list[150]

./data/wallet_performance.json
  - signals=list[715]

./data/paper_trades.json
  - open_trades=list[2]
  - closed_trades=list[6]
  - failed_trades=list[0]
```

This means dashboard counts and trade visibility were wrong because the UI was pointed at the wrong state files.

---

# ✅ Dashboard Fix Status

A full dashboard replacement was provided that:
- Reads alerts/events from `live_state.json`
- Reads paper trades from `data/paper_trades.json`
- Reads wallet signals from `data/wallet_performance.json`
- Reads manual protection entries from `data/manual_watchlist.json`
- Shows raw trade data inside expanders so field-name mismatches are visible

Current dashboard goal:
- Make open trades fully readable
- Show token, entry MC, current MC, value, PnL, reason, and raw data
- Help diagnose why some fields are blank by exposing the raw JSON per trade

If trade values still show blank, the issue is likely that `paper_trader.py` is not saving fields like:
```txt
entry_market_cap
current_market_cap
entry_value
current_value
pnl
pnl_pct
entry_reason
```

Next fix may need to be inside `paper_trader.py`, not the dashboard.

---

# 🛡️ Manual Trade Protection Feature

## Goal
Allow manual Axiom trades to be pasted into the dashboard so the bot can monitor them and eventually auto-sell if rug conditions appear.

## Intended workflow
```txt
1. User buys token manually on Axiom
2. User pastes token mint / contract address into dashboard
3. User optionally enters wallet address
4. Bot watches token for danger
5. Dashboard displays risk status
6. Later: if real execution is connected, bot auto-sells on danger
```

## Input should be
```txt
Token Mint / Contract Address
```

Not dev wallet.

## Current manual protection file
```txt
data/manual_watchlist.json
```

Initial contents if missing:
```json
[]
```

## Current feature status
- Dashboard input panel exists / was provided
- Watchlist file support exists
- Alert-only concept exists
- Auto-sell toggle exists in UI but real auto-sell is NOT connected yet
- Rug watchdog file was discussed but real on-chain detection is not finished

---

# 🧯 Rug / Scam Lessons Learned From Live Trading

Recent live examples showed that:

## Locked liquidity is not enough
A token can show a locked-liquidity icon but still collapse if:
- Only part of LP is locked
- Lock is fake/misclassified
- Token-2022 mechanics allow fee extraction
- Dev/insider wallets drain value another way
- Pool backing asset is drained while the pool technically still exists

## Most important rug signals to detect
```txt
Dev wallet receiving SOL repeatedly
Fees: Claim events
Pool SOL balance dropping fast
Large token -> pool sell clusters
Jupiter sell quote collapsing
Token-2022 risk flags
Liquidity falling while market cap still looks high
```

## Practical rule
```txt
Market cap is an illusion. Liquidity is reality.
```

---

# 🎯 Current Strategy: Sniper Mode

Current intended flow:
```txt
1. Tracked wallet buys token
2. Wallet quality/performance evaluated
3. Weighted wallet signal calculated
4. Early trigger OR cluster trigger
5. Full scoring engine runs
6. Risk system applied
7. Jupiter buy + sell quotes checked
8. Position size calculated
9. Paper trade created
10. Dashboard displays open position
```

---

# ⚠️ Current Problem To Fix Next

Night session summary showed:
```txt
Total events: 1
Buys: 1
Sells: 0
Evaluated alerts: 0
Performance signals: 715
Open trades: 2
Closed trades: 6
Failed trades: 0
No alerts scored.
```

Initial concern was “why no buys?”

Debugging found the dashboard was reading the wrong files, but the deeper issue may still be:
```txt
signals exist, but they may not be turning into evaluated alerts/trades reliably
```

Need to verify the actual signal -> alert -> score -> buy pipeline.

---

# 🔎 Debug Files Created / Suggested

## `debug_pipeline.py`
Purpose:
- Inspect `data/live_state.json`
- Show top-level keys
- Show signals/alerts/trades if present

Result showed `data/live_state.json` was mostly empty.

## `find_state_files.py`
Purpose:
- Walk project JSON files
- Find where alerts, signals, and trades are actually stored

Result found real state in:
```txt
live_state.json
data/wallet_performance.json
data/paper_trades.json
```

These files can be kept for future debugging.

---

# 🧠 Trading Rules Learned From Live Session

## Avoid
```txt
Post-dump bounces
Dead-cat bounces
Vertical pump tops
Coins with huge sell clusters at highs
High bundler % launches
Holding after structure breaks
Waiting to “get back to entry”
```

## Prefer
```txt
Very early clean strength
Healthy first pullback
Higher low formation
Reclaim + continuation
Strong liquidity relative to market cap
Clear exit plan before entry
```

## Manual exit rules
```txt
Take partial profit at +10% to +25%
Exit if structure breaks
Exit if key support is lost
Exit if sell clusters hit after weak bounce
Do not let a green trade turn red
```

---

# 🚀 Roadmap To Pro-Level System

## Phase 1: Fix Dashboard + Trade Visibility
Status: In progress

Needed:
- Dashboard must show real open/closed trade fields
- If fields are missing, update `paper_trader.py` to save full metadata
- Show exact entry reason, wallet signal, MC, value, and PnL

## Phase 2: Fix Signal -> Alert -> Trade Pipeline
Status: Next priority

Need to confirm:
```txt
wallet event -> signal -> alert -> score -> risk check -> quote check -> paper buy
```

Add durable logging for:
```txt
alerts_created
alerts_evaluated
skip_reasons
quote_blocks
paper_buys
paper_sells
```

## Phase 3: Manual Trade Protection Watchdog
Status: UI started, engine not complete

Build:
```txt
core/rug_watchdog.py
execution/emergency_seller.py later
```

First real detection should use:
```txt
Jupiter quote collapse
pool liquidity drop
large sell clusters
dev wallet SOL inflow
Token-2022 warnings
```

## Phase 4: Auto Partial Sell / Exit Management
Status: Not built

Goal:
- Take profit automatically at configured levels
- Trail winners
- Kill position if structure breaks

## Phase 5: Real Execution
Status: Not built

Needed before real auto-sell:
```txt
Jupiter swap execution
private key/wallet handling
priority fees
slippage controls
retry logic
failover routing
```

## Phase 6: Social Catalyst Engine
Status: Planned

Build:
```txt
social/x_monitor.py
social/social_state.json
```

Logic:
```txt
SOCIAL ONLY -> no trade
SOCIAL + 1 elite wallet -> evaluate
SOCIAL + 2 wallets -> strong
SOCIAL + cluster -> high conviction
```

## Phase 7: Discovery Scanner
Status: Planned

Sources:
```txt
Dexscreener new pairs
Pump.fun launches
Raydium pools
```

Goal:
- Catch tokens before tracked wallets
- Feed clean candidates into scoring engine

## Phase 8: Momentum Engine
Status: Planned

Signals:
```txt
volume acceleration
liquidity inflow
price velocity
healthy pullback/reclaim
```

---

# 📌 Operating Rules

Very important:
```txt
Use full file replacements only.
Do not provide tiny snippets unless explicitly requested.
Verify file paths before assuming.
Use real logs and JSON state as truth.
Fix one system at a time.
No blind auto-buy logic.
Paper mode first, real execution later.
```

---

# ✅ Recommended Next Prompt For Another Chat

Paste this into the next chat:

```txt
Continue MemeTraderPro from this updated project state.
Use full pasteable files only.
Current priority: fix trade visibility and then fix the signal -> alert -> trade pipeline.

Known correct state files:
- live_state.json = alerts/events
- data/wallet_performance.json = signals
- data/paper_trades.json = open/closed/failed trades
- data/manual_watchlist.json = manual protection watchlist

Do not assume data/live_state.json is the main state file anymore.
First task: inspect/repair dashboard trade display and then update paper_trader.py so every trade saves entry MC, current MC, entry value, current value, PnL, PnL %, token mint, reason, and timestamps.
```

---

# 🧠 Current Status Summary

MemeTraderPro is roughly 70% toward a serious professional system.

Working:
```txt
wallet tracking
signal generation
paper trading
basic dashboard
state files
manual protection UI concept
```

Needs immediate work:
```txt
correct trade metadata display
paper trade field completeness
signal -> alert -> score -> buy reliability
real rug watchdog detection
manual trade protection engine
auto-sell only after real execution is safely built
```

Main priority now:
```txt
Make the bot explain every trade clearly, then make it consistently evaluate and trade qualified signals.
```

## 2026-05-10 Update: Paper Activity Lane

The current bottleneck is not only trade strictness; after restart, many wallet events are too weak to trigger a full candidate evaluation, so the decision ledger can sit still for long stretches.

Implemented a paper-only activity evaluation trigger:

```txt
mid-quality wallet buy -> candidate evaluation -> normal risk/quote/confirmation checks -> tiny exploration sample only if eligible
```

Main/live criteria are still unchanged. This is meant to increase labeled paper observations and make the dashboard feel alive while preserving the difference between:

```txt
main strategy trade
exploration observation
hard-risk skip
quote/route failure
confirmation miss
```
