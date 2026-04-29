# MemeTraderPro Product Research Brief

## Positioning

MemeTraderPro should not try to win by being the fastest Telegram sniper. Existing tools already compete hard on raw execution speed, paste-to-buy workflows, and copy-trading convenience.

The stronger wedge is:

```txt
The local Solana meme trading cockpit for safer decisions, wallet intelligence, paper learning, replay, runtime health, and exit protection.
```

Competitors help users trade faster. MemeTraderPro should help users stop donating tuition to the market.

## Table Stakes

Serious meme traders expect:

- Fast buy/sell execution presets
- Slippage, priority fee, and MEV/Jito controls
- New-pair and Pump.fun/PumpSwap discovery
- Wallet tracking and copy trading
- TP/SL, trailing exits, and limit orders
- Token risk checks: liquidity, holder concentration, mint/freeze authority, dev history
- PnL, open positions, realized/unrealized history
- Mobile/Telegram-style alerts

Examples in the market include BONKbot, Trojan, GMGN, BullX, Photon, Axiom, DEX Screener workflows, Birdeye, RugCheck/SolanaTracker-style risk tools, and copy-trading terminals.

## Competitor Openings

Most existing products are strong at:

- Fast execution
- Habit-forming Telegram UX
- Token discovery feeds
- Basic wallet following
- Basic token metadata risk flags

Common gaps:

- Weak explainability
- Weak paper-learning before real copy trading
- Poor local observability and runtime health
- No strong memory of what worked for the user
- Little replay of missed/passed signals
- Entry-focused workflows with weaker exit protection
- Fragmented workflow across charts, bots, scanners, notes, and wallet trackers

## Strong Differentiators To Build

### 1. Local Intelligence Memory

Persist every alert, wallet, token, paper trade, skipped candidate, protected position, exit trigger, and outcome. Build a private learning layer that improves with the user's own data.

### 2. Paper-Copy Engine

Before copying a wallet live, shadow-copy it in paper mode for a meaningful sample. Include realistic delay, slippage, fees, failed fills, and position sizing.

### 3. Wallet Intelligence Database

Label wallets beyond generic "smart money":

- early buyer
- late buyer
- dev-adjacent
- copy-bait
- paper-profitable
- rug-exit-fast
- late-exit
- high-fee churner
- follower trap

Track rolling stats like 7d/30d win rate, median hold time, realized PnL, average drawdown after entry, and whether the wallet sells before followers.

### 4. Exit And Rug Watchdog

Competitors emphasize entries. Meme traders often lose from late exits.

Watch for:

- liquidity drain
- dev or copied-wallet sell
- whale concentration shift
- sell pressure spike
- Jupiter route degradation
- price impact explosion
- volume disappearing
- price down from local high

Start manual-first: alert, prepare sell, paper sell. Add real auto-sell only after execution is hardened.

### 5. Signal Replay Lab

Replay alerts and watched tokens through current strategy rules. Eventually store time-series snapshots so the user can inspect how a token evolved second by second.

### 6. Runtime Health

Show whether the system is actually alive:

- WebSocket connected/subscribed
- latest wallet event
- scanner event counts
- quote API success/rate-limit state
- price feed freshness
- watchdog loop status
- stale JSON/log warnings

### 7. Double-Click Local App

Package the system as a local app experience:

- one launcher
- preflight checks
- start dashboard/bot/watchdog
- no terminal required
- clear logs and health state

## Build Priority

1. Command center and runtime health
2. System readiness/preflight checks
3. Candidate workbench and decision ledger
4. Performance intelligence and strategy guard
5. Wallet intelligence and paper-copy engine
6. Token console with market/risk/quote panels
7. Real exit/rug watchdog
8. Replay lab with strategy comparison
9. SQLite event store
10. Guarded Jupiter live execution

## Current Strategic Rule

Paper mode first. Real execution later.

The system should earn trust by showing what it would have done, why, and how those decisions performed before it ever touches real SOL.
