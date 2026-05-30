# Social Tracker Adaptation Plan

Last updated: 2026-04-29

This breaks down the GitHub/Rohun-inspired social tracker ideas into a MemeTraderPro build plan.

## Bottom Line

The other agent's take is correct: social media hype is central to meme coin movement, but it should become an evidence layer, not an auto-buy trigger.

MemeTraderPro should adapt the strongest ideas into a local, auditable catalyst system:

- source/social signal,
- thesis/catalyst card,
- token candidate,
- risk checks,
- wallet/on-chain confirmation,
- signal-time price,
- action-time price,
- paper/live-gated outcome,
- postmortem.

## Source Ideas To Adapt

### `paste-trade`

Use as the strongest product pattern.

Adapt:

- signal -> thesis -> candidate route -> locked price -> P&L lifecycle,
- source timestamp vs action timestamp,
- routed/dropped candidate state,
- thesis/outcome audit trail.

MemeTraderPro version:

- `detected -> enriched -> scored -> paper_entered | skipped -> monitored -> closed/postmortem`
- compare signal-time price to operator/action-time price,
- store why the system cared about the token before it traded or skipped.

### `walletdoctor`

Use as the wallet analytics/backfill reference.

Adapt:

- batch wallet backfills,
- parse metrics,
- error counts,
- wallet P&L/behavior evidence,
- progress reporting.

MemeTraderPro version:

- promote wallets only after enough evidence,
- show parse confidence and sample size,
- track rapid-dump exposure and copy-bait risk.

### `tweet-price-charts`

Use as the social-signal-to-price-impact reference.

Adapt:

- tweet/post timestamp alignment,
- price at post,
- follow-up windows,
- baseline/no-post comparison,
- outlier warnings.

MemeTraderPro version:

- measure 5m, 15m, 1h, 4h movement after a post,
- include liquidity/volume change, not just price,
- mark sniper candles and low-liquidity distortions,
- treat social as evidence, not proof.

### `x-research-skill`

Use as the watchlist/cached X research pattern.

Adapt:

- account watchlists,
- cached searches,
- quick pulse checks,
- no-reply/no-retweet filters,
- cost-aware queries,
- JSON/Markdown outputs.

MemeTraderPro version:

- local X watchlist config,
- recent-post cache,
- narrative keyword extraction,
- audit-friendly social signal records.

### `why-pump`

Use as the catalyst-card concept.

Adapt:

- explainable catalyst cards,
- strict evidence links,
- confidence/severity/horizon,
- invalidation criteria.

MemeTraderPro version:

- every social/on-chain/wallet catalyst must separate observed facts from inferred narrative,
- no AI-only claims without evidence,
- catalyst cards become the bridge between social signals, wallet signals, risk checks, and paper outcomes.

## Proposed Data Objects

### Social Event

Fields:

- `event_id`
- `source_platform`
- `account`
- `account_category`
- `post_id`
- `post_url`
- `text`
- `timestamp`
- `discovered_at`
- `keywords`
- `tickers`
- `mints`
- `engagement`
- `raw`

### Catalyst Card

Fields:

- `card_id`
- `source_event_ids`
- `candidate_mints`
- `narrative`
- `catalyst_type`
- `direction`
- `confidence`
- `severity`
- `time_horizon`
- `evidence`
- `invalidation`
- `status`
- `created_at`
- `updated_at`

### Social Price Alignment

Fields:

- `event_id`
- `mint`
- `price_at_event`
- `liquidity_at_event`
- `volume_at_event`
- `price_5m`
- `price_15m`
- `price_1h`
- `price_4h`
- `return_5m_pct`
- `return_15m_pct`
- `return_1h_pct`
- `return_4h_pct`
- `liquidity_change_pct`
- `volume_change_pct`
- `outlier_flags`

## Build Order

1. Add local catalyst/social schemas.
2. Add manual/import social event ingestion.
3. Convert current `SocialSignalEngine` outputs into catalyst cards.
4. Show catalyst cards in dashboard.
5. Add price alignment snapshots for social events.
6. Add cached X watchlist pulse checks.
7. Add wallet + social + risk combined candidate view.
8. Backtest whether social signals improved paper outcomes.

## Safety Rules

- Social signals cannot bypass token mechanics checks.
- Social signals cannot bypass liquidity/quote checks.
- Social signals cannot trigger live buys by themselves.
- Social signals should affect confidence and review priority, not override hard risk gates.
- All inferred narratives must be labeled as inference.

## First Implementation Ticket

Add a local `core/catalyst_cards.py` module and `data/catalyst_cards.json` schema.

Goal:

- Turn existing manual social signals into auditable catalyst cards.
- Link catalyst cards to candidate tokens when token name/symbol/mint matches.
- Surface active catalyst cards in the dashboard.

This gives the social tracker a durable product shape before adding live X/API ingestion.
