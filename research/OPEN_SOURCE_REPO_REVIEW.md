# Open Source Repo Review

Last updated: 2026-05-12

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

## 2026-05-12 Hot Market Radar Search

Context:

- RKC/Red Kitten Crew was missed because the app was wallet-first. It had no broad hot Dex/Pump discovery lane, so a token could run hard without entering the decision ledger.
- The new path should add discovery breadth without diluting the core product: every hot-feed candidate must be paper-only, lane-labeled, risk checked, decision-recorded, and measured both as Market Radar Co-Main and separately from wallet-main.

### Best Reference: Flotapponnier/pulse-sniper

Repo: `https://github.com/Flotapponnier/pulse-sniper`

Why it matters:

- Fresh-token feed architecture, WebSocket reconnect/resubscribe discipline, and SQLite dedup keyed by chain/address.
- Quality gate pattern: score new tokens before acting, using holder concentration, pool growth, trending, and trader composition concepts.
- Good model for future streaming discovery if polling Dexscreener is too slow.

Use clean-room concepts only:

- Dedup hot candidates before they create repeated paper decisions.
- Keep a quality gate before quote checks.
- Track rejected tokens too, because misses matter as much as buys.

### Useful Endpoint Reference: Ziondido/DexscreenerAPI

Repo: `https://github.com/Ziondido/DexscreenerAPI`

Why it matters:

- Clear organization of Dexscreener token profiles, latest boosts, top boosts, token orders, and pair endpoints.
- Confirms that latest profiles/boosts/top boosts are reasonable starter surfaces for a light Market Radar Lane.

Use clean-room concepts only:

- Keep endpoint access thin and local to our Python service.
- Do not add a TypeScript dependency just to call simple public endpoints.

### Useful Scoring Reference: NadirAliOfficial/Solana-New-Pairs

Repo: `https://github.com/NadirAliOfficial/Solana-New-Pairs`

Why it matters:

- Python new-pair scoring direction aligns with our current stack.
- Useful concepts: liquidity, transaction count, holder distribution, liquidity-lock checks, historical performance, and weighted scoring.

Caution:

- The repo includes a `.env` file in its tree. Treat it as a reference only and do not copy config patterns.

### Useful Risk Reference: hcrypto7/rug_token_checker

Repo: `https://github.com/hcrypto7/rug_token_checker`

Why it matters:

- Raydium new-token detection plus RugCheck-style safety evaluation.
- Useful future input for Market Radar risk: creator, safety score, holder balances, and Raydium liquidity-pool detection.

Use clean-room concepts only:

- Feed rug/risk evidence into decision records.
- Keep it as a gate and label, not a live-buy trigger.

### Decision For MemeTraderPro

Implemented now:

- Dexscreener polling-based Market Radar Lane, paper-only.
- Co-main paper review and outcome analytics for wallet-main plus `market_radar`, while preserving separate lane stats.
- Exploration Lane auto-pause after poor early paper outcomes.

Future only if needed:

- Add WebSocket/PumpPortal/Mobula-style discovery after we prove Dexscreener polling misses too many high-quality runners.
- Add deeper Raydium/Pump launch listeners only under the same decision-ledger and paper-only rules.

## Additional Open Source Search

The user asked whether searching for more open-source options is useful. Answer: yes, but only selectively. Most public "meme trading bot" repos are either too sniper-focused, too promotional, poorly licensed, incomplete, or designed around live private-key execution. The useful layer is lower-level infrastructure and specific algorithms.

## 2026-05-12 Broad Meme/Solana Search

### wagmi97/SolClaw

Repo: `https://github.com/wagmi97/SolClaw`

Why it matters:

- Very relevant product reference: Solana memecoin algo IDE, token nursery, live chart, order-book tape, paper trading, performance tab, and AI-assisted strategy knob control.
- Clean-room concepts for this project: a token nursery split into New / Heating Up / Watch / Rejected / Paper Bought, visible paper-performance review, and operator-adjustable strategy knobs that still write auditable settings.

### wagmi97/Meme-Radar

Repo: `https://github.com/wagmi97/Meme-Radar`

Why it matters:

- Mostly Reddit meme-stock trend tracking, not Solana trading.
- Useful for social catalyst hygiene: scan cadence, evidence posts/comments, rising/fading attention, sentiment terms, and trend charts.
- Not directly useful for execution or Solana token risk.

