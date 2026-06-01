# Launch Lifecycle Data Quality Status

This status is research-only. It does not authorize backtests, walk-forward validation, thesis promotion, paper trading, live trading, auto-buy/sell logic, threshold optimization, grid search, or ML.

## Current External Artifacts

External data lake root:

```text
/Volumes/Polymarket Data/MemeTraderPro
```

Current classified lifecycle artifacts:

- All collected launches: `3,000`
- All collected snapshots: `36,000`
- All collected outcomes: `3,000`
- Strict launch-regime launches: `1,500`
- Strict launch-regime snapshots: `18,000`
- Strict launch-regime outcomes: `1,500`
- Normalized lifecycle events: `184,189`
- All collected liquidity-proxy snapshots: `36,000`
- All collected liquidity-proxy outcomes: `3,000`
- Strict launch-regime liquidity-proxy snapshots: `18,000`
- Strict launch-regime liquidity-proxy outcomes: `1,500`

## Event Classification Coverage

Current classified event counts:

- `pumpfun_buy`: `98,588`
- `pumpfun_sell`: `78,670`
- `pumpfun_create`: `6,545`
- `pumpfun_migrate`: `2`
- `pumpfun_swap`: `709`
- `unknown_token_swap_candidate`: `0`

The previous lifecycle event file classified all `184,189` events as `unknown_token_swap_candidate`. The classified replay reduced unknowns to `0` using deterministic Pump.fun program-id plus instruction-log evidence, with invalid account layouts failing closed. Pump.fun `SwapTob` and `SwapV2` logs are classified as `pumpfun_swap` without inventing buy/sell side from venue evidence alone.

## Survival Semantics

The old `survived_120m` field remains for compatibility, but it means observed activity at or after 120 minutes. That is intentionally stricter than liquidity survival.

New labels separate the concepts:

- `has_activity_at_or_after_120m`
- `has_price_at_120m`
- `has_liquidity_proxy_at_120m`
- `price_available_120m`
- `liquidity_survival_120m`
- `lifecycle_observed_to_120m`
- `survival_label_quality`

Current status: survival semantics are separated, but liquidity survival is still proxy-based. It is not confirmed pool liquidity survival.

The current classified lifecycle artifacts now populate a bonding-curve reserve proxy from the Pump.fun bonding-curve account post balance:

- Liquidity proxy source: `bonding_curve_post_balance`
- All collected liquidity-proxy source rows: `39,000`
- Strict launch-regime liquidity-proxy source rows: `19,500`

This improves lifecycle survival labeling, but it is still a SOL reserve proxy. It is not market cap, not confirmed DexScreener liquidity, and not a tradability claim.

## Market Cap Status

Market cap remains unavailable in the current lifecycle event set.

Market-cap fields are explicit:

- `market_cap_available`
- `market_cap_source`
- `market_cap_missing_reason`
- `threshold_outcomes_usable`

Threshold outcomes such as `ever_hit_15k`, `ever_hit_35k`, `ever_hit_50k`, and `ever_hit_100k` are unusable when `threshold_outcomes_usable=False`. They must not be treated as false outcomes.

## Research Readiness

The dataset is improved but not research-ready for conclusions.

Current blockers:

- Market cap enrichment is missing for threshold outcome work.
- Liquidity survival is now bonding-curve reserve proxy-based, not confirmed external pool liquidity.

Next recommended action:

```text
Add deterministic market-cap enrichment before running any thesis, validation, or strategy analysis.
```
