# Validation Rules

- Event-driven backtesting, not candle-only backtesting.
- Include venue fees, slippage, latency, stale quotes, priority fees, failed fills, and partial fills.
- Use rolling time-based walk-forward validation.
- Do not use random train/test splits for launch strategies.

## Required reporting metrics

- net expectancy
- hit rate
- payoff ratio
- profit factor
- max drawdown
- slippage
- fill rate
- venue attribution
- performance by lifecycle stage

## Trade event inference

- Trade event inference is heuristic in v0.
- Every inferred trade event must carry confidence and reasons.
- Backtests must be able to filter by minimum confidence.
- Low-confidence events should be used for exploratory analysis, not live execution.
- Later DEX-specific decoders may replace or upgrade these heuristic events.