### Immutal0/dexscreener-analysis-bot-meme

Repo: `https://github.com/Immutal0/dexscreener-analysis-bot-meme`

Why it matters:

- Direct Market Radar reference: Dexscreener-based meme analysis with volume, liquidity, security/rugcheck, Solana/Base token discovery, and anomaly-style filters.
- Clean-room concepts now mapped into Market Radar Quality Gate V2: liquidity quality, volume/liquidity anomaly detection, social proof, and route/risk gating before entry.

### boluwatifee4/pump.fun-Token-tracker

Repo: `https://github.com/boluwatifee4/pump.fun-Token-tracker`

Why it matters:

- Pump.fun-specific tracker for price movement, trading activity, bonding curve progress, whale activity, bot-like behavior, unique buyers, and top-holder concentration.
- Best future use: add a Pump Lifecycle lane or evidence panel, not a live sniper path.

### chainstacklabs/pumpfun-bonkfun-bot

Repo: `https://github.com/chainstacklabs/pumpfun-bonkfun-bot`

Why it matters:

- Apache-2.0 Python reference for Pump.fun / LetsBonk lifecycle mechanics, bonding curve completion, PumpSwap migration, listener patterns, and RPC rate-limit discipline.
- Clean-room use only: lifecycle state, migration detection, and listener/backtest architecture.

### petershepherd/j33t-intel

Repo: `https://github.com/petershepherd/j33t-intel`

Why it matters:

- Solana meme-token intelligence reference with risk/potential scoring direction: rug score, potential score, coordinated wallets, dev-sell status, and liquidity-lock style evidence.
- Future fit: enrich decision records and the GUI risk panel.

### MemeTrans / SolRPDS / SOLMEMES

References:

- MemeTrans paper: `https://arxiv.org/abs/2602.13480`
- SolRPDS: `https://github.com/DeFiLabX/SolRPDS`
- SOLMEMES dataset: `https://huggingface.co/datasets/rucyfer/solmemes`

Why they matter:

- These are research/data references rather than trading bots.
- Useful concepts: launch context, trading activity, holder concentration, time-series behavior, liquidity add/remove history, bundle-linked wallets, and rug-pull labels.
- Future fit: offline backtests and decision-ledger feature expansion.

Implemented from this research:

- Market Radar Quality Gate V2 blocks thin liquidity, weak market cap, poor liquidity-to-market-cap structure, abnormal H1 volume versus liquidity, collapsing H1 momentum, one-sided flow, micro-transaction spam, too-fresh pairs, stale resurrected pairs without fresh strength, and missing social/site proof before spending quote budget.
- Dex source bonuses are capped to the strongest single source, so latest profile + boost + top boost stacking cannot override weak quality signals.

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

## Rohun Vora Repo Review

User prompt:

- Review `https://github.com/rohunvora` from the perspective of MemeTraderPro.
- Look for pieces worth adapting into our safety-first local Solana meme trading cockpit.

Reviewed locally in `/tmp/rohunvora-mtp-review` for research only. No external repo code was copied into MemeTraderPro.

### Licensing / Reuse Boundary

User update:

- Diane checked with Rohun Vora directly.
- Rohun said to use anything needed and that the work is completely open source.

Reuse call after permission:

- Rohun Vora repos may be used as implementation references or source material for MemeTraderPro where useful.
- Keep attribution in notes/commit messages when adapting meaningful pieces.
- Prefer adapting only the relevant pieces instead of importing whole unrelated apps.
- Preserve any existing license notices where license files exist.
- Still keep secrets, API keys, and generated/runtime files out of the repo.

Repos with explicit or visible MIT-style reuse signals:

- `rohunvora/paste-trade` - MIT license.
- `rohunvora/walletdoctor` - MIT license.
- `rohunvora/traderfm` - MIT license, lower relevance.
- `rohunvora/x-research-skill` - permission confirmed by user; public repo does not show a root license in the quick clone.
- `rohunvora/twitter-feedback` - README mentions MIT; permission confirmed by user.

Repos now allowed by direct permission, but still best adapted selectively:

