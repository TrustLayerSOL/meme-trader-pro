# Candidate Walk-Forward Survivor Review

## What Changed

Added a candidate-only survivor review layer for walk-forward validation. This report explains the row-level train/validation evidence behind wallets that currently have the `continued_validation` walk-forward conclusion.

This layer is review-only. It does not enable paper trading, live trading, execution, wallet promotion, wallet trust mutation, or wallet-list mutation.

## Command

```bash
python3 -m utils.build_candidate_walk_forward_survivor_review --run-id 20260525-candidate-walk-forward-survivor-review
```

## Outputs

- `data/reports/forward_testing/candidate_walk_forward/candidate_walk_forward_survivor_review_20260525-candidate-walk-forward-survivor-review.json`
- `data/reports/forward_testing/candidate_walk_forward/candidate_walk_forward_survivor_review_20260525-candidate-walk-forward-survivor-review.csv`
- `data/reports/forward_testing/candidate_walk_forward/candidate_walk_forward_survivor_events_20260525-candidate-walk-forward-survivor-review.csv`
- `data/reports/forward_testing/candidate_walk_forward/candidate_walk_forward_survivor_review_20260525-candidate-walk-forward-survivor-review.md`

## Current Result

- Survivor wallets reviewed: `2`
- Proof metric rows: `35`
- Excluded rows: `138`
- Train event rows: `24`
- Validation event rows: `11`
- Promotions allowed: `0`
- Wallet-list mutations: `0`
- Wallet-trust mutations: `0`

## Wallet Summaries

### `2K5DekX2pitRReFBC4byUCv2Ci3o89StnBQnBbkA9BdN`

- Walk-forward conclusion: `continued_validation`
- Paper simulation readiness: `not_ready`
- Proof metric rows: `19`
- Excluded rows: `36`
- Train clean rows: `13`
- Train runners: `8`
- Train runner rate: `0.6154`
- Validation clean rows: `6`
- Validation runners: `5`
- Validation runner rate: `0.8333`
- Blocked excluded rows: `31`

### `D11LfGmruiKraNB9BtPqb1ELEYnNtpsNDuft32wArYV3`

- Walk-forward conclusion: `continued_validation`
- Paper simulation readiness: `not_ready`
- Proof metric rows: `16`
- Excluded rows: `102`
- Train clean rows: `11`
- Train runners: `5`
- Train runner rate: `0.4545`
- Validation clean rows: `5`
- Validation runners: `3`
- Validation runner rate: `0.6`
- Blocked excluded rows: `98`

## Interpretation

Both survivor wallets are still candidates only. The row-level report gives reasons to continue validation, but the clean sample sizes are too small and the excluded context-blocked rows are too large to justify paper simulation.

The correct next step is to keep collecting clean forward rows and reduce context blockers for these two wallets before considering any paper-trading gate.

## Paper Readiness Gate

Added a separate advisory gate:

```bash
python3 -m utils.build_candidate_walk_forward_paper_readiness_gate --run-id 20260525-candidate-walk-forward-paper-readiness-gate
```

Outputs:

- `data/reports/forward_testing/candidate_walk_forward/candidate_walk_forward_paper_readiness_gate_20260525-candidate-walk-forward-paper-readiness-gate.json`
- `data/reports/forward_testing/candidate_walk_forward/candidate_walk_forward_paper_readiness_gate_20260525-candidate-walk-forward-paper-readiness-gate.csv`
- `data/reports/forward_testing/candidate_walk_forward/candidate_walk_forward_paper_readiness_gate_20260525-candidate-walk-forward-paper-readiness-gate.md`

Gate requirements:

- Required walk-forward conclusion: `continued_validation`
- Minimum total clean rows: `100`
- Minimum validation clean rows: `25`
- Minimum validation runners: `5`
- Minimum validation token count: `15`
- Minimum context completion rate: `0.8`
- Maximum excluded rate: `0.2`

Current gate result:

- Wallets evaluated: `2`
- Eligible for manual paper-simulation review: `0`
- Not ready wallets: `2`
- Paper simulation enabled: `false`
- Promotions allowed: `0`
- Wallet-list mutations: `0`
- Wallet-trust mutations: `0`

## Candidate Context Quality Lift

Added a targeted blocker-reduction queue for survivor wallets that failed the paper-readiness gate because of context completion or excluded-row rate.

