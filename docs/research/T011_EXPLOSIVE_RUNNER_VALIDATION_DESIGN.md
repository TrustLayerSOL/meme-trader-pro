# T011 Explosive Runner Validation Design

## 1. Thesis Statement

T011 asks whether a launch that reaches an observable FDV-proxy trigger can be distinguished by its raw-flow structure before it continues into higher explosive-runner tiers.

The pre-registered validation question is:

> Among launches that cross a fixed FDV-proxy trigger, does low total flow with high FDV efficiency at the trigger predict continuation into higher FDV-proxy tiers on a chronological holdout?

This is a validation design only. No validation, walk-forward test, backtest, trading simulation, paper trading, live trading, or thesis promotion was run.

## 2. Why This Is The First Validation Candidate

T011 is the first MemeTraderPro descriptive thesis to reach a robustness classification of `robust_descriptive_signal`.

Observed state:

- Original T011 classification: `descriptive_signal_present`
- Robustness classification: `robust_descriptive_signal`
- All-collected launches analyzed: `3,000`
- Primary `$20k` trigger rows: `422`
- Fixed-trigger robustness:
  - `$15k`: `448` rows, stable
  - `$20k`: `422` rows, stable
  - `$30k`: `395` rows, stable
- Outlier checks: stable after top 1%, top 5%, `$1M+`, and extreme-drawdown exclusions
- Dominance checks: stable after dominant creator, top 3 `$1M+` creators, and top date exclusions
- Remaining caveat: chronological thirds and top 3 date exclusions were not fully stable

The refined descriptive read is `low_total_flow_with_high_fdv_efficiency`, with active-wallet reconciliation suggesting `low_total_flow_and_lower_event_density_per_wallet`.

## 3. Data Used

Primary design input:

- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T011_explosive_runner_raw_flow/trigger_20k_feature_rows.csv`

Supporting inputs:

- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T011_explosive_runner_raw_flow/T011_explosive_runner_raw_flow_summary.json`
- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T011_explosive_runner_raw_flow_robustness/T011_explosive_runner_raw_flow_robustness_summary.json`
- `/Volumes/ORICO/MemeTraderPro/data/normalized/launch_lifecycle_collected_valuation_enriched/launch_lifecycle_snapshots_valuation_enriched.jsonl`

Data semantics:

- FDV/valuation proxy only
- True market-cap claims remain blocked
- Holder/entity/funding overlays remain partial context only
- No PnL, trade execution, or entry/exit claims

## 4. Trigger Definition

Primary trigger:

- First launch-relative snapshot where `valuation_proxy_usd >= 20,000`

Secondary fixed-trigger sensitivity:

- First snapshot where `valuation_proxy_usd >= 15,000`
- First snapshot where `valuation_proxy_usd >= 30,000`

The trigger thresholds are fixed by prior descriptive work. They must not be optimized during validation.

## 5. Feature Definitions

Primary feature family:

- `event_count_at_trigger`
- `buy_count_at_trigger`
- `fdv_per_event_at_trigger = trigger_fdv_proxy / event_count_at_trigger`
- `fdv_per_buy_at_trigger = trigger_fdv_proxy / buy_count_at_trigger`
- `events_per_active_wallet_at_trigger = event_count_at_trigger / active_wallets_at_trigger`
- `active_wallets_at_trigger`

Neutral signal labels:

- `low_total_flow`
- `high_fdv_efficiency`
- `low_event_density_per_wallet`

Context-only overlays:

- `holder_count_at_trigger`
- `fdv_per_holder_at_trigger`
- `repeated_actor_overlap_proxy`
- `funding_source_available`

Overlay fields must not drive primary validation because their current all-collected coverage is partial.

## 6. Outcome Definitions

Primary validation outcome:

- `crossed_100k_after_20k`

Justification:

- `$100k` is far enough above the `$20k` trigger to measure meaningful continuation.
- It has more support than `$500k` or `$1M`, reducing the risk that validation is dominated by a few extreme runners.
- It remains aligned with the robustness finding that compared `$100k+` against sub-`$100k`.

Secondary outcomes:

- `crossed_50k_after_20k`
- `crossed_200k_after_20k`
- `crossed_500k_after_20k`
- `crossed_1m_after_20k`
- `crossed_100k_within_10m_from_20k`
- `crossed_500k_within_60m_from_20k` if forward-path support is available

## 7. Leakage Controls

Validation must enforce these controls:

- Features are computed only from the trigger snapshot or prior launch-relative snapshots.
- No future snapshots may be used for feature construction.
- Outcome labels may use future path after the trigger, but never feed back into feature buckets.
- Bucket boundaries are learned only from the design/train partition.
- Holdout launch rows are assigned to pre-registered train-derived buckets.
- Creator/date dominance checks are evaluated after holdout scoring, not used to tune buckets.
- No threshold optimization, grid search, model fitting, or ML feature selection.
- FDV-proxy semantics must remain explicit; do not call results true market cap.

## 8. Chronological Split Design

Primary split:

- Earliest 60% of `$20k` trigger launches: design/train partition
- Latest 40% of `$20k` trigger launches: holdout partition

Recommendation:

- Use 60/40 as the primary split.

Reason:

- There are only `422` `$20k` trigger rows. A 70/30 split would leave a smaller holdout and increase uncertainty in higher-tier outcomes.
- The 60/40 split still preserves chronological separation while keeping enough holdout support to evaluate lift, precision, recall, and concentration.

Secondary split:

- 70/30 chronological split as a sensitivity report only

No random split should be primary.

## 9. Pre-Registered Buckets

Use train-partition quintiles only:

- `event_count_at_trigger` quintiles
- `buy_count_at_trigger` quintiles
- `fdv_per_event_at_trigger` quintiles
- `fdv_per_buy_at_trigger` quintiles
- `events_per_active_wallet_at_trigger` quintiles

Primary contrast:

- Highest `fdv_per_event_at_trigger` quintile AND lowest `event_count_at_trigger` quintile
- Compared against all other trigger launches in the holdout

Secondary contrasts:

- Highest `fdv_per_buy_at_trigger` quintile AND lowest `buy_count_at_trigger` quintile
- Lowest `events_per_active_wallet_at_trigger` quintile
- Low-flow bucket with at least median active-wallet breadth

Important:

- Bucket boundaries are descriptive pre-registration tools, not optimized thresholds.
- If primary contrast support is too small in the train partition or holdout partition, validation must fail support criteria rather than relaxing the definition.

## 10. Primary Validation Metric

Primary metric:

- Holdout hit-rate lift for `crossed_100k_after_20k`

Definition:

- `primary_bucket_hit_rate / holdout_baseline_hit_rate`

The primary result must report:

- holdout baseline hit rate
- primary bucket hit rate
- absolute lift
- relative lift
- bucket support
- precision
- recall
- false-positive rate
- creator/date concentration inside the primary bucket

No PnL metric is allowed in this validation.

## 11. Secondary Metrics

Secondary metrics:

- Hit rate by pre-registered quintile bucket
- Lift vs the full `$20k` trigger holdout universe
- Precision
- Recall
- Median max favorable FDV-proxy excursion
- Median max adverse FDV-proxy excursion
- False-positive rate
- Bucket support
- Creator concentration
- Date concentration
- Bucket monotonicity for FDV-efficiency features, if applicable
- Trigger sensitivity at `$15k` and `$30k`

Secondary metrics are explanatory only. They must not be used to redefine the primary bucket.

## 12. Failure Conditions

Validation fails if any of the following occur:

- The primary bucket does not produce meaningful holdout lift above the holdout baseline.
- The primary bucket has too little support to interpret.
- Direction reverses on the holdout.
- The signal is dominated by one creator.
- The signal is dominated by one date or a very small date cluster.
- The signal is unstable across `$15k`, `$20k`, and `$30k` triggers.
- The signal depends on excluding inconvenient outliers.
- The signal only works through an FDV-proxy artifact or compressed snapshot timing.
- Forward path is unavailable for the target outcome.
- Feature rows use any post-trigger information.

## 13. Promotion / Progression Criteria

Progression to a step-forward observation design requires all of the following:

- Stable lift on the chronological holdout for the primary outcome.
- Primary bucket support is moderate enough to interpret.
- Primary bucket is not dominated by one creator.
- Primary bucket is not dominated by one date.
- Feature direction remains interpretable as low total flow plus high FDV efficiency.
- Outlier removal does not reverse the result.
- Trigger sensitivity at `$15k` and `$30k` is directionally consistent.
- Target-event count is sufficient for a practical observation plan.

This would justify designing a step-forward observation system, not live trading, paper trading, or thesis promotion.

## 14. Reasons Not To Validate Yet

Validation is recommended next, but with these constraints:

- Current evidence is FDV-proxy only.
- Chronological thirds were not fully stable in robustness review.
- Top 3 date exclusion was not stable.
- Holder and funding overlays are partial and should remain context-only.
- Snapshot timing around fast crossings may compress the observable trigger path.

These caveats do not block validation design, but they must be explicitly carried into validation.

## 15. Future Validation Command Shape

The future validation command should look like this, but it must not be run in this sprint:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_t011_explosive_runner_raw_flow_validation \
  --trigger-20k-rows-path /Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/T011_explosive_runner_raw_flow/trigger_20k_feature_rows.csv \
  --snapshots-path /Volumes/ORICO/MemeTraderPro/data/normalized/launch_lifecycle_collected_valuation_enriched/launch_lifecycle_snapshots_valuation_enriched.jsonl \
  --primary-trigger 20000 \
  --secondary-triggers 15000,30000 \
  --primary-outcome crossed_100k_after_20k \
  --primary-split chronological_60_40 \
  --bucket-method train_quintiles \
  --primary-contrast high_fdv_per_event_q5_and_low_event_count_q1 \
  --execute
```

The command is a design target only. The validation runner does not need to exist yet, and validation must not be executed until explicitly requested.

## Final Recommendation

Proceed next to implementation of a validation runner that follows this design exactly. Do not run validation until the runner has guardrail tests proving:

- train-derived bucket boundaries only
- no future leakage
- no threshold optimization
- no PnL or trading claims
- deterministic chronological split behavior
- explicit failure handling for small bucket support and creator/date dominance