- `rohunvora/tweet-price-charts` - high-value social/price analytics reference.
- `rohunvora/why-pump` - no obvious license file; README says abandoned learning project.
- `rohunvora/my-cmc` - no obvious license file.
- `rohunvora/chart-ai` - README says private/all rights reserved, but direct permission from Rohun overrides for Diane's project use. Still use selectively.

Decision: use what is needed, but do it intentionally. The best path remains adapting the strongest pieces into MemeTraderPro's Python/local safety-first architecture rather than wholesale app merges.

### Highest-Value Candidate: paste-trade

Repo: `https://github.com/rohunvora/paste-trade`

License: MIT.

What it is:

- Agent workflow for turning a source into trade theses, routing those theses to instruments, locking prices, and tracking P&L.
- Accepts sources such as tweets, videos, articles, PDFs, screenshots, or typed hunches.
- Uses a thesis lifecycle: saved, routing, routed/dropped, posted.
- Separates author/source price from posted/platform price.

Why it matters for MemeTraderPro:

- This maps well to our desired candidate lifecycle:
  - source/social/on-chain trigger,
  - thesis/catalyst card,
  - candidate token/instrument,
  - entry price snapshot,
  - paper outcome tracking,
  - postmortem.
- Its "author price vs posted price" distinction should become our "signal time price vs operator/action time price" distinction.

Clean-room additions to consider:

1. Add a local `signal_thesis` or `candidate_card` schema:
   - source type,
   - source timestamp,
   - discovered timestamp,
   - token mint,
   - thesis,
   - evidence links,
   - route/status,
   - signal price,
   - observed/action price,
   - invalidation/kill conditions.
2. Add P&L lenses:
   - signal P&L from first source/signal time,
   - platform/operator P&L from when MemeTraderPro surfaced or paper-entered it.
3. Add candidate state machine:
   - `detected -> enriched -> scored -> paper_entered | skipped -> monitored -> closed/postmortem`.

Priority: high. Best near-term product/data-model reference.

### Highest-Value Candidate: walletdoctor

Repo: `https://github.com/rohunvora/walletdoctor`

License: MIT.

What it is:

- High-performance Solana wallet analytics using Helius RPC and batch fetching.
- Uses paged `getSignaturesForAddress`, batch transaction parsing, concurrency controls, price caching, and parse metrics.
- README targets sub-20-second analysis for wallets with thousands of trades.

Why it matters for MemeTraderPro:

- Our wallet intelligence is one of the likely edges.
- We already track wallet quality/performance locally, but need stronger backfill, parse-rate metrics, and evidence about whether a wallet is actually good.

Clean-room additions to consider:

1. Add wallet analytics backfill jobs:
   - signatures fetched,
   - signatures parsed,
   - trades parsed,
   - parse rate,
   - errors,
   - elapsed seconds.
2. Add concurrency/rate-limit discipline for Helius batch calls.
3. Add per-wallet evidence fields:
   - unique tokens traded,
   - realized/paper P&L,
   - average hold time,
   - median drawdown,
   - rapid dump exposure,
   - entry market cap where available.
4. Add progress status to the dashboard for long wallet backfills.

Priority: high. Strong technical reference for wallet intelligence.

### Highest-Value Candidate: tweet-price-charts

Repo: `https://github.com/rohunvora/tweet-price-charts`

License: no obvious license file in quick clone. Direct project use approved by Rohun via Diane.

Permission update: Diane confirmed Rohun approved using anything needed.

What it is:

- Analytics platform correlating founder/adopter tweets with token price action.
- Tracks multiple crypto assets, including Solana meme assets.
- Has asset configs, multi-source price fetching, tweet alignment, outlier warnings, statistics, chart markers, and automated updates.

Why it matters for MemeTraderPro:

- This is directly relevant to social-signal scoring.
- Its most useful concept is not "tweets make price go up"; it is careful alignment of tweet timestamps, price candles, baselines, and outlier handling.

Clean-room additions to consider:

1. Add curated account/token watchlists:
   - token mint,
   - primary ticker/keyword filter,
   - founder/KOL/adopter account,
   - launch date,
   - price source,
   - notes.
2. Add social-event-to-price alignment:
   - price at post,
   - 5m/15m/1h/4h follow-up returns,
   - volume/liquidity change,
   - whether the move beat no-post baseline.
