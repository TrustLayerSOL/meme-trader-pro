# MemeTraderPro Owner's Manual

This manual is for the person operating MemeTraderPro. It avoids code terms when possible and describes what the current repo does today.

## What MemeTraderPro Does

MemeTraderPro watches Solana meme-token activity and helps you review possible trades without sending real orders.

It is built around a few jobs:

- Watch tracked wallets for buys and sells.
- Notice early token launches and wallet clusters.
- Score tokens with liquidity, launch age, wallet quality, social signals, and rug-risk checks.
- Open and manage paper trades only.
- Watch manually protected tokens for price drops, liquidity drains, risky token mechanics, and exit warnings.
- Show all of that in a local desktop cockpit.

The current system is an operator cockpit and paper-trading workstation. It is not a live trading bot.

## Starting the System

The launcher can start the main local pieces:

- Dashboard.
- Paper bot.
- Protection watchdog.
- Wallet discovery scheduler.

Start System now starts all four. Wallet Discovery has its own status row and its own log file at `logs/wallet_discovery.log`.

The wallet discovery scheduler keeps review data fresh. It does not buy, sell, promote wallets by itself, or unlock live trading.

The double-click desktop launcher reuses a healthy local desktop API if one is already running. This avoids duplicate local API sessions on port `8765`.

## Current Trading Status

MemeTraderPro is paper-only right now.

Live execution is locked in the desktop app and in the backend safety code. The current execution settings say:

- Paper trading is enabled.
- Live trading is disabled.
- Auto-sell is disabled.
- Desktop API routes are read-only, except for local metadata-only editors for protected-token amounts, protected-token watch entries, wallet review decisions, approved wallet-list apply, and social research imports.
- When launched through the desktop app or fallback desktop command, metadata edits require a local session token.
- The desktop app verifies that the saved session token belongs to the currently running local API process. If an old API is still running, the app will not blindly trust a stale token.
- Buy, sell, exit-now, add-position, and protect-position buttons in the desktop app are disabled.

The app can request Jupiter quotes for checking route feasibility and price impact, but those quote checks do not place trades.

## Desktop App Tabs

The desktop app has these main tabs.

### Cockpit

This is the main screen.

It shows current paper positions and manual protected tokens, the selected token, price/liquidity chart data, scanner activity, live launch candidates, protection state, signal matches, recent snapshots, and paper-trade lifecycle data.

The execution state panel is visible here, but buy, add, exit, and live trading remain locked.

The selected-token chart supports Market Cap, Price, and Liquidity views plus 1s, 5s, 30s, and 1m intervals. The static desktop shell uses the open-source TradingView `lightweight-charts` renderer so the chart has normal trading-chart axes, candles, crosshair, scroll zoom, and drag/pan behavior. The UI refreshes the selected token every second when auto-refresh is enabled.

Important chart note: the chart now has a tick-first backend path. If `swap_ticks` exist for the selected mint, the chart labels the data as `swap ticks` and uses tick-derived OHLC candles. Scanner wallet events now calculate execution-price ticks only when the transaction contains a known swap route program and same-transaction SOL/USDC/USDT balance deltas are available. Non-route balance changes fall back to market-enriched ticks instead of being treated as exact swap prices. If no ticks exist yet, the chart falls back to local market snapshots and labels the data as `sampled quotes`. The next accuracy upgrade is route-level pool attribution.

### Portfolio

This is the easiest place to review trading results.

It shows total paper PnL, open-position PnL, closed-trade PnL, open trade count, closed trade count, and failed attempt count.

Below the totals, it separates:

- Open Positions: paper trades still being monitored.
- Closed Trades: completed paper exits with each trade's PnL.
- Failed Attempts: paper entries that failed, were blocked, or could not fill.

Use this tab when you want to know what the bot is in, what each trade is doing, and what the full paper-trading result is so far.

Click any trade row to open its detail card. The detail card shows market cap in, market cap out or current market cap, entry and exit/current price, entry and current liquidity, size, PnL, fees, opened/closed time, entry reason, exit/failure reason, wallets, and recorded sell events.

The Portfolio tab also includes Winner Pattern Review. This compares closed winners against closed losers and lists repeatable traits, top winning wallets, top winners, worst losers, and review actions. Treat this as paper-tuning evidence only until the system has a larger closed-trade sample.

### Details

This shows deeper information for the selected token.

Use it when you want more context than the cockpit summary provides.

### Protection

