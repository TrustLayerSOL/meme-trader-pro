# 2026-05-24 Market Snapshot Repair Queue

## Purpose

Create a focused repair queue for rows that already have Helius-recovered quote anchors but remain blocked because they lack later market snapshots.

This is review-only. It does not collect market data, repair canonical records, mutate wallet trust, mutate wallet lists, promote wallets, unlock live execution, or execute trades.

## Command

```bash
python3 -m utils.build_forward_market_snapshot_repair_queue --rejected-records data/reports/forward_testing/helius_quote_anchor_merge/forward_helius_quote_anchor_merge_rejected_20260524-helius-quote-anchor-merge-250.jsonl --run-id 20260524-market-snapshot-repair-queue-250
```

## Outputs

- `data/reports/forward_testing/market_snapshot_repair_queue/forward_market_snapshot_repair_queue_20260524-market-snapshot-repair-queue-250.json`
- `data/reports/forward_testing/market_snapshot_repair_queue/forward_market_snapshot_repair_queue_20260524-market-snapshot-repair-queue-250.csv`
- `data/reports/forward_testing/market_snapshot_repair_queue/forward_market_snapshot_repair_queue_20260524-market-snapshot-repair-queue-250.md`

## Result

- Input rejected records: 2,531
- Missing later market snapshot rows: 614
- Queued token mints: 324
- Queued wallets: 17
- Top token blocked rows: 18
- Repair rows written: 0
- Promotions allowed: 0
- Wallet trust mutations: 0
- Wallet list mutations: 0

Top queued token mints:

| Token | Rows | Wallets |
| --- | ---: | ---: |
| `B4CpMwR6xX8XigLUoFTJcz3auczCJshLxhZAud7Ypump` | 18 | 3 |
| `2D6PovdKHE4JVfcxtro8EC2w8RmZMDhRA8eMKxE4pump` | 9 | 1 |
| `APnYywLJov813xdZn1uxctspfU2M6Coairq7hy8gd2Qr` | 8 | 1 |
| `AgbEjPQxJ9wjXgAPdEEbv5fo2u74u81aaZ8ZeBreMoXY` | 8 | 1 |
| `2RKqPTpXLW4C5VuGm6wxvFobtyvAeF2tj6Gfs51HCgzh` | 7 | 1 |

## Safety

- Canonical resolver files were not overwritten.
- Canonical wallet score/trust/list files were not mutated.
- Promotions allowed: 0
- Wallet trust mutations: 0
- Wallet list mutations: 0
- Live execution: locked
- Trades executed: 0