3. Add outlier warnings for sniper candles instead of silently removing them.
4. Add "quiet period" and "burst period" social features as evidence, not trade triggers.

Priority: high as a reference. Direct reuse is allowed by permission, but clean adaptation is still preferred.

### Useful Candidate: x-research-skill

Repo: `https://github.com/rohunvora/x-research-skill`

License: no obvious license file in quick clone. Direct project use approved by Rohun via Diane.

Permission update: Diane confirmed Rohun approved using anything needed.

What it is:

- X/Twitter research CLI for search, profile pulls, threads, watchlists, caching, engagement filters, quick mode, JSON/Markdown output, and cost display.

Why it matters for MemeTraderPro:

- We need cheap pulse checks and watchlist monitoring for meme narratives.
- The cost-aware quick mode and caching are the key ideas.

Clean-room additions to consider:

1. Add an X watchlist config for KOLs/founders/adopters.
2. Add quick pulse checks with:
   - one-page limit,
   - no-retweet/no-reply filters,
   - engagement threshold,
   - one-hour cache.
3. Save research outputs to local JSON/Markdown artifacts for later audit.
4. Surface estimated API cost per run before making high-volume queries.

Priority: medium-high. Operationally useful, but license unclear.

### Useful Candidate: why-pump

Repo: `https://github.com/rohunvora/why-pump`

License: no obvious license file in quick clone. Direct project use approved by Rohun via Diane.

Permission update: Diane confirmed Rohun approved using anything needed.

What it is:

- "Catalyst card" system for explaining why Solana tokens pump/dump.
- Attempts to correlate on-chain events, social activity, and market data.
- README itself notes data-quality, cost, and hallucination risks.

Why it matters for MemeTraderPro:

- Catalyst cards are a strong UI/data primitive for explainable candidates and skipped trades.
- The cautionary notes are as useful as the feature idea: do not let AI hallucinate causal explanations.

Clean-room additions to consider:

1. Add catalyst cards with strict evidence requirements:
   - type,
   - direction,
   - severity,
   - confidence,
   - time horizon,
   - evidence links,
   - source timestamps,
   - what would invalidate it.
2. Separate observed facts from AI narrative.
3. Require at least one non-AI source for high-severity cards.

Priority: medium-high. Good product concept; implement defensively.

### Useful Candidate: twitter-feedback

Repo: `https://github.com/rohunvora/twitter-feedback`

License: README mentions MIT, and direct project use was approved by Rohun via Diane.
License: README mentions MIT, and Diane confirmed Rohun approved using anything needed.

What it is:

- Fetches replies/quotes for a tweet, stores them locally, and produces dashboards/AI insights.

Potential MemeTraderPro use:

- Measure community reaction to a token/KOL post.
- Track whether replies are bullish, skeptical, bot-like, or asking for contract/liquidity details.
- Use incremental watermarks and local SQLite for crash-safe social ingestion.

Priority: medium.

### Lower-Priority Candidates

`rohunvora/my-cmc`

- Useful as a fundamentals-style dashboard reference for protocol revenue/buyback context.
- Less relevant for very early meme tokens, more useful for listed protocols such as PUMP, HYPE, RAY, etc.
- Direct project use approved by Rohun via Diane; still lower priority than the social/wallet/catalyst work.

`rohunvora/chart-ai`

- Interesting structured chart-analysis product: regime, support/resistance, scenarios, invalidation.
- README says private/all rights reserved, but Diane confirmed Rohun approved using anything needed. Use selectively and keep attribution.
- Could inspire a future "chart read" panel, but not a priority until our data and paper evidence are stronger.

`rohunvora/traderfm`

- MIT and useful for community/trader profile ideas.
- Low immediate relevance to local trading cockpit.

## Recommended Rohun-Inspired Integration Plan

1. Add candidate/catalyst card schema and lifecycle.
   - Inspired by `paste-trade` and `why-pump`.
   - Store every candidate's source, evidence, status, signal price, action price, P&L lenses, invalidation, and final outcome.

2. Upgrade wallet analytics backfills.
   - Inspired by `walletdoctor`.
   - Add batch progress, parse metrics, error counts, and wallet evidence fields before promoting wallets.

3. Add social signal alignment.
   - Inspired by `tweet-price-charts`.
   - Align X/KOL/founder events to token price/volume/liquidity windows and compare against baselines.

