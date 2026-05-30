# 2026-05-24 Helius Quote Anchor Merge

## Purpose

Route recovered Helius quote anchors through the existing forward entry-context resolver without overwriting canonical resolver files.

This is review-only. It does not repair canonical records, mutate wallet trust, mutate wallet lists, promote wallets, unlock live execution, or execute trades.

## Commands

Merge recovered quote anchors into a temporary resolver input:

```bash
python3 -m utils.build_forward_helius_quote_anchor_merge --quote-probe data/reports/forward_testing/helius_quote_probe/forward_helius_quote_probe_20260524-helius-native-quote-probe-25.json --run-id 20260524-helius-quote-anchor-merge
```

Build an isolated merged calibration scorecard from the isolated resolved rows:

```bash
python3 -m utils.build_forward_merged_calibration_scorecard --repaired-records data/reports/forward_testing/helius_quote_anchor_merge/forward_helius_quote_anchor_merge_resolved_20260524-helius-quote-anchor-merge.jsonl --report-path data/reports/forward_testing/helius_quote_anchor_merge/forward_helius_quote_anchor_merge_scorecard_20260524-helius-quote-anchor-merge.json --markdown-path data/reports/forward_testing/helius_quote_anchor_merge/forward_helius_quote_anchor_merge_scorecard_20260524-helius-quote-anchor-merge.md
```

## Outputs

- `data/reports/forward_testing/helius_quote_anchor_merge/forward_helius_quote_anchor_merge_20260524-helius-quote-anchor-merge.json`
- `data/reports/forward_testing/helius_quote_anchor_merge/forward_helius_quote_anchor_merge_20260524-helius-quote-anchor-merge.csv`
- `data/reports/forward_testing/helius_quote_anchor_merge/forward_helius_quote_anchor_merge_20260524-helius-quote-anchor-merge.md`
- `data/reports/forward_testing/helius_quote_anchor_merge/forward_helius_quote_anchor_merge_resolved_20260524-helius-quote-anchor-merge.jsonl`
- `data/reports/forward_testing/helius_quote_anchor_merge/forward_helius_quote_anchor_merge_rejected_20260524-helius-quote-anchor-merge.jsonl`
- `data/reports/forward_testing/helius_quote_anchor_merge/forward_helius_quote_anchor_merge_scorecard_20260524-helius-quote-anchor-merge.json`
- `data/reports/forward_testing/helius_quote_anchor_merge/forward_helius_quote_anchor_merge_scorecard_20260524-helius-quote-anchor-merge.md`

## Result

- Input forward records: 3,937
- Input quote-probe rows: 25
- Recoverable quote anchors: 20
- Records augmented with quote anchor: 20
- Isolated resolver resolved rows: 94
- Isolated resolver known 15m outcomes: 60
- Isolated resolver blocked without later snapshot: 491
- Isolated resolver blocked without quote anchor: 2,126

Compared with the canonical merged scorecard:

- Repaired/replaced rows increased from 84 to 94.
- Blocked records decreased from 2,627 to 2,617.
- Known 15m outcomes stayed at 1,280.
- Review-behavioral-signal wallets stayed at 3.
- Flat/noise candidate wallets stayed at 6.
- Fix-context wallets stayed at 21.

## Safety

- Canonical resolver files were not overwritten.
- Canonical wallet score/trust/list files were not mutated.
- Promotions allowed: 0
- Wallet trust mutations: 0
- Wallet list mutations: 0
- Live execution: locked
- Trades executed: 0
