# Social Catalyst Automation Workflow

Last updated: 2026-05-09

## Purpose

Manual social import proved the catalyst-card model, but it cannot be the long-term workflow. Social catalysts need automated collection, durable evidence, token matching, and outcome measurement while staying subordinate to wallet confirmation, quote feasibility, and token-risk gates.

This workflow merges the strongest ideas from Meme Radar and the latest GitHub review into the current MemeTraderPro roadmap.

## Product Rule

Social is evidence, not authority.

```txt
SOCIAL ONLY -> watch / annotate
SOCIAL + 1 trusted wallet -> evaluate
SOCIAL + 2 trusted wallets -> strong paper candidate
SOCIAL + wallet cluster + clean risk + quote feasible -> high-priority paper candidate
```

No social signal may bypass hard token mechanics, holder/cluster risk, quote feasibility, strategy guard, paper-lane separation, or live execution locks.

Broader crypto and stablecoin data can be used as market-regime evidence only. Examples: SOL risk-off moves, USDC/USDT depeg warnings, sector-wide liquidity contraction, or broad meme-cycle heat. These inputs may annotate or reduce confidence in a memecoin candidate, but they should not open a separate stablecoin or broad-market trading strategy inside this product.

## Reference Repos And Concepts

### Social Collection

| Reference | Use | Stance |
| --- | --- | --- |
| `wagmi97/Meme-Radar` | Reddit scan cadence, mention velocity, sentiment, evidence links, rank/change thinking. | Conceptual reference only; stock-ticker logic must be redesigned for Solana mints/symbols. |
| `praw-dev/asyncpraw` | Compliant async Reddit ingestion. | Best first collector to implement. |
| `tweepy/tweepy` | Official X/Twitter API ingestion. | Preferred production X route if API access is available. |
| `vladkens/twscrape` | X search/profile scraping patterns and raw payload structure. | Experimental only; isolate behind feature flag due ToS/account risk. |
| `LonamiWebs/Telethon` | Telegram public-channel/group ingestion. | Useful after Reddit/X basics; respect Telegram account and group constraints. |
| `Rapptz/discord.py` | Opt-in Discord server/channel ingestion. | Useful for owned/authorized servers only. |
| `ArchiveBox/ArchiveBox` | Evidence capture for posts, sites, and announcements. | Strong evidence layer; integrate after normalized events exist. |

### Solana / Meme Discovery

| Reference | Use | Stance |
| --- | --- | --- |
| `0xfnzero/solana-streamer` | Event-ingestion model for PumpFun/PumpSwap/Bonk/Raydium. | Best future launch-discovery reference; verify parsers before relying on it. |
| `chainstacklabs/pumpfun-bonkfun-bot` | Pump.fun / LetsBonk listener, bonding curve, migration, IDL, rate-limit concepts. | Use listener/account-layout concepts only; do not import execution flow. |
| `petershepherd/j33t-intel` | Local Solana meme-token risk cockpit and score presentation ideas. | Good product/risk-panel reference. |
| `Immutal0/dexscreener-analysis-bot-meme` | DexScreener filters, social presence checks, anomaly checks. | Useful enrichment reference; license unclear, avoid code copying. |
| `nixonjoshua98/dexscreener` / `nickatnight/birdeye-py` | Python enrichment adapters. | Optional wrappers; keep adapters replaceable. |

## Target Data Flow

```txt
collector adapter
  -> normalized social event
  -> evidence snapshot / source URL
  -> token match confidence
  -> catalyst card
  -> decision ledger attachment
  -> paper outcome / price alignment
  -> wallet/social/risk scoring feedback
```

## Normalized Social Event

Extend the current `data/social_state.json` event shape with:

```txt
collector
external_id
source_platform
account
account_category
text
url
timestamp
discovered_at
keywords
tickers
mints
sentiment
engagement
source_confidence
match_confidence
matched_mint
matched_symbol
evidence_url
raw
```

The first implementation should keep JSON compatibility with current `SocialSignalEngine`, then add SQLite persistence once event volume grows.

## Catalyst Scoring Inputs

Catalyst score should be explainable and stored with each decision record:

- source credibility,
- exact mint match,
- symbol/name/keyword match confidence,
- mention velocity,
- sentiment and bearish warning terms,
- engagement quality,
- account/category weight,
- reply/quote/community reaction quality when available,
- wallet confirmation,
- holder/cluster risk,
- token mechanics risk,
- buy/sell quote feasibility,
- paper lane and final action.

## Build Order

1. Finish React/Tauri Decision Ledger parity. `Done 2026-05-09`
   - Filters, clickable decisions, detail drilldowns, and canonical read paths come first.
   - The GUI must show why a candidate bought/skipped before automated social data increases volume.

2. Make backend decision records social-ready. `Done 2026-05-09`
   - Add richer fields for `social_event_ids`, catalyst score, match confidence, evidence URL, holder/cluster risk, quote result, and eventual paper result.

3. Expose richer backend evidence in React/Tauri decision details. `Done 2026-05-09`
   - Show route feasibility, holder/cluster risk, social/catalyst evidence, market context, and paper outcome in a clean operator drilldown.

4. Add collector freshness and staleness indicators. `Done 2026-05-09`
   - Runtime Health/System should show collector heartbeat, last success, last error, event count, and stale-source warnings before automated volume increases.

5. Add Reddit collector first.
   - Use `asyncpraw` or a narrow official Reddit API adapter.
   - Start with configured subreddits and keyword/mint/symbol watchlists.
   - Write normalized events into the existing social state without triggering trades.

6. Add X official API collector.
   - Use `tweepy` when credentials are available.
   - `twscrape` stays experimental and disabled by default unless explicitly enabled.

7. Add evidence snapshots.
   - Store source URL immediately.
   - Add ArchiveBox or lightweight snapshot support for high-value catalyst URLs.

8. Add social-to-price alignment.
   - Record event-time price/liquidity/market cap.
   - Follow up at 5m, 15m, 1h, and 4h.
   - Mark low-liquidity and sniper-candle outliers.

9. Add Telegram/Discord collectors.
   - Only for authorized public/owned channels.
   - Normalize to the same schema.

10. Add Solana launch-discovery enrichment.
   - Use `solana-streamer`, Chainstack, Shyft, and DexScreener references to improve discovery/event parsing after the decision ledger is stable.

## Next Implementation Step

The next build step is:

```txt
Reddit collector.
```

The backend and GUI now carry richer evidence fields and freshness/staleness indicators. Implement Reddit as the first automated social source because it is the lowest-friction, lowest-risk source and maps cleanly to the Meme Radar concepts.

## Acceptance Criteria

- Every automated social event has a source, timestamp, URL, collector name, and raw payload.
- Every matched catalyst can explain whether it matched by mint, symbol, token name, or keyword.
- Social-only events never create live actions or override hard risk gates.
- Decision records show social/catalyst evidence beside wallet, quote, holder, and risk evidence.
- Paper results feed back into social-event usefulness over time.
- The operator can see collector freshness and whether social data is stale.
