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

## Feature snapshots

- Feature snapshots are generated only from normalized local events.
- Backtests must consume FeatureSnapshotStore data, not direct RPC calls.
- Features must not include future events beyond `snapshot_ts`.
- Rolling windows must use strict time filtering to avoid leakage.
- Confidence-weighted features should separate high-confidence inferred trades from exploratory low-confidence events.
- Strategy labels/outcomes are not part of Milestone 7.

## Outcome labels

- Outcome labels may look forward in time; features may not.
- Outcome labeling must be separate from feature generation to avoid leakage.
- Backtests should join FeatureSnapshot rows with OutcomeLabel rows by `snapshot_id` and horizon.
- Entry price source must be tracked.
- Labels with `entry_price_source="first_after_snapshot"` should be treated carefully because they use future information for entry approximation.
- `label_quality` must be used to filter sparse/no-price rows.
- Rug-like labels are heuristic and threshold-based in v0.

## Research datasets

- Research datasets are the first place features and future outcomes are joined.
- Feature columns must come only from FeatureSnapshot.
- Outcome columns must come only from OutcomeLabel.
- Strategy/backtest code should consume ResearchDatasetRow, not raw transaction data.
- Rows with low `label_quality` should be excluded from serious validation unless explicitly being investigated.
- Dataset filters must be recorded in reports when used.
