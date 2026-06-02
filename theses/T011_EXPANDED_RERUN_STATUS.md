# T011 Expanded Rerun Status

## Why This Rerun Was Needed

The prior T011 validation failed because the holdout collapsed to one date. The expanded sample fixes the date-clustering blocker before any validation rerun is attempted.

## Expanded Dataset Coverage

- Launches: `12`
- $20k trigger rows: `12`
- Unique $20k trigger dates: `12`
- Median rows per active $20k date: `1.0`
- Top date share: `0.08333333333333333`
- Top 3 date share: `0.25`
- Forward path coverage: `1.0`

## Winner Anatomy Result

- Readiness: `winner_anatomy_blocked`
- Milestone tier counts: `{'reached_1m_plus': 6, 'reached_20k_but_never_50k': 6}`

## Expanded T011 Result

- Classification: `data_limited`
- Robustness classification: `not_run_no_descriptive_signal`
- Low-flow/high-FDV-efficiency survived: `True`

## Old vs Expanded

- Old $20k trigger rows: `422`
- Old unique trigger dates: `3`
- Expanded $20k trigger rows: `12`
- Expanded unique trigger dates: `12`
- Validation recommended: `False`

## Limitations

- Entity, migration, and funding overlays may have sidecar-limited coverage.
- FDV/valuation proxy is used; true market-cap claims remain blocked.
- Features are descriptive at the first $20k FDV-proxy crossing and are not entry/exit rules.
- Holder coverage at trigger: 0.0%.
- Holder state is observed-delta replay, not confirmed full-chain account state.
- No entry, exit, profitability, or execution claims are made.
- This rerun is descriptive only and does not validate a strategy.
- True market-cap labels remain blocked; this uses FDV/valuation proxy only.

## Next Recommendation

Refine robustness design before validation; the descriptive pattern survived but robustness did not fully justify validation.

## Report Paths

- JSON: `/private/var/folders/x9/dq8sv7hj50j3j38_n6tmdv180000gn/T/pytest-of-dianeposs/pytest-272/test_expanded_rerun_writes_rep0/reports/T011_expanded_rerun_summary.json`
- Markdown: `/private/var/folders/x9/dq8sv7hj50j3j38_n6tmdv180000gn/T/pytest-of-dianeposs/pytest-272/test_expanded_rerun_writes_rep0/reports/T011_expanded_rerun_summary.md`