4. Add X watchlist pulse checks.
   - Inspired by `x-research-skill`.
   - Keep it cached, cost-aware, and audit-friendly.

5. Add explainable catalyst cards to the dashboard.
   - Use strict evidence links and separate observed facts from AI-generated narrative.

## Rohun Review Bottom Line

There is real signal here. The best pieces to adapt are product/data-model patterns, not wholesale code:

- `paste-trade` for signal-to-thesis-to-P&L lifecycle,
- `walletdoctor` for Solana wallet analytics/backfill discipline,
- `tweet-price-charts` for social-to-price alignment,
- `x-research-skill` for cheap social pulse checks,
- `why-pump` for explainable catalyst cards.

Immediate next build recommendation:

- Add a `candidate/catalyst card` ledger and use it as the central bridge between social signals, wallet signals, risk checks, paper entries, skips, and postmortems.

## Rohun Vora Full Repo Sweep - Additional Findings

Date: 2026-04-29

Source:

- GitHub profile: `https://github.com/rohunvora?tab=repositories`
- GitHub API inventory and local read-only clones under `/tmp/rohunvora-full-review`

Scope:

- Reviewed the broader repo list, not only the first five high-signal projects.
- No code was copied into MemeTraderPro.
- User says Rohun gave direct permission to use anything needed. Still prefer selective adaptation with attribution.

### Additional High-Value Ideas

#### `twitter-feedback`

Repo: `https://github.com/rohunvora/twitter-feedback`

What it adds beyond `tweet-price-charts`:

- Reply/quote analysis for a specific X post.
- Incremental watermarks and local SQLite storage.
- Basic analysis plus optional AI insight reports.

MemeTraderPro adaptation:

- Add a community-reaction layer for KOL/founder posts:
  - bullish support,
  - skeptical replies,
  - bot-like replies,
  - contract-address requests,
  - rug/insider warnings,
  - notable smart-account replies.
- Use this as evidence on catalyst cards, not as an automatic buy trigger.
- Save reply/quote snapshots locally so we can later compare reaction quality against paper outcomes.

Priority: high for social edge after the catalyst-card ledger exists.

#### `chart-ai`

Repo: `https://github.com/rohunvora/chart-ai`

What it adds:

- Structured chart analysis output:
  - regime,
  - support/resistance zones,
  - bullish/bearish scenarios,
  - invalidation rules,
  - follow-up chat/context.

MemeTraderPro adaptation:

- Add a future "Chart Read" panel for tokens already being watched.
- Keep output deterministic and evidence-labeled:
  - current regime,
  - support zone,
  - breakdown invalidation,
  - take-profit / stop-zone suggestions.
- Avoid AI-only trade authority. The chart read should support operator judgment and paper-trade postmortems.

Priority: medium-high for the pro GUI, lower than watchdog/quote feasibility.

#### `rrcalc`

Repo: `https://github.com/rohunvora/rrcalc`

What it adds:

- Fast expected-value and risk/reward calculator.
- Inputs map well to meme trades: entry market cap, target market cap, position size, max loss, confidence.

MemeTraderPro adaptation:

- Add an operator sizing widget:
  - entry market cap,
  - target market cap,
  - invalidation market cap or max loss,
  - confidence,
  - position size,
  - expected value verdict.
- Use this to explain why the bot suggests "paper only", "watch", "small size", or "fold".

Priority: medium-high. Very useful for disciplined manual confirmation mode.

#### `my-cmc`

Repo: `https://github.com/rohunvora/my-cmc`

What it adds:

- Revenue/buyback leaderboard and protocol fundamentals dashboard.
- Curated verification of buyback mechanics.

MemeTraderPro adaptation:

- Not useful for fresh pump launches.
- Useful for mid/large listed Solana ecosystem tokens and context around protocols like PUMP/RAY.
- Reuse the curation mindset: verified mechanism, not marketing claims.

Priority: medium-low for meme launch bot, useful later for broader Solana cockpit.

### GUI / Product Quality References

#### `anti-slop-library`

Repo: `https://github.com/rohunvora/anti-slop-library`

What it adds:

- Detects generic AI-generated UI patterns.
- Provides concrete design alternatives.

MemeTraderPro adaptation:

