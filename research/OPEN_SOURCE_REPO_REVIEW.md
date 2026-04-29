# Open Source Repo Review

Last updated: 2026-04-29

Reviewed:

- `https://github.com/keidev-sol/Solana-meme-trading-bot`
- `https://github.com/Immutal0/solana-meme-trading-agent`
- `https://github.com/chainstacklabs/pump-fun-bot`
- `https://github.com/ahk780/solana-copy-trading-bot`
- `https://github.com/pumpfun-sol/Solana-Pumpfun-Trading-Bot`
- `https://github.com/Tee-py/solana-txn-parser`
- `https://github.com/mpandzo/solana-watch`
- `https://github.com/Shyft-to/solana-defi`

## Summary

Both repos are useful as product and architecture references, but neither should be copied directly into MemeTraderPro right now.

The current project goal is a local confirmation-trading and protection cockpit. The strongest reuse path is to study ideas, dependencies, and data models, then reimplement only the pieces that fit our safety-first paper/live-gated architecture.

## Licensing / Copying Risk

- `keidev-sol/Solana-meme-trading-bot` did not include an obvious root license file in the cloned repo. Treat direct code copying as unsafe unless a clear license is added by the author.
- `Immutal0/solana-meme-trading-agent` has `"license": "ISC"` in `package.json`, but no obvious standalone root license file was found in the quick review. Treat small conceptual reuse as fine, but avoid copying large code blocks verbatim without a deeper license pass.

Decision: do not paste their code into MemeTraderPro. Use clean-room reimplementation of selected ideas.

## keidev-sol/Solana-meme-trading-bot

What it is:

- Rust + React + Tauri desktop app.
- Focused on token creation, Pump.fun bundling, wallet groups, buying/selling, and token management.
- Has a useful desktop-app direction for our eventual pro GUI.

Potentially useful ideas:

- Tauri as a future pro desktop shell.
- React/Tailwind operational UI layout.
- Job manager/progress monitor concept for long-running actions.
- Wallet group management patterns.
- Explicit priority fee/slippage config areas.
- Rust backend if we later need lower-latency execution or wallet tooling.

Reasons not to integrate directly now:

- It is aimed more at token launch/bundling than our confirmation-trading edge.
- Bundling/volume-generation/anti-detection features do not align with our safety-first operator cockpit.
- Different stack from current Python/Streamlit runtime.
- Unclear license.
- It would be a large rewrite before our data model, paper evidence, watchdog, and safety gates are mature.

Recommended use:

- Keep as a future GUI inspiration source.
- Recreate the job/progress pattern in Python first, then consider Tauri/React once the backend is stable.

## Immutal0/solana-meme-trading-agent

What it is:

- TypeScript/Node AI agent stack.
- Includes Solana integrations, Jupiter, Helius/Birdeye style market data, social/AI components, trust scoring, simulation selling, Redis/Postgres/Mongo/RabbitMQ style infrastructure.

Potentially useful ideas:

- Trust/recommender scoring model.
- Token performance records including liquidity, holder changes, rapid dump, suspicious volume, and recommendation history.
- Simulation-selling service concept.
- Caching/retry patterns around market APIs.
- Social/narrative intelligence as a future input stream.
- Holder concentration and high-value holder analysis.

Reasons not to integrate directly now:

- It is much heavier than our local-first workstation.
- Requires infrastructure we do not need yet: RabbitMQ, Redis, Postgres/Mongo-style services.
- Some formulas are broad or questionable for our very early launch window.
- Different runtime stack.
- Direct code copying still needs a deeper license pass.

Recommended use:

- Reimplement a compact version of its useful concepts inside our Python system:
  - token performance snapshots,
  - wallet/recommender trust history,
  - holder concentration checks,
  - suspicious volume/unique wallet ratios,
  - paper/simulation exit records.

## Actionable Additions For MemeTraderPro

Best near-term features to pull conceptually:

1. Job/progress tracking
   - Add a local job ledger for watchdog checks, SQLite sync, backfills, replay runs, and future GUI actions.
   - Surface status, percent, step, started/finished timestamps, and errors in the dashboard.

2. Protected-position action queue
   - Add prepared paper/simulation sell intents before any live sell.
   - Include reason, alert level, suggested amount, quote status, and safety gate result.

3. Token performance snapshot table
   - Store liquidity, market cap, price, holder count, wallet count, volume, token mechanics risk, and quote feasibility at entry/skip/exit/watchdog check time.

4. Holder concentration module
   - Use Helius/RPC token accounts where possible.
   - Add warnings for top-holder concentration, linked holder patterns, and sudden holder balance shifts.

5. Wallet/recommender trust model
   - Promote wallets only with paper evidence.
   - Track recommendation win rate, median drawdown, median hold time, rapid-dump exposure, and consistency.

6. Future GUI direction
   - Tauri + React is a strong candidate for the pro desktop app after backend/data model maturity.
   - Do not migrate from Streamlit until strategy and protection workflows are proven.

## Decision

Use both repos as reference material, not dependencies.

Immediate priority remains:

- watchdog status and paper/simulation exits,
- complete risk snapshots on every decision,
- holder concentration checks,
- stronger wallet trust scoring,
- runtime/job progress visibility,
- continued paper-first execution safety.

## Additional Open Source Search

The user asked whether searching for more open-source options is useful. Answer: yes, but only selectively. Most public "meme trading bot" repos are either too sniper-focused, too promotional, poorly licensed, incomplete, or designed around live private-key execution. The useful layer is lower-level infrastructure and specific algorithms.

## Strongest Candidate: Chainstack Pump.fun / Bonk.fun Bot

