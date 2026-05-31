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

## Baseline edge reports

- Baseline edge reports are exploratory descriptive reports, not strategy validation.
- They must not produce trading signals, live recommendations, or wallet/token trust claims.
- Apparent edge must survive event-driven backtesting and walk-forward validation before it can be used as a candidate rule.
- Feature analysis must not use future/outcome fields as predictors.
- Reports must show sample sizes and warning flags.
- Small-bucket findings are not trusted.
- Top findings are hypothesis generators, not recommendations.

## Rule-based backtests

- Rule-based backtests are exploratory until walk-forward validation exists.
- Backtests must show gross and net returns separately.
- Cost assumptions must be visible in every report.
- Rules must not use future/outcome fields as conditions.
- Rule definitions must be simple and auditable.
- Small sample warnings must be shown.
- A profitable in-sample rule is not a trading strategy.
- Live trading remains disabled.

## Walk-forward validation

- Walk-forward validation is required before any rule can be considered for paper trading.
- Rows must be split chronologically by `snapshot_ts`.
- Random train/test splits are not allowed.
- Train results must not be used to alter rules in v0.
- Test fold results must be reported separately from train fold results.
- A rule needs consistency across folds, not just one strong fold.
- Walk-forward reports remain exploratory until tested on larger historical samples and then paper traded.
- Live trading remains disabled.