This is for manually watched or protected tokens.

It shows risk level, price from peak, liquidity from peak, token mechanics, holder information, quote status, suggested sell plan, and exit-readiness checks.

It also includes local protection metadata forms:

- Add Protected Token: paste a token mint / CA so the watchdog can monitor it.
- Protected Amount: save a token amount or raw token amount for simulation and route-readiness checks.

These forms do not buy, sell, or unlock auto-sell. If the desktop API was launched with a session token, the app must also be opened from the desktop launcher so those metadata forms can save.

### Wallets

This shows wallet intelligence.

It includes tracked wallet scores, recent wallet signals, paper outcomes tied to wallets, and candidate wallets that may deserve review.

### Signals

This shows scanner tape, launch candidates, and selected-token social or catalyst matches.

Use it to understand why a token appeared in the system.

Signals also includes Social / Tweet Import. Paste a post, source account, URL, keywords, and optional token mint / CA to save local social research. This does not place trades, unlock live execution, or bypass token risk checks.

### Replay

This shows paper-trade history.

It separates open paper trades, closed trades, and failed trades.

It also includes Paper Profitability Review. This review shows whether there are enough closed paper trades to judge performance, the current win rate, PnL, expectancy, profit factor, drawdown, entry reasons, exit reasons, failure reasons, and wallet-label exposure. Treat fewer than 50 closed paper trades as an early signal only, not a meaningful profitability test.

The review separates Main Strategy trades from Exploration Lane trades. Main Strategy is the stricter confirmation setup. Exploration Lane is paper-only and uses smaller simulated size to test safe near-misses without changing the main strategy scorecard. The app treats main-strategy readiness separately, so exploration volume does not make the main strategy look proven.

### Ops

This is the operator view.

It shows strategy settings, safety status, refresh rates, runtime freshness, provider health, and redacted local log tails.

### System

This shows readiness and data freshness.

It checks whether key local files exist, whether runtime components are fresh, and how many rows are in the local SQLite store.

## Scanner and Live Feed

The scanner watches wallet activity and records buy/sell events.

The desktop app has two important feed views:

- Scanner Tape: raw tracked-wallet buys and sells before strategy filters.
- Live Launch Feed: recent scanner candidates, including tokens that were skipped or blocked.

The scanner can evaluate a token when wallet activity is strong enough. It looks at wallet count, weighted wallet score, repeated buys, liquidity, volume, launch age, social matches, risk checks, confirmation rules, Jupiter quote checks, and strategy guard results.

If a token passes enough checks, the system can open a paper trade. It does not open a real trade.

The scanner also has a paper-only Exploration Lane. This lane can open a small simulated paper trade when a token is close to passing but misses the main score threshold. It still requires the important safety checks: no confirmation block, no strategy-guard block, no hard risk block, acceptable market sanity, a passing buy quote, and a passing sell/exit quote. It is designed to create more evidence for wallet discovery and threshold tuning without pretending those trades are main-strategy wins or live-trade eligible.

## Wallet Intelligence

MemeTraderPro tracks wallet behavior over time.

Wallet intelligence includes:

- How many signals a wallet has produced.
- How many paper entries were tied to that wallet.
- Wins, losses, win rate, average PnL, best PnL, and worst PnL.
- Rolling 7-day and 30-day paper-trade windows.
- Behavior labels such as early-buyer, late-buyer, paper-profitable, follower-trap, high-fee-churner, late-exit, rug-exit-fast, and copy-bait.
- Per-wallet postmortem summaries: closed trades, failed trades, best paper outcome, worst paper outcome, main exit reasons, main failure reasons, and average hold time.
- A wallet score and label.
- Recent wallet signals.
- Paper trades linked to the selected wallet.

The system combines wallet quality and wallet performance when scoring signals.

Behavior labels are advisory. They help explain the wallet review queue, but they do not directly promote wallets, execute trades, or unlock live trading.

The selected-token Details tab also shows Wallet Confidence. This card explains which wallets are connected to the selected token, how many matched signals were seen, how many supporting wallets have profitable paper evidence, how many are trap/copy-bait risks, their average score, and each wallet's recent labels and paper outcomes.

The Cockpit tab also has a Wallet Confidence summary. It rolls up recent signal wallets and open paper-trade wallets so you can quickly see whether the current feed is mostly supported by proven wallets or polluted by trap/copy-bait wallets.

## Candidate Wallets

