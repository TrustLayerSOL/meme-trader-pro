# 2026-05-24 Helius Quote Probe

## Purpose

Test whether Helius can help reduce forward records blocked by `missing_valid_execution_price_quote`.

This is a review-only probe. It does not write repaired records, mutate wallet trust, mutate wallet lists, promote wallets, unlock live execution, or execute trades.

## Commands

Dry-run selection:

```bash
python3 -m utils.run_forward_helius_quote_probe --wallet 6b86E2apHeeHoLeeZs5bRSW8gFGDNqYH468mqVGuccdi --max-rows 3 --run-id 20260524-helius-quote-probe-dry-run
```

Bounded Helius execution:

```bash
python3 -m utils.run_forward_helius_quote_probe --wallet 6b86E2apHeeHoLeeZs5bRSW8gFGDNqYH468mqVGuccdi --max-rows 3 --execute --allow-paid-rpc --run-id 20260524-helius-quote-probe
```

General three-row sample:

```bash
python3 -m utils.run_forward_helius_quote_probe --max-rows 3 --execute --allow-paid-rpc --run-id 20260524-helius-quote-probe-general
```

## Outputs

- `data/reports/forward_testing/helius_quote_probe/forward_helius_quote_probe_20260524-helius-quote-probe.json`
- `data/reports/forward_testing/helius_quote_probe/forward_helius_quote_probe_20260524-helius-quote-probe.csv`
- `data/reports/forward_testing/helius_quote_probe/forward_helius_quote_probe_20260524-helius-quote-probe-general.json`
- `data/reports/forward_testing/helius_quote_probe/forward_helius_quote_probe_20260524-helius-quote-probe-general.csv`

## Result

Helius returned transaction bodies successfully for all attempted rows. The first implementation fetched transactions but recovered `0` quote anchors because the parser only used SPL token-balance deltas. The completed implementation now also recovers quote anchors from native SOL balance deltas with fee adjustment.

- Rows selected in final 25-row sample: 25
- Rows attempted: 25
- Transactions fetched: 25
- RPC failures: 0
- Recoverable quote rows: 20
- Unrecoverable rows: 5
- Repaired rows written: 0
- Promotions allowed: 0
- Wallet trust mutations: 0
- Wallet list mutations: 0

The five unrecovered rows had matching token deltas but no quote movement on the tracked wallet account. They remain blocked rather than guessed.

This closes the Helius quote-probe lane as an implementation milestone: Helius is reachable, paid-RPC usage is explicit, dry-run is safe by default, native SOL quote recovery is supported, unrecoverable rows are classified, and no repair/trust/list/execution mutation is performed.

## Safety

`ExecutionSafetyGate().report()` stayed `PAPER_SAFE`.

- Live trading allowed: `false`
- Live trading enabled: `false`
- Paper mode enabled: `true`
- Repaired rows written: `0`
- Promotions allowed: `0`
- Wallet trust mutations: `0`
- Wallet list mutations: `0`
