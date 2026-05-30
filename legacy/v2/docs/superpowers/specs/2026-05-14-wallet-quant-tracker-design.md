# Quant Wallet Tracker Refocus Design

## Decision

MemeTraderPro is now refocused around a Quant Wallet Tracker.

The core product is no longer a broad meme trading cockpit. The core product is a private wallet intelligence system that discovers wallets, tracks repeat behavior, builds paper evidence, promotes useful wallets, demotes bad wallets, and gives the operator a clean way to evaluate the data.

## Problem

The project accumulated too many product lanes:

- Axiom-style chart polish.
- General GUI expansion.
- Social and catalyst cards.
- Manual protected-token workflows.
- Market Radar as a separate strategy.
- AI decision explanations.
- Marketing assets.
- Future live execution planning.

Those pieces created noise before the main edge was proven. The strongest measurable loop is wallet behavior because wallets are repeat actors. Tokens are one-off, narratives are noisy, and PnL is premature until the data loop is clean.

## New Product Goal

Build the best possible quant wallet tracking system for Solana meme markets.

The system should answer:

- Which wallets buy early before meaningful market-cap expansion?
- Which wallets repeatedly find runners?
- Which wallets sell well instead of round-tripping gains?
- Which wallets avoid obvious rugs and low-quality launches?
- Which wallets are copy-bait or late/noisy participants?
- Which wallets deserve higher signal weight?
- Which wallets should be demoted, blocked, or ignored?

## Active Scope

The active system is:

1. Wallet discovery from runners.
2. Wallet observation at scale.
3. Wallet behavior metrics.
4. Wallet outcome ledger.
5. Paper-watch evidence.
6. Promotion and demotion review.
7. Clean wallet evaluation UI/reporting.

## Supporting Scope

These stay only because they support wallet evaluation:

- Token market-cap, liquidity, holder, and route/sell feasibility fields.
- Token risk and mechanics as filters on wallet-trade quality.
- Decision ledger where it links wallet signals to outcomes.
- Runtime health so the data stream can be trusted.
- Paper trade simulation only as evidence generation, not as a profitability claim.

## Frozen Scope

These are frozen for the next iteration unless directly needed by wallet evaluation:

- Chart polish and Axiom-style visual work.
- Manual protected-token UX.
- Social/catalyst automation.
- AI explanations.
- Market Radar as a separate co-main strategy.
- Marketing assets.
- Live execution wiring.
- Broad GUI expansion.

Frozen does not mean deleted immediately. It means no new work, no new features, and no roadmap priority. Physical deletion should happen only after the wallet system has canonical replacements for any useful data paths.

## Wallet Data Points

Each wallet should eventually have these fields.

Identity:

- `wallet`
- `first_seen_at`
- `last_seen_at`
- `source_count`
- `discovery_sources`
- `tier`
- `labels`

Activity:

- `observed_buys`
- `observed_sells`
- `unique_mints`
- `early_buys`
- `repeat_mint_buys`
- `avg_buy_market_cap`
- `median_buy_market_cap`
- `avg_buy_liquidity`
- `median_buy_liquidity`

Outcome quality:

- `runner_entries`
- `runner_capture_rate`
- `max_favorable_excursion_median_pct`
- `max_drawdown_after_entry_median_pct`
- `average_hold_seconds`
- `median_hold_seconds`
- `sold_before_peak_rate`
- `round_trip_rate`
- `rug_exposure_rate`
- `dead_token_rate`

Paper-watch evidence:

- `paper_watch_entries`
- `paper_watch_closed`
- `paper_watch_win_rate`
- `paper_watch_total_pnl`
- `paper_watch_median_pnl`
- `paper_watch_expectancy`
- `paper_watch_best_trade`
- `paper_watch_worst_trade`
- `paper_watch_last_7d_expectancy`
- `paper_watch_last_30d_expectancy`

Scoring:

- `raw_behavior_score`
- `paper_evidence_score`
- `risk_penalty_score`
- `recency_score`
- `confidence_score`
- `promotion_score`
- `demotion_score`
- `sample_quality`