Candidate wallets are wallets that may be worth watching, but are not automatically promoted into trusted tracked wallets.

The candidate wallet tool builds a watch-only review file from local scanner history and optional read-only mint evidence. It can mark wallets for review, paper-watch, hold-review, promotion-review, demote-review, or reject.

The wallet discovery scheduler refreshes this file on a timer. By default it uses local scanner history, then syncs the paper-watch lane and refreshes the dry-run apply preview.

Important: candidate wallet review does not edit the tracked wallet list by itself.

The Wallets tab also has a Promotion Queue. This queue shows the evidence behind each wallet lifecycle recommendation:

- Trade count.
- Win/loss record.
- Win rate.
- Total PnL.
- Average PnL.
- Rolling 7-day and 30-day summaries.
- Behavior labels.
- Best/worst paper outcome and failed/closed trade counts.
- Wallet score.
- The main reason or blocker.

From that queue, you can save one of four decisions:

- Approve Promote.
- Approve Demote.
- Hold.
- Reject.

Saving one of these decisions only records your choice in `data/wallet_review_decisions.json`. It does not update the tracked wallet list by itself.

The actual list update is a separate controlled apply step shown as Approved List Update in the Wallets tab. It first shows a dry-run preview: how many wallets would be promoted, demoted, or skipped.

The Apply Approved Wallet Changes button is disabled when there are no approved changes ready. When it is enabled and used, the app runs the controlled apply step with a confirmation guard. It backs up the current wallet files, applies only approved decisions, and writes an audit record. A promotion also needs paper-watch evidence and a promotion lifecycle recommendation. The apply step runs under a local lock so two applies cannot safely overlap. It still does not buy, sell, or unlock live trading.

Until that apply step is run, approved wallets stay in review status.

## Paper-Watch Wallets

Paper-watch wallets are wallets the scanner may observe, but they are not treated the same as trusted tracked wallets.

In the current code, the scanner loads paper-watch wallets from `data/paper_watch_wallets.json` if that file exists. These wallets can help the system learn and gather evidence, but they are watch-only and should not be considered live-trade drivers.

This is useful for testing a wallet before deciding whether it belongs in the main tracked wallet set.

Exploration Lane trades can help this process by giving the wallet system more fresh observations. A wallet should still be promoted or demoted based on repeated behavior, not one lucky paper trade.

The paper bot now reloads the paper-watch list while running. When the scheduler adds a new paper-watch wallet, the bot can subscribe to that new wallet without a manual restart.

Current limitation: the live reload path adds new paper-watch wallet subscriptions. It does not unsubscribe removed paper-watch wallets mid-session. Removed or demoted wallets are fully cleaned up on the next bot restart.

## Protection and Watchdog

The protection watchdog watches manually listed tokens.

It checks:

- Current price.
- Current liquidity.
- Price drop from entry and from peak.
- Liquidity drop from entry and from peak.
- Token mechanics and token standard.
- Holder concentration.
- Whether an exit route quote looks feasible.
- Whether a protected amount is available.

The watchdog can prepare a simulated exit intent, such as "watch closely," "prepare partial exit," or "prepare full exit."

It does not execute that exit.

The current protection exit planner is simulation-only. Its own safety note says no live sell is executed.

## Manual Protected Tokens

Manual protected tokens live in the manual watchlist.

They are tokens you want MemeTraderPro to watch for danger signs. The app can show them in the cockpit and protection tab even if they were not opened by the paper trader.

The protection tab lets you add a protected token with:

- Token mint / CA.
- Optional wallet address.
- Optional token amount.
- Decimals.
- Optional raw token amount.
- Exit priority.

For an existing protected token, the protection tab also lets you update:

- Token amount.
- Decimals.
- Raw amount.
- Whether the amount is a test/simulated amount.

This is local protection metadata only. It helps the watchdog and route-readiness checks reason about possible exits. It does not prove the wallet owns the tokens unless the amount came from a real wallet balance lookup.

Treat test amounts as simulation data.

## Social and Catalyst Features

MemeTraderPro has local social-signal and catalyst-card features.

Social signals can store watched account posts, keywords, tickers, mint addresses, sentiment, and source links. The scanner can match a token against local social signals and apply a social catalyst bonus when there is a match.

The desktop Signals tab can import a single social post through `POST /api/social/import`. This saves local research into `data/social_state.json` only. It does not trigger a trade.