```bash
python3 -m utils.build_candidate_context_quality_lift --run-id 20260525-candidate-context-quality-lift
```

Outputs:

- `data/reports/forward_testing/candidate_walk_forward/candidate_context_quality_lift_20260525-candidate-context-quality-lift.json`
- `data/reports/forward_testing/candidate_walk_forward/candidate_context_quality_lift_20260525-candidate-context-quality-lift.csv`
- `data/reports/forward_testing/candidate_walk_forward/candidate_context_quality_lift_blocker_events_20260525-candidate-context-quality-lift.csv`
- `data/reports/forward_testing/candidate_walk_forward/candidate_context_quality_lift_20260525-candidate-context-quality-lift.md`

Current queue result:

- Wallets in queue: `2`
- Open blocker rows: `138`
- Clean proof rows: `35`
- Unique blocked tokens: `66`
- Repair entry timestamp wallets: `2`
- Repair market snapshot wallets: `0`
- Promotions allowed: `0`
- Wallet-list mutations: `0`
- Wallet-trust mutations: `0`

The primary blocker is missing forward entry price, not missing later market snapshots.

### Context Queue Detail

`D11LfGmruiKraNB9BtPqb1ELEYnNtpsNDuft32wArYV3`:

- Recommended action: `repair_entry_timestamp`
- Open blocker rows: `102`
- Clean proof rows: `16`
- Unique blocked tokens: `41`
- Missing forward entry price rows: `98`
- Missing outcome label rows: `4`
- Context completion rate: `0.1356`
- Excluded rate: `0.8644`

`2K5DekX2pitRReFBC4byUCv2Ci3o89StnBQnBbkA9BdN`:

- Recommended action: `repair_entry_timestamp`
- Open blocker rows: `36`
- Clean proof rows: `19`
- Unique blocked tokens: `25`
- Missing forward entry price rows: `31`
- Missing outcome label rows: `5`
- Context completion rate: `0.3455`
- Excluded rate: `0.6545`

## Entry Price Anchor Repair

Added a candidate-only entry-price anchor repair packet for the two survivor wallets. It parses preserved raw forward wallet transactions, finds same-transaction quote anchors, and writes separate anchor-enriched candidate records. It does not apply those records to the official merged evidence stream.

```bash
python3 -m utils.build_candidate_entry_price_anchor_repair --run-id 20260525-candidate-entry-price-anchor-repair
```

Outputs:

- `data/reports/forward_testing/candidate_walk_forward/candidate_entry_price_anchor_repair_20260525-candidate-entry-price-anchor-repair.json`
- `data/reports/forward_testing/candidate_walk_forward/candidate_entry_price_anchor_repair_20260525-candidate-entry-price-anchor-repair.csv`
- `data/reports/forward_testing/candidate_walk_forward/candidate_entry_price_anchor_repaired_records_20260525-candidate-entry-price-anchor-repair.jsonl`
- `data/reports/forward_testing/candidate_walk_forward/candidate_entry_price_anchor_rejected_records_20260525-candidate-entry-price-anchor-repair.jsonl`
- `data/reports/forward_testing/candidate_walk_forward/candidate_entry_price_anchor_repair_20260525-candidate-entry-price-anchor-repair.md`

Current repair result:

- Target wallets: `2`
- Missing entry price rows: `159`
- Anchor repaired rows: `159`
- Rejected rows: `0`
- Raw rows scanned: `17641`
- Raw anchor rows parsed: `13741`
- Promotions allowed: `0`
- Wallet-list mutations: `0`
- Wallet-trust mutations: `0`

Wallet repair counts:

- `D11LfGmruiKraNB9BtPqb1ELEYnNtpsNDuft32wArYV3`: `110/110` anchor repaired
- `2K5DekX2pitRReFBC4byUCv2Ci3o89StnBQnBbkA9BdN`: `49/49` anchor repaired

Then the existing review-only resolver was run on the separate anchor-enriched records:

```bash
python3 -m utils.build_forward_entry_context_resolver \
  --records data/reports/forward_testing/candidate_walk_forward/candidate_entry_price_anchor_repaired_records_20260525-candidate-entry-price-anchor-repair.jsonl \
  --market-context data/wallet_backfills/forward_market_context_snapshots.jsonl \
  --report-path data/reports/forward_testing/candidate_walk_forward/candidate_entry_price_anchor_resolver_report_20260525-candidate-entry-price-anchor-repair.json \
  --resolved-records-path data/reports/forward_testing/candidate_walk_forward/candidate_entry_price_anchor_resolved_records_20260525-candidate-entry-price-anchor-repair.jsonl \
  --rejected-records-path data/reports/forward_testing/candidate_walk_forward/candidate_entry_price_anchor_resolver_rejected_20260525-candidate-entry-price-anchor-repair.jsonl \
  --markdown-path data/reports/forward_testing/candidate_walk_forward/candidate_entry_price_anchor_resolver_report_20260525-candidate-entry-price-anchor-repair.md
```

Resolver result:

- Blocked rows scanned: `159`
- Quote-anchor candidates: `159`
- Resolved rows: `150`
- Known 15m outcomes: `82`
- Blocked without later snapshot: `9`
- Blocked without valid quote anchor: `0`
- Wallet-list mutations: `0`
- Wallet-trust mutations: `0`

After rebuilding the candidate-only walk-forward stack using only the separate resolved artifact:

- Survivor proof rows improved from `35` to `96`
- Survivor excluded rows improved from `138` to `77`
- Validation rows improved from `11` to `30`
- Eligible for manual paper-simulation review remained `0`

Post-repair survivor details:

- `2K5DekX2pitRReFBC4byUCv2Ci3o89StnBQnBbkA9BdN`: proof rows `35`, validation rows `11`, validation runners `9`, validation tokens `10`
- `D11LfGmruiKraNB9BtPqb1ELEYnNtpsNDuft32wArYV3`: proof rows `61`, validation rows `19`, validation runners `17`, validation tokens `14`

Remaining blockers after the separate repair pass:

- `D11LfGmruiKraNB9BtPqb1ELEYnNtpsNDuft32wArYV3`: `57` open blockers, mostly `54` missing outcome labels
- `2K5DekX2pitRReFBC4byUCv2Ci3o89StnBQnBbkA9BdN`: `20` open blockers, mostly `14` missing outcome labels

The next bottleneck is no longer entry-price anchoring. It is outcome/window completion plus a small number of missing later snapshots.

## Outcome Window Completion

Added a candidate-only outcome-window completion queue for the post-anchor-repair resolver outputs. This does not invent labels. It identifies which unresolved candidate rows need later market snapshots before the 15m outcome can be completed.

```bash
python3 -m utils.build_candidate_outcome_window_completion --run-id 20260525-candidate-outcome-window-completion
```

Outputs:

- `data/reports/forward_testing/candidate_walk_forward/candidate_outcome_window_completion_20260525-candidate-outcome-window-completion.json`
- `data/reports/forward_testing/candidate_walk_forward/candidate_outcome_window_completion_20260525-candidate-outcome-window-completion.csv`
- `data/reports/forward_testing/candidate_walk_forward/candidate_outcome_window_capture_queue_20260525-candidate-outcome-window-completion.csv`
- `data/reports/forward_testing/candidate_walk_forward/candidate_outcome_window_completion_20260525-candidate-outcome-window-completion.md`

Current completion queue:

- Records scanned: `159`
- Known 15m rows: `82`
- Unresolved 15m rows: `68`
- Rejected missing later snapshot rows: `9`
- Structurally blocked rows: `0`
- Capture queue rows: `77`
- Unique tokens to capture: `47`
- Wallets affected: `2`
- Promotions allowed: `0`
- Wallet-list mutations: `0`
- Wallet-trust mutations: `0`

Queue by wallet:

- `D11LfGmruiKraNB9BtPqb1ELEYnNtpsNDuft32wArYV3`: `57`
- `2K5DekX2pitRReFBC4byUCv2Ci3o89StnBQnBbkA9BdN`: `20`

Queue by blocker:

- `missing_15m_outcome`: `68`
- `missing_later_market_snapshot`: `9`

The next step is bounded snapshot capture for the `47` queued token/time windows, then rerun the resolver and paper-readiness gate.

## Bounded Candidate Snapshot Capture

Added a candidate-only bounded snapshot capture layer with a stale-window guard. It refuses to capture current snapshots for already-expired 15m windows because those snapshots would not be valid outcome-window evidence.

```bash
python3 -m utils.capture_candidate_bounded_snapshots --run-id 20260525-candidate-bounded-snapshot-capture --execute --max-market-context-calls 10
```

Outputs:

- `data/reports/forward_testing/candidate_walk_forward/candidate_bounded_snapshot_capture_20260525-candidate-bounded-snapshot-capture.json`
- `data/reports/forward_testing/candidate_walk_forward/candidate_bounded_snapshot_capture_snapshots_20260525-candidate-bounded-snapshot-capture.jsonl`
- `data/reports/forward_testing/candidate_walk_forward/candidate_bounded_snapshot_capture_snapshots_20260525-candidate-bounded-snapshot-capture.csv`
- `data/reports/forward_testing/candidate_walk_forward/candidate_bounded_snapshot_capture_deferred_20260525-candidate-bounded-snapshot-capture.csv`
- `data/reports/forward_testing/candidate_walk_forward/candidate_bounded_snapshot_capture_20260525-candidate-bounded-snapshot-capture.md`

Capture result:

- Input capture queue rows: `77`
- Deduped capture queue rows: `77`
- Capture eligible rows: `0`
- Deferred expired window rows: `77`
- Current snapshots captured: `0`
- Provider misses: `0`
- Unique tokens deferred: `47`
- Promotions allowed: `0`
- Wallet-list mutations: `0`
- Wallet-trust mutations: `0`

Interpretation: current-market capture is not valid for these rows because all 15m windows are already closed. The next real milestone is archival/onchain later-snapshot recovery for the deferred queue.

## Candidate Onchain Later-Snapshot Recovery

Added a candidate-only archival recovery layer for expired outcome windows. It uses preserved raw transactions after the signal timestamp to recover later token snapshots when current-market capture would be invalid.

```bash
python3 -m utils.build_candidate_onchain_later_snapshot_recovery --run-id 20260525-candidate-onchain-later-snapshot-recovery
```

Outputs:

- `data/reports/forward_testing/candidate_walk_forward/candidate_onchain_later_snapshot_recovery_20260525-candidate-onchain-later-snapshot-recovery.json`
- `data/reports/forward_testing/candidate_walk_forward/candidate_onchain_later_snapshot_recovery_records_20260525-candidate-onchain-later-snapshot-recovery.jsonl`
- `data/reports/forward_testing/candidate_walk_forward/candidate_onchain_later_snapshot_recovered_forward_records_20260525-candidate-onchain-later-snapshot-recovery.jsonl`
- `data/reports/forward_testing/candidate_walk_forward/candidate_onchain_later_snapshot_combined_repaired_records_20260525-candidate-onchain-later-snapshot-recovery.jsonl`
- `data/reports/forward_testing/candidate_walk_forward/candidate_onchain_later_snapshot_recovery_blocked_20260525-candidate-onchain-later-snapshot-recovery.csv`
- `data/reports/forward_testing/candidate_walk_forward/candidate_onchain_later_snapshot_recovery_20260525-candidate-onchain-later-snapshot-recovery.md`

Recovery result:

- Deferred rows scanned: `77`
- Candidate records built from resolved anchors: `68`
- Blocked missing anchor rows: `9`
- Known 15m outcomes added: `6`
- Recovered forward records written: `6`
- Combined repaired records written: `150`
- Records still blocked without later onchain snapshots: `62`
- Raw transactions scanned: `63881`
- Promotions allowed: `0`
- Wallet-list mutations: `0`
- Wallet-trust mutations: `0`

Recovered outcomes:

- `2K5DekX2pitRReFBC4byUCv2Ci3o89StnBQnBbkA9BdN`: `3` recovered 15m runner labels
- `D11LfGmruiKraNB9BtPqb1ELEYnNtpsNDuft32wArYV3`: `3` recovered 15m runner labels

Then the candidate-only walk-forward stack was rebuilt using the separate combined repaired-record artifact:

```bash
python3 -m utils.build_candidate_walk_forward_validation \
  --run-id 20260525-candidate-after-onchain-later-recovery \
  --repaired-records data/reports/forward_testing/candidate_walk_forward/candidate_onchain_later_snapshot_combined_repaired_records_20260525-candidate-onchain-later-snapshot-recovery.jsonl

python3 -m utils.build_candidate_walk_forward_survivor_review \
  --run-id 20260525-candidate-survivor-after-onchain-later-recovery \
  --walk-forward-report data/reports/forward_testing/candidate_walk_forward/candidate_walk_forward_validation_20260525-candidate-after-onchain-later-recovery.json \
  --repaired-records data/reports/forward_testing/candidate_walk_forward/candidate_onchain_later_snapshot_combined_repaired_records_20260525-candidate-onchain-later-snapshot-recovery.jsonl

python3 -m utils.build_candidate_walk_forward_paper_readiness_gate \
  --run-id 20260525-paper-readiness-after-onchain-later-recovery \
  --survivor-review data/reports/forward_testing/candidate_walk_forward/candidate_walk_forward_survivor_review_20260525-candidate-survivor-after-onchain-later-recovery.json
```

