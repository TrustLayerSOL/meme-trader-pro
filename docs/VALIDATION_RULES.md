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

## Thesis decisions

- Thesis decisions are research workflow decisions, not trading instructions.
- No thesis can be promoted to `paper_candidate` without walk-forward evidence.
- Planned theses with missing data should remain `needs_more_data`.
- `paper_candidate` requires human review.
- Live trading remains disabled.
- Thesis status should be updated intentionally after reviewing reports, not automatically edited by the evaluator in v0.

## Evidence population

- First evidence runs should use tiny bounded samples.
- Early reports with sparse datasets should not promote theses.
- Thesis evaluation should remain `needs_more_data` until walk-forward folds have enough test rows/trades.
- Real evidence population must be reproducible from seed files, raw transaction stores, and derived local artifacts.
- Backfill and rebuild steps must be separated so derived artifacts can be regenerated without spending Helius credits.
- `nearest_research_fallback` is diagnostic only.
- Clean validation should prefer exact or prior entry prices.
- Any row with `entry_price_source="nearest_research_fallback"` must be separately filterable.
- `no_price` label counts must be monitored before scaling Helius backfills.
- Thesis promotion should not use fallback rows unless explicitly reviewed.
- Price inference from token balance deltas must carry `price_inference_method` metadata.

## Diagnostic validation

- Diagnostic fallback validation must be separate from canonical validation.
- Diagnostic validation may inform next research steps but cannot promote a thesis without human review.
- Nearest fallback rows must be counted in every diagnostic report.
- Canonical clean labels remain the source of truth for serious validation.
- Any diagnostic report using nearest-entry fallback must include the warning: `diagnostic fallback dataset; not valid for live trading or thesis promotion without human review.`

## Fold sufficiency diagnostics

- Fold sufficiency diagnostics are not strategy optimization.
- Fold window choice should initially be based on evidence sufficiency, not returns.
- Short diagnostic folds may be used while the dataset is small.
- Canonical validation should move toward longer, more stable folds as data grows.
- No thesis can be promoted based only on diagnostic fold settings.

## Backfill scaling

- Backfill scale decisions should be based on time-span and fold sufficiency, not just row count.
- Do not trust walk-forward results unless the dataset spans enough time for the chosen fold configuration.
- Bounded Helius scaling should proceed in small steps and be followed by offline rebuild and review.
- Any execution wrapper must default to dry-run and require `--execute` for real Helius calls.

## Offline rebuild freshness

- Outcome labels and research datasets must be refreshed after raw/events/features grow before interpreting fold sufficiency.
- Stale diagnostic datasets should be treated as a blocker, not evidence that more Helius data is needed.
- Do not run another bounded backfill when derived layers are stale; first run the fast offline rebuild and review path.
- Offline rebuild commands must report selected counts, progress, timings, and output paths so slow steps can be isolated.
- Diagnostic nearest-entry outputs remain separate from canonical clean outputs and remain invalid for live trading or thesis promotion without human review.

## Diagnostic walk-forward review

- Diagnostic walk-forward using nearest-entry fallback is not canonical validation.
- Diagnostic walk-forward can identify hypotheses worth inspecting, but cannot promote theses alone.
- Any rule with positive diagnostic evidence must be re-tested on clean labels and larger historical samples.
- Fallback dependency must be reported for every diagnostic walk-forward review.
- Diagnostic reports must keep outputs under `data/backtests/diagnostics/` and must not overwrite canonical clean walk-forward or thesis stores.

## Rule failure review

- Rule failure review is required before changing rule definitions.
- Do not optimize thresholds based on tiny diagnostic folds.
- Positive diagnostic folds are hypothesis clues only.
- Rule changes should be made only after the failure cause is understood.
- Inspect selected rows manually before changing thresholds or adding new rules.

## Sample adequacy gate

- No thesis can be rejected from tiny samples.
- Tiny diagnostic samples can only produce diagnostic notes.
- Rejection requires enough independent evidence across real tokens, time span, valid folds, and selected test rows.
- Promotion requires at least the same sample adequacy gate plus human review.
- If the sample adequacy gate fails, thesis recommendations must remain `needs_more_data`.
- Weak or negative diagnostic reads should be preserved in metadata as `diagnostic_raw_recommendation`, not converted into demotion.
- Current diagnostic fallback results are not reliable enough to demote anything until sample adequacy is met.

## Artifact span coverage

- Derived validation artifacts must cover a representative share of the raw evidence time span before fold sufficiency or thesis results are interpreted.
- Snapshot caps must not silently truncate validation to early-only slices after broad raw evidence expansion.
- Full-span or per-token snapshot selection is required after raw evidence covers multiple tokens or a wider time span.
- Artifact span reports should be reviewed before deciding whether the next bottleneck is more evidence, price inference, or fold-window configuration.
- Span checks are offline-only and do not justify live trading, thesis promotion, or rule optimization.

## Token-active feature windows

- Feature snapshots should not create validation rows for a token outside that token's observed local activity window unless an explicit global-grid diagnostic is being run.
- Global snapshot grids can be useful for debugging, but they can inflate `no_price` labels when applied to every token.
- Token-active feature rebuilds are preferred before clean-label price coverage review.
- Rebuilding features must remain offline-only and must not change strategy thresholds.

## Selected-row and price-outlier audit

- Before changing rule definitions, inspect the rows selected by each rule.
- Positive diagnostic averages can be invalid if a small number of outliers dominate returns.
- Median return and positive fold rate matter more than average return on small or diagnostic samples.
- Rows using `nearest_research_fallback` must be counted separately and treated as diagnostic-only.
- Stale entry prices must be audited before interpreting forward returns or max runup.
- Extreme max runup and forward-return rows require manual price-path inspection before bounded evidence scaling or rule review.
- Selected-row audits must remain offline-only and must not produce live signals, thesis promotion, or rule threshold optimization.
- Outlier-dominated averages must not be used for thesis decisions.
- Robust return metrics are required before interpreting rule averages.
- Isolated price prints should be excluded or separately labeled from serious validation.
- Price-path reviews must classify extreme rows as plausible, suspicious, fallback-dependent, isolated, or unusable before the next evidence-scaling decision.
