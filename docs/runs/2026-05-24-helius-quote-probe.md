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

Helius returned transaction bodies successfully for all six attempted rows.

- Rows selected: 6
- Rows attempted: 6
- Transactions fetched: 6
- RPC failures: 0
- Recoverable quote rows: 0
- Repaired rows written: 0
- Promotions allowed: 0
- Wallet trust mutations: 0
- Wallet list mutations: 0

The sampled transaction bodies included matching token deltas, but did not expose a same-transaction quote token delta under the current parser. That means standard Helius RPC is useful for reliable transaction retrieval, but this specific blocker likely needs either an enhanced Helius transaction parser, native SOL balance-delta handling, or a separate market-context repair path.

## Safety

`ExecutionSafetyGate().report()` stayed `PAPER_SAFE`.

- Live trading allowed: `false`
- Live trading enabled: `false`
- Paper mode enabled: `true`
- Repaired rows written: `0`
- Promotions allowed: `0`
- Wallet trust mutations: `0`
- Wallet list mutations: `0`