Review:

- `recommended_action`
- `recommendation_reasons`
- `promotion_eligible`
- `demotion_eligible`
- `blocked_reason`
- `last_reviewed_at`
- `review_decision`

## Wallet Tiers

Use a clear tier model:

- `candidate`: discovered from runner/history but not yet observed enough.
- `paper_watch`: observed live for paper evidence.
- `promotion_review`: enough positive evidence to consider trusted tracking.
- `trusted`: allowed to contribute meaningful signal weight.
- `demotion_review`: tracked but underperforming or noisy.
- `blocked`: known poor, manipulative, copy-bait, or spam wallet.

## Feedback Loop

The loop is:

1. Find runner tokens.
2. Extract early buyers and profitable/competent sellers.
3. Add wallets to candidate/paper-watch.
4. Observe future wallet behavior.
5. Record wallet-level events and token outcomes.
6. Simulate paper-copy outcomes.
7. Score wallets from behavior and paper evidence.
8. Promote repeat winners.
9. Demote decayed or bad wallets.
10. Report clean wallet metrics.

## Data Architecture

Keep JSON runtime files for now, but move wallet evaluation toward canonical SQLite-backed analytics.

Near-term sources:

- `data/tracked_wallets.json`
- `data/paper_watch_wallets.json`
- `data/candidate_wallets.json`
- `data/wallet_performance.json`
- `data/wallet_behavior.json`
- SQLite `events`
- SQLite `trades`
- SQLite `token_snapshots`
- SQLite `decision_records`

New target artifact:

- `data/wallet_quant_report.json`
- `data/signal_contexts/contexts.jsonl`
- `data/rejected_signals/rejections.jsonl`
- `data/replay_visibility_report.json`

Later canonical tables:

- `wallet_observations`
- `wallet_token_outcomes`
- `wallet_quant_scores`
- `wallet_tier_history`
- `signal_contexts`
- `signal_outcomes`

## V2 Observability Direction

Quant Wallet Tracker V2 should maximize information captured from every signal before it tries to optimize thresholds.

Every signal context should include:

- triggering wallets
- wallet scores/labels when known
- cluster timing
- token age
- liquidity, market cap, price, and volume
- holder concentration and hard-risk flags
- estimated slippage and execution delay assumptions
- score reasons
- market-regime tags

Every no-trade row should preserve:

- rejection reason
- full signal context
- wallet context
- liquidity state
- current placeholder for later counterfactual outcome

Replay is review-only until it can prove it uses only pre-signal information for the simulated decision. Future outcome labels can be attached later, but they must not influence the reconstructed entry decision.

## UI Direction

The UI should become data-evaluation first, not trading-cockpit first.

Required views:

- Wallet Funnel: counts by tier and source.
- Wallet Rankings: best candidates by evidence quality.
- Promotion Queue: wallets close to trusted status.
- Demotion Queue: wallets dragging signal quality down.
- Wallet Detail: observed mints, entries, exits, outcomes, labels, score history.
- Data Health: whether wallet data is fresh enough to trust.

Charts are optional and only useful if they explain wallet behavior. No more chart polish unless it directly improves wallet evaluation.

## Non-Goals

This iteration will not:

- Enable live trading.
- Optimize for PnL claims.
- Expand social automation.
- Improve Axiom-style charting.
- Add more manual protection features.
- Build marketing assets.
- Add AI-generated explanations as product logic.

## Success Criteria

The next iteration is successful when:

- The active roadmap clearly centers wallet quant tracking.
- Irrelevant lanes are frozen in docs and UI navigation.
- Wallet metrics are defined in one place.
- A wallet quant report exists and can be regenerated.
- No-trade/rejected signals carry structured signal context.
- A replay visibility report exists for rejected signals.
- The system can show how many wallets are in each tier.
- The system can explain why a wallet is promoted, held, demoted, or blocked.
- PnL is treated as one metric, not the primary product proof.