- Use as a quality gate when we build the pro GUI:
  - avoid generic purple-gradient SaaS look,
  - keep trading UI dense, legible, and operator-focused,
  - flag vague marketing copy and repetitive card grids.

Priority: medium for the GUI phase.

#### `taste-library`

Repo: `https://github.com/rohunvora/taste-library`

What it adds:

- Visual reference ingestion, tagging, and searchable design libraries.

MemeTraderPro adaptation:

- Use the idea, not necessarily the tooling, for a local design reference folder:
  - trading dashboards,
  - risk consoles,
  - execution panels,
  - alert timelines,
  - mobile confirmation flows.

Priority: medium for GUI/marketing polish.

### Agent / Workflow References

#### `github-tndr`

Repo: `https://github.com/rohunvora/github-tndr`

What it adds:

- Telegram bot framework with pluggable tools, skills, progress tracking, and dependency injection.

MemeTraderPro adaptation:

- Useful architectural inspiration if we later add mobile/Telegram alerts:
  - narrow tools,
  - testable skills layer,
  - progress callbacks,
  - multi-provider AI.

Priority: low-medium. Good future alerting pattern, not core trading edge today.

#### `cool-claude-skills`

Repo: `https://github.com/rohunvora/cool-claude-skills`

What it adds:

- Reusable skill patterns, especially `incremental-fetch`, `quick-view`, `table-filters`, and `html-style`.

MemeTraderPro adaptation:

- The most relevant idea is resilient API ingestion:
  - save after each page,
  - track cursor/watermark,
  - resume interrupted fetches,
  - avoid duplicate downloads.
- This overlaps with the social tracker and wallet backfill work.

Priority: medium as implementation discipline.

#### `cursor-habits` / `cursor-maxxing`

What they add:

- Turning chat history and repeated instructions into persistent workflow rules.
- Sharing full prompt/build history for reproducibility.

MemeTraderPro adaptation:

- Useful for our own agent workflow, not bot features:
  - keep `AGENT_WORKFLOW.md` and `WORK_LOG.md` current,
  - extract recurring decisions into permanent repo rules,
  - reduce drift between sessions.

Priority: low-medium. Helps development quality.

#### `openclaw`

Repo: `https://github.com/rohunvora/openclaw`

What it adds:

- Large local-first assistant/control-plane architecture.
- Strong ideas around channels, pairing, security defaults, local gateway, and tool routing.

MemeTraderPro adaptation:

- Do not merge this into MemeTraderPro.
- Borrow selectively later if building:
  - local desktop app control plane,
  - mobile alerts,
  - permissioned operator commands,
  - paired-device controls.

Priority: low for current trading edge; medium for long-term desktop/mobile product architecture.

### Low Immediate Relevance

These are not worth near-term integration:

- `just-fucking-cancel` - popular, but unrelated to trading except general agent workflow patterns.
- `twitch-to-youtube`, `video-to-claude`, `physics-vid`, `course-ai`, `courseai` - media/course workflows, not trading.
- `meme-gem` - meme generation, marketing-only at best.
- old school/project repos and calculators unrelated to Solana/social/wallet risk.
- `pnl-scraping-test` - cloned repo appeared empty except `.git` metadata in this sweep, so no useful pattern found.

### Updated Rohun-Inspired Build Order

1. Keep Phase 6 safety work first:
   - quote/sell-route feasibility,
   - watchdog timeout hardening,
   - holder/risk snapshots.
2. Add local candidate/catalyst card ledger.
3. Add social event ingestion:
   - manual/import first,
   - X watchlist pulse later,
   - reply/quote reaction layer after basic catalyst cards.
4. Add price/social alignment:
   - signal price,
   - action/paper-entry price,
   - 5m/15m/1h returns,
   - volume/liquidity changes,
   - sniper/outlier warnings.
5. Add wallet analytics backfill from tracked wallets.
6. Add dashboard views:
   - catalyst cards,
   - social reaction quality,
   - wallet confirmation,
   - risk flags,
   - postmortem outcome.
7. Add EV/risk sizing widget for confirmation-mode trades.
8. Use `anti-slop-library` / `taste-library` ideas when replacing Streamlit with the pro GUI.

### Practical Takeaway