Catalyst cards summarize token history from local snapshots. They can combine scanner evidence, social matches, wallet confirmation, paper-trade outcome, watchdog risk, and market data into a short review card.

These features are local signal helpers. They do not guarantee a trade is safe.

## Settings and Adjustable Items

The main strategy settings are stored in `data/bot_settings.json` and loaded through the settings manager.

Settings currently include items such as:

- Strategy mode.
- Score thresholds for sniper, confirmation, and safe modes.
- Jupiter pre-score threshold.
- Weighted wallet trigger and strong-wallet bonus.
- Cluster wallet count and cluster time window.
- Confirmation launch-age limits.
- Confirmation liquidity minimum.
- Confirmation wallet and repeated-buy requirements.
- Paper trade position sizes.
- Paper Exploration Mode: enabled/disabled, near-miss score threshold, edge-score threshold, and smaller simulated position size.
- Strategy guard on/off.

The Ops tab displays these settings, plus safety status and refresh timing.

The desktop app does not currently provide a full settings editor. The protected amount editor and wallet review decision buttons are the main local write actions available in the desktop app.

## Runtime Health

MemeTraderPro tracks runtime health with heartbeat-style status files.

The System and Ops tabs show whether these parts are fresh or stale:

- Bot.
- Websocket.
- Scanner.
- Market checks.
- Quote checks.
- Watchdog.
- Wallet discovery.

If key components are stale, the app may still open, but the displayed market and signal data may be old.

Use the System tab to check readiness and data freshness before trusting what you see.

## Data Files in Plain Terms

These are the important local data files and what they mean:

- `live_state.json`: current local bot/dashboard state and alerts.
- `data/live_state.json`: compatibility copy of live state for older pieces.
- `data/paper_trades.json`: open, closed, and failed paper trades.
- `data/manual_watchlist.json`: manually protected tokens for watchdog review.
- `data/wallet_performance.json`: wallet scoring and paper outcome history.
- `data/wallet_behavior.json`: rolling wallet windows, behavior labels, and per-wallet paper-trade postmortem summaries.
- `data/candidate_wallets.json`: watch-only candidate wallet review list.
- `data/wallet_discovery_status.json`: latest wallet discovery scheduler summary.
- `data/wallet_review_decisions.json`: saved operator decisions for wallet promotions, demotions, holds, and rejects.
- `data/wallet_list_update_audit.json`: audit trail for controlled wallet-list apply runs.
- `data/social_state.json`: local social events and signals.
- `data/catalyst_cards.json`: generated token review/catalyst summaries.
- `data/bot_settings.json`: strategy and paper-trading settings.
- `data/runtime_status.json`: heartbeat status for bot, scanner, quotes, watchdog, and related components.
- `data/tracked_wallets.json`: the main tracked wallet list.
- `data/paper_watch_wallets.json`: optional watch-only wallet list, if present.
- `data/memetrader.db`: local SQLite history for events, alerts, trades, watchlist records, and token snapshots.
- `logs/`: local logs for bot, dashboard, desktop API, and watchdog.

Do not delete or hand-edit these files unless you know exactly why. Many screens depend on them.

## Safety Limits

The current repo includes several safety layers:

- Live trading is disabled in execution config.
- Live execution requires a separate explicit acknowledgement environment value before future live paths can pass.
- Private key material is required before future live paths could pass.
- Position size and price impact limits are checked by the live safety gate.
- Desktop execution mutation routes are blocked. Scoped metadata mutations require the local desktop session token when token protection is active.
- Auto-sell is off.
- Protection exits are simulation-only.
- Paper trades use simulated fills, fees, slippage, failed fills, and price impact.
- Scanner candidates can be blocked by market sanity checks, confirmation checks, rug checks, strategy guard, quote checks, and zero-size checks.

These limits reduce accidental live action, but they do not make meme trading safe. The system is still experimental and should be treated as a research and paper-trading tool.

## What Is Not Live Yet

These items are not live-ready in the current repo:

- Real buy execution.
- Real sell execution.
- Exit Now.
- Auto-sell.
- Real protected-position selling.
- In-app add-position or protect-position actions.
- Automatic promotion of candidate wallets into tracked wallets.
- Full in-app settings editing.
- A complete live-trading audit trail and kill switch.
- Any guarantee that social or catalyst signals are complete.

Before any real-money use, the live execution gates, audit logging, kill-switch behavior, wallet ownership checks, quote checks, operator confirmation flow, and failure handling need explicit review and testing.
