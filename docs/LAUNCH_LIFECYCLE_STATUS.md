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
- All collected valuation-enriched rows: `39,000`
- Strict launch-regime valuation-enriched rows: `19,500`
- Token supply rows: `3,000`
- SOL/USD reference rows: `164`

## Event Classification Coverage

Current classified event counts:

- `pumpfun_buy`: `98,263`
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

## Valuation Input Audit

Current availability from local lifecycle artifacts plus bounded provenance-safe valuation inputs:

- Token mint: available.
- Token decimals: available from `getTokenSupply` supply rows.
- Total supply: available from current SPL mint supply via Helius `getTokenSupply`.
- Circulating supply: not available.
- Pump.fun fixed supply assumption: not encoded as a trusted repo assumption.
- Bonding-curve virtual reserves: not available as verified virtual reserve fields.
- Real token reserves: available in normalized event metadata, not promoted into snapshot/outcome valuation semantics.
- Real SOL reserves: available as bonding-curve post-balance proxy.
- Token price in SOL: available in enriched snapshot/outcome rows from the latest local priced event at each snapshot and 120-minute outcome horizon.
- Token price in USD: available through timestamp-compatible SOL/USD join.
- SOL/USD source: available from CoinGecko Solana range prices.
- Bonding-curve post balance: available.
- Liquidity proxy fields: available.
- Snapshot timestamp and launch age: available.
- Price source/provenance: available for SOL price via `price_source`, `price_event_signature`, `price_event_block_time`, and `price_staleness_seconds`.
- Supply source/provenance: available as `helius_getTokenSupply` with `current_spl_mint_supply`.

## Valuation Layer Status

Valuation enrichment outputs now exist for both lifecycle cohorts. The layer is conservative:

- `true_market_cap_usd`: unavailable.
- `fdv_usd`: available.
- `valuation_proxy_usd`: available and currently equals FDV.
- `bonding_curve_liquidity_proxy_sol`: available.
- `threshold_outcomes_usable`: `false`.
- `threshold_outcomes_source`: `null`.
- `threshold_outcomes_missing_reason`: `usd_valuation_unavailable`.
- `proxy_threshold_outcomes_usable`: `true`.
- `proxy_threshold_outcomes_source`: `fdv_usd_current_supply_proxy`.

Current enriched coverage:

- All collected bonding-curve liquidity proxy rows: `39,000`
- Strict launch-regime bonding-curve liquidity proxy rows: `19,500`
- True market cap available rows: `0`
- FDV available rows: `39,000` all collected, `19,500` strict launch-regime
- USD valuation proxy available rows: `39,000` all collected, `19,500` strict launch-regime
- Threshold-outcome usable rows: `0`
- Proxy-threshold usable rows: `39,000` all collected, `19,500` strict launch-regime
- Supply available rows: `39,000` all collected, `19,500` strict launch-regime
- SOL/USD available rows: `39,000` all collected, `19,500` strict launch-regime
- USD price available rows: `39,000` all collected, `19,500` strict launch-regime
- SOL price available rows: `39,000` all collected, `19,500` strict launch-regime

## Market Cap Status

Market cap remains unavailable in the current lifecycle event set.

Market-cap fields are explicit:

- `market_cap_available`
- `market_cap_source`
- `market_cap_missing_reason`
- `threshold_outcomes_usable`

Threshold outcomes such as `ever_hit_15k`, `ever_hit_35k`, `ever_hit_50k`, and `ever_hit_100k` are unusable when `threshold_outcomes_usable=False`. They must not be treated as false outcomes.

Proxy threshold fields such as `ever_hit_valuation_proxy_15k`, `ever_hit_valuation_proxy_35k`, `ever_hit_valuation_proxy_50k`, and `ever_hit_valuation_proxy_100k` are usable in enriched outputs under explicit FDV-proxy semantics. They are not true market-cap labels.

## Research Readiness

The dataset is ready for thesis-testing preparation under FDV-proxy valuation semantics. It is not ready for true-market-cap thesis tests or tradability claims.

Current blockers:

- True circulating supply is unavailable.
- True market cap remains unavailable.
- Original market-cap threshold outcomes remain unusable and must not be treated as false.
- Liquidity survival is bonding-curve reserve proxy-based, not confirmed external pool liquidity.

Next recommended action:

```text
Begin thesis-test design against the strict launch-regime FDV-proxy dataset, keeping true market-cap claims blocked.
```