Post-recovery survivor result:

- Survivor proof rows improved from `96` to `102`
- Survivor excluded rows improved from `77` to `73`
- Validation event rows improved from `30` to `32`
- Eligible for manual paper-simulation review remained `0`

Post-recovery wallet details:

- `2K5DekX2pitRReFBC4byUCv2Ci3o89StnBQnBbkA9BdN`: proof rows `38`, validation rows `12`, validation runners `10`, validation tokens `10`, context completion rate `0.6667`, status `not_ready`
- `D11LfGmruiKraNB9BtPqb1ELEYnNtpsNDuft32wArYV3`: proof rows `64`, validation rows `20`, validation runners `18`, validation tokens `14`, context completion rate `0.5424`, status `not_ready`

Remaining blocker queue after onchain recovery:

- Open blocker rows: `73`
- Unique blocked tokens: `46`
- Missing outcome labels: `62`
- Missing valid execution quote rows: `11`

Interpretation: onchain recovery helped, but it did not change the operating conclusion. Both survivor wallets remain candidate-only and not ready for paper simulation. The correct next step is to continue forward collection and target the remaining missing outcome labels plus the small set of unresolved quote anchors.

### Readiness Detail

`2K5DekX2pitRReFBC4byUCv2Ci3o89StnBQnBbkA9BdN` is not ready:

- Proof rows: `19`
- Validation clean rows: `6`
- Validation runners: `5`
- Validation token count: `6`
- Excluded rate: `0.6545`
- Context completion rate: `0.3455`
- Failed gates: `min_total_clean_rows_not_met`, `min_validation_clean_rows_not_met`, `min_validation_token_count_not_met`, `min_context_completion_rate_not_met`, `max_excluded_rate_exceeded`

`D11LfGmruiKraNB9BtPqb1ELEYnNtpsNDuft32wArYV3` is not ready:

- Proof rows: `16`
- Validation clean rows: `5`
- Validation runners: `3`
- Validation token count: `5`
- Excluded rate: `0.8644`
- Context completion rate: `0.1356`
- Failed gates: `min_total_clean_rows_not_met`, `min_validation_clean_rows_not_met`, `min_validation_runner_count_not_met`, `min_validation_token_count_not_met`, `min_context_completion_rate_not_met`, `max_excluded_rate_exceeded`

## Verification

```bash
python3 -m pytest tests/test_candidate_bounded_snapshot_capture.py -q
python3 -m pytest tests/test_candidate_onchain_later_snapshot_recovery.py -q
python3 -m pytest tests/test_candidate_outcome_window_completion.py -q
python3 -m pytest tests/test_candidate_entry_price_anchor_repair.py -q
python3 -m pytest tests/test_candidate_context_quality_lift.py -q
python3 -m pytest tests/test_candidate_onchain_later_snapshot_recovery.py tests/test_candidate_bounded_snapshot_capture.py tests/test_candidate_outcome_window_completion.py tests/test_candidate_entry_price_anchor_repair.py tests/test_candidate_context_quality_lift.py tests/test_candidate_walk_forward_paper_readiness_gate.py tests/test_candidate_walk_forward_survivor_review.py tests/test_candidate_walk_forward_validation.py tests/test_forward_entry_context_resolver.py tests/test_onchain_later_outcome_backfill.py -q
python3 -m pytest tests/test_candidate_context_quality_lift.py tests/test_candidate_walk_forward_paper_readiness_gate.py tests/test_candidate_walk_forward_survivor_review.py tests/test_candidate_walk_forward_validation.py -q
python3 -m pytest tests/test_candidate_walk_forward_paper_readiness_gate.py tests/test_candidate_walk_forward_survivor_review.py tests/test_candidate_walk_forward_validation.py -q
python3 -m pytest tests/test_candidate_walk_forward_survivor_review.py tests/test_candidate_walk_forward_validation.py -q
python3 -m pytest -q
```

Result: `869 passed`.