The biggest edge from Rohun's repo ecosystem is not a single bot script. It is a product architecture:

- every candidate needs a source,
- every source becomes a thesis,
- every thesis gets evidence,
- every entry/skip locks the market state at that moment,
- every outcome feeds back into wallet/social/risk scoring.

That should become the core data model behind MemeTraderPro's competitive advantage.

## 2026-05-09 Social Catalyst / Discovery Repo Sweep

Purpose:

- Replace manual-only social catalyst import with automated, auditable collection.
- Keep the current priority on the canonical decision ledger.
- Use public repos as references or dependencies only when licensing, API terms, and architecture fit the safety-first local cockpit.

### Meme Radar Reference

Repo: `https://github.com/wagmi97/Meme-Radar`

What it is:

- Next.js / TypeScript Reddit meme-stock scanner.
- Extracts stock tickers from Reddit posts/comments.
- Scores weighted sentiment, stores evidence, and ranks trending/fading stocks.

Useful concepts:

- Scan cadence and source freshness.
- Mention velocity and rank-delta thinking.
- Evidence links per mention.
- Sentiment categories and keyword weights.
- Public/API dashboard shape for top trending and fading items.

Limits:

- It is equity ticker focused, not Solana mint focused.
- Stock whitelist and Reddit subreddit choices do not transfer directly.
- It should inspire the social/catalyst workflow, not be merged.

### Recommended Social Collection References

| Repo | License | Use | Stance |
| --- | --- | --- | --- |
| `https://github.com/praw-dev/asyncpraw` | BSD-2-Clause | Async Reddit API wrapper. | Best first automated collector. |
| `https://github.com/tweepy/tweepy` | MIT | Official X/Twitter API client. | Preferred production X collector if API access exists. |
| `https://github.com/vladkens/twscrape` | MIT | X GraphQL scraping/search patterns. | Experimental only; disable by default due ToS/account risk. |
| `https://github.com/LonamiWebs/Telethon` | MIT | Telegram MTProto client. | Useful for authorized public channels/groups. |
| `https://github.com/Rapptz/discord.py` | MIT | Discord bot/client library. | Useful for opted-in servers/channels. |
| `https://github.com/cjhutto/vaderSentiment` | MIT | Lightweight social sentiment. | Good baseline, but extend with crypto/meme slang. |
| `https://github.com/ArchiveBox/ArchiveBox` | MIT | Durable URL/post evidence capture. | Strong future evidence layer. |

### Recommended Solana / Meme Discovery References

| Repo | License | Use | Stance |
| --- | --- | --- | --- |
| `https://github.com/0xfnzero/solana-streamer` | MIT | PumpFun/PumpSwap/Bonk/Raydium event streaming model. | Best future launch-discovery reference. |
| `https://github.com/chainstacklabs/pumpfun-bonkfun-bot` | Apache-2.0 | Pump.fun / LetsBonk listener, migration, bonding curve, IDL concepts. | Use listener/account-layout concepts only. |
| `https://github.com/petershepherd/j33t-intel` | MIT | Local meme-token analysis/risk cockpit ideas. | Strong product/risk reference. |
| `https://github.com/Shyft-to/solana-defi` | MIT badge in README | Yellowstone gRPC parsing examples. | Useful parser reference; confirm license before copying. |
| `https://github.com/Immutal0/dexscreener-analysis-bot-meme` | no obvious license | DexScreener filters, social presence, anomaly checks. | Conceptual reference only unless licensing is clarified. |
| `https://github.com/savantpseudoist/Solana-Token-Purchase-Monitor` | MIT | Python Helius wallet purchase monitor with Telegram alerts and DexScreener. | Useful alert/monitoring reference. |

### Integration Decision

The next project step does not change: finish React/Tauri Replay Decision Ledger polish first.

The new repo findings change what comes immediately after:

1. Add social/catalyst evidence fields to decision records.
2. Add collector status/freshness so automated sources cannot silently go stale.
3. Add Reddit collection first using official/compliant API access.
4. Add official X collection second if credentials are available.
5. Keep Telegram/Discord and Solana launch-discovery enrichment behind separate adapters.
6. Add evidence capture and social-to-price alignment only after normalized events exist.

Do not create social-only buy logic. Automated catalysts should raise review priority, enrich decision records, and improve postmortems.