Repo: `https://github.com/chainstacklabs/pump-fun-bot`

License: Apache-2.0.

Why it matters:

- Python project, closer to our current stack.
- Direct on-chain pump.fun / letsbonk.fun interaction without relying on random third-party APIs.
- Includes multiple listener paths: logs, blocks, Geyser, PumpPortal.
- Includes learning examples for new-token listening, migrations, bonding-curve progress, PumpSwap, manual buy/sell, and IDL parsing.
- Includes a token bucket RPC rate limiter and retry thinking.
- Tracks recent pump.fun program upgrade details and account-list changes.

Best clean-room additions for us:

- `logsSubscribe` / `blockSubscribe` listener comparison as a research/backtest tool.
- Bonding-curve progress watcher.
- Pump.fun migration listener.
- RPC rate limiter pattern.
- IDL/account-list validation discipline.

What not to do:

- Do not turn MemeTraderPro into a 3-second sniper.
- Do not enable direct buy/sell logic from this repo until our safety gates and paper evidence are strong.
- Do not copy large code chunks without preserving Apache notices.

Priority: high as reference material.

## Useful Candidate: ahk780 Solana Copy Trading Bot

Repo: `https://github.com/ahk780/solana-copy-trading-bot`

License: MIT in `package.json` and README.

Why it matters:

- Simple copy-trading structure.
- Local JSON position tracking.
- SAFE mode with stop-loss/take-profit.
- Trailing stop loss concept.
- Emergency sell concept.
- Jito execution configuration.

Best clean-room additions for us:

- Trailing-stop state fields for protected/paper positions.
- Emergency liquidation design, but only as a simulated/prepared action for now.
- Position ledger fields for stop-loss, take-profit, trailing activation, highest price.

Risks:

- Depends on CoinVera APIs for price/copy feeds.
- Focused on mirroring a wallet, not validating edge.
- Live private-key execution is central to the repo.

Priority: medium. Good ideas, not a direct dependency.

## Low Priority / Mostly Avoid: pumpfun-sol Trading Bot

Repo: `https://github.com/pumpfun-sol/Solana-Pumpfun-Trading-Bot`

License: MIT file exists, but the license placeholder is not filled in.

Why it is less useful:

- Promotional/product-style README.
- Features include volume generation, pump orders, liquidity management, antidump behavior, and mass transactions.
- Some goals do not align with our safer confirmation-trading cockpit.
- The code is small and older-looking compared with Chainstack.

Potentially useful:

- Basic Python manual buy/sell examples and trade logging.

Priority: low. Avoid unless a specific small idea is needed.

## Transaction Parsing Candidates

### Tee-py Solana Transaction Parser

Repo: `https://github.com/Tee-py/solana-txn-parser`

License: MIT.

Useful because:

- Parses PumpFun and RaydiumV4 transactions.
- Provides a clean action model: create, complete, trade.
- Output includes token mint, trader, buy/sell flag, token/SOL amount, timestamp, and virtual reserves.

Potential use:

- Study its event model for our wallet tracker and skipped-candidate ledger.
- If we add a Node/TypeScript sidecar later, consider direct dependency.

Priority: medium.

### mpandzo Solana Watch

Repo: `https://github.com/mpandzo/solana-watch`

License: not obvious in quick review.

Useful because:

- Real-time observer/parser for PumpFun, PumpSwap, MoonIt, Raydium, and Raydium Launchpad.
- Clear explanation of slot/block observation and IDL/custom parser needs.

Potential use:

- Architecture reference for transaction parsing.

Priority: low to medium due unclear license and small adoption.

### Shyft Solana Defi Examples

Repo: `https://github.com/Shyft-to/solana-defi`

License: MIT.

Useful because:

- Large collection of Yellowstone gRPC parsing examples for Pump, Meteora, Raydium, Orca, and more.
- Good reference if we later add gRPC/low-latency parsing.

Potential use:

- Study gRPC parser examples when moving beyond RPC/WebSocket polling.
- Use as a future execution/data-feed roadmap reference.

Priority: medium to high for future low-latency work, not immediate Streamlit/Python work.

## Non-Code / API Ideas Worth Considering

- RugCheck API: useful for external risk enrichment, but should be treated as an additional signal, not a single source of truth.
- `getTokenLargestAccounts`: good first holder concentration method for Solana token distribution checks.
- CoinGecko new pools endpoint: potentially useful as a discovery feed, but not a replacement for on-chain event watching.
- Helius parsed/enhanced transactions: useful for wallet tracker accuracy and postmortems.

## Recommended Open-Source Integration Plan

1. Add a holder concentration module using native Solana RPC methods first.
2. Add a token snapshot table/ledger for risk state at entry, skip, exit, and watchdog check.
3. Add a job/progress ledger inspired by desktop/job-manager patterns.
4. Add trailing-stop and prepared paper-exit state fields for protected manual positions.
5. Study Chainstack's listener examples and build our own safe listener comparison mode.
6. Later, evaluate Shyft/Yellowstone gRPC examples for faster wallet/token feeds.

## Bottom Line

The user is not barking up the wrong tree. Open source is useful here, but the edge will not come from cloning another bot. The edge comes from combining:

- robust data feeds,
- risk/mechanics inspection,
- wallet reputation,
- paper evidence,
- fast but gated exits,
- clean local operator UX.

The best immediate reference is Chainstack's Apache-2.0 Python pump.fun bot. The best near-term ideas from the broader search are holder concentration, token performance snapshots, job/progress monitoring, direct listener comparisons, and prepared simulated exits.
