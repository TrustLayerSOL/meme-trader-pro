# 2026-05-24 Market Snapshot Capture

## Purpose

Run a bounded review-only market snapshot capture pass for the top rows in the market-snapshot repair queue, then measure the impact through the isolated Helius quote-anchor merge and merged calibration scorecard.

This is not a canonical repair. It does not overwrite market context, resolver outputs, wallet trust, wallet lists, promotions, execution settings, or live trading state.

## Commands

Dry-run selection:

```bash
python3 -m utils.capture_forward_market_snapshot_repair_queue --repair-queue data/reports/forward_testing/market_snapshot_repair_queue/forward_market_snapshot_repair_queue_20260524-market-snapshot-repair-queue-250.json --max-mints 10 --max-market-context-calls 10 --run-id 20260524-market-snapshot-capture-top10-dry-run
```

Bounded execution:

```bash
python3 -m utils.capture_forward_market_snapshot_repair_queue --repair-queue data/reports/forward_testing/market_snapshot_repair_queue/forward_market_snapshot_repair_queue_20260524-market-snapshot-repair-queue-250.json --max-mints 10 --max-market-context-calls 10 --execute --run-id 20260524-market-snapshot-capture-top10
```

Isolated merge using captured context:

```bash
python3 -m utils.build_forward_helius_quote_anchor_merge --quote-probe data/reports/forward_testing/helius_quote_probe/forward_helius_quote_probe_20260524-helius-quote-probe-250.json --market-context data/reports/forward_testing/market_snapshot_capture/forward_market_snapshot_capture_combined_market_context_20260524-market-snapshot-capture-top10.jsonl --run-id 20260524-helius-quote-anchor-merge-250-market-top10
```

Isolated scorecard:

```bash
python3 -m utils.build_forward_merged_calibration_scorecard --repaired-records data/reports/forward_testing/helius_quote_anchor_merge/forward_helius_quote_anchor_merge_resolved_20260524-helius-quote-anchor-merge-250-market-top10.jsonl --report-path data/reports/forward_testing/market_snapshot_capture/forward_market_snapshot_capture_scorecard_20260524-market-snapshot-capture-top10.json --markdown-path data/reports/forward_testing/market_snapshot_capture/forward_market_snapshot_capture_scorecard_20260524-market-snapshot-capture-top10.md
```

Second bounded batch using the first batch's combined context:

```bash
python3 -m utils.capture_forward_market_snapshot_repair_queue --repair-queue data/reports/forward_testing/market_snapshot_repair_queue/forward_market_snapshot_repair_queue_20260524-market-snapshot-repair-queue-250.json --existing-market-context data/reports/forward_testing/market_snapshot_capture/forward_market_snapshot_capture_combined_market_context_20260524-market-snapshot-capture-top10.jsonl --start-index 10 --max-mints 10 --max-market-context-calls 10 --execute --run-id 20260524-market-snapshot-capture-batch2
```

Second isolated merge and scorecard:

```bash
python3 -m utils.build_forward_helius_quote_anchor_merge --quote-probe data/reports/forward_testing/helius_quote_probe/forward_helius_quote_probe_20260524-helius-quote-probe-250.json --market-context data/reports/forward_testing/market_snapshot_capture/forward_market_snapshot_capture_combined_market_context_20260524-market-snapshot-capture-batch2.jsonl --run-id 20260524-helius-quote-anchor-merge-250-market-batch2
python3 -m utils.build_forward_merged_calibration_scorecard --repaired-records data/reports/forward_testing/helius_quote_anchor_merge/forward_helius_quote_anchor_merge_resolved_20260524-helius-quote-anchor-merge-250-market-batch2.jsonl --report-path data/reports/forward_testing/market_snapshot_capture/forward_market_snapshot_capture_scorecard_20260524-market-snapshot-capture-batch2.json --markdown-path data/reports/forward_testing/market_snapshot_capture/forward_market_snapshot_capture_scorecard_20260524-market-snapshot-capture-batch2.md
```

## Outputs

- `data/reports/forward_testing/market_snapshot_capture/forward_market_snapshot_capture_20260524-market-snapshot-capture-top10.json`
- `data/reports/forward_testing/market_snapshot_capture/forward_market_snapshot_capture_20260524-market-snapshot-capture-top10.csv`
- `data/reports/forward_testing/market_snapshot_capture/forward_market_snapshot_capture_20260524-market-snapshot-capture-top10.md`
- `data/reports/forward_testing/market_snapshot_capture/forward_market_snapshot_capture_snapshots_20260524-market-snapshot-capture-top10.jsonl`
- `data/reports/forward_testing/market_snapshot_capture/forward_market_snapshot_capture_combined_market_context_20260524-market-snapshot-capture-top10.jsonl`
- `data/reports/forward_testing/helius_quote_anchor_merge/forward_helius_quote_anchor_merge_20260524-helius-quote-anchor-merge-250-market-top10.json`
- `data/reports/forward_testing/market_snapshot_capture/forward_market_snapshot_capture_scorecard_20260524-market-snapshot-capture-top10.json`
- `data/reports/forward_testing/market_snapshot_capture/forward_market_snapshot_capture_20260524-market-snapshot-capture-batch2.json`
- `data/reports/forward_testing/market_snapshot_capture/forward_market_snapshot_capture_combined_market_context_20260524-market-snapshot-capture-batch2.jsonl`
- `data/reports/forward_testing/helius_quote_anchor_merge/forward_helius_quote_anchor_merge_20260524-helius-quote-anchor-merge-250-market-batch2.json`
- `data/reports/forward_testing/market_snapshot_capture/forward_market_snapshot_capture_scorecard_20260524-market-snapshot-capture-batch2.json`

## Result

- Queue rows available: 324
- Selected mints: 10
- Market-context call limit: 10
- Snapshots captured: 3
- Provider misses: 7
- Existing market snapshots: 2,422
- Combined isolated market snapshots: 2,425

Compared with the isolated 250-row Helius quote-anchor merge before the capture:

- Isolated resolver resolved rows increased from 180 to 213.
- Isolated rejected rows decreased from 2,531 to 2,498.
- Scorecard repaired/replaced rows increased from 180 to 213.
- Scorecard blocked records decreased from 2,531 to 2,498.
- Known 15m outcomes stayed at 1,282.
- Runner 15m outcomes stayed at 63.
- Review-behavioral-signal wallets stayed at 4.
- Fix-context wallets decreased from 21 to 20.
- Collect-more-evidence wallets increased from 2 to 3.

Second batch cumulative result:

- Additional selected mints: 10
- Additional snapshots captured: 2
- Additional provider misses: 8
- Cumulative captured snapshots: 5
- Cumulative combined isolated market snapshots: 2,427
- Isolated resolver resolved rows increased from 213 to 223.
- Isolated rejected rows decreased from 2,498 to 2,488.
- Scorecard repaired/replaced rows increased from 213 to 223.
- Scorecard blocked records decreased from 2,498 to 2,488.
- Known 15m outcomes stayed at 1,282.
- Runner 15m outcomes stayed at 63.
- Review-behavioral-signal wallets stayed at 4.
- Fix-context wallets stayed at 20.

## Interpretation

The top-10 capture proved the repair lane works, but Dexscreener only had usable current data for 3 of the selected queued mints. This means current public market snapshots can reduce some context blockers, but they will not recover every historical gap. The next practical improvement is to continue small bounded capture batches for queued mints with available current pairs, while preserving blocked rows that need true historical context or unrecoverable quote anchors.

## Safety

- Canonical market-context files were not overwritten.
- Canonical resolver files were not overwritten.
- Canonical wallet score/trust/list files were not mutated.
- Promotions allowed: 0
- Wallet trust mutations: 0
- Wallet list mutations: 0
- Live execution: locked
- Trades executed: 0
