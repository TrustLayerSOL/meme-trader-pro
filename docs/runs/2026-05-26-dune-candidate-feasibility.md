# 2026-05-26 Dune Candidate Feasibility Probe

## Purpose

This run tests whether Dune can support candidate-only historical walk-forward evidence for MemeTraderPro / Quant Wallet Tracker V2.

The probe is review-only. It does not promote wallets, mutate wallet trust, mutate wallet lists, change execution settings, unlock live execution, or claim profitability.

## Commands

Dry-run SQL/report generation:

```bash
python3 -m utils.build_dune_candidate_feasibility_probe --run-id 20260526-dune-candidate-feasibility
```

Live Dune probe:

```bash
python3 -m utils.build_dune_candidate_feasibility_probe \
  --execute \
  --start-date 2026-04-26 \
  --end-date 2026-05-27 \
  --limit 100 \
  --run-id 20260526-dune-candidate-feasibility-live
```

## Outputs

- `data/reports/forward_testing/candidate_walk_forward/dune_candidate_feasibility_20260526-dune-candidate-feasibility-live-v4.json`
- `data/reports/forward_testing/candidate_walk_forward/dune_candidate_feasibility_wallets_20260526-dune-candidate-feasibility-live-v4.csv`
- `data/reports/forward_testing/candidate_walk_forward/dune_candidate_feasibility_20260526-dune-candidate-feasibility-live-v4.md`
- `data/reports/forward_testing/candidate_walk_forward/dune_candidate_feasibility_sql_20260526-dune-candidate-feasibility-live-v4.json`
- `data/reports/forward_testing/candidate_walk_forward/dune_candidate_feasibility_rows_20260526-dune-candidate-feasibility-live-v4.json`
- `data/reports/forward_testing/candidate_walk_forward/dune_candidate_join_20260526-dune-candidate-join-live-v4.json`
- `data/reports/forward_testing/candidate_walk_forward/dune_candidate_join_events_20260526-dune-candidate-join-live-v4.csv`
- `data/reports/forward_testing/candidate_walk_forward/dune_candidate_join_20260526-dune-candidate-join-live-v4.md`

## Summary

- Candidate wallets: `3`
- Query count: `4`
- Queries completed: `3`
- Queries failed: `1`
- Rows returned: `300`
- Wallets with transaction history or DEX/transfer evidence: `3`
- Wallets with DEX matches: `3`
- Quote-anchor candidate rows: `100`
- Price-context candidate rows: `95`
- Liquidity-context candidate rows: `0`
- Market-cap context candidate rows: `0`
- Proof-ready rows from Dune alone: `0`
- Promotions allowed: `0`
- Wallet-list mutations: `0`
- Wallet-trust mutations: `0`

The raw `solana.transactions` aggregation exceeded the initial polling window, but Dune still returned DEX, token-transfer, and price-coverage evidence for all three candidate wallets. That is enough to confirm Dune is useful as a historical backfill source. It is not enough to treat Dune as a complete trust-validation source by itself.

The follow-up join layer matched the live Dune DEX rows to local candidate events:

- Candidate events scanned: `1,148`
- Dune DEX rows: `100`
- Matched events: `5`
- Exact signature matches: `2`
- Wallet/token/time-window matches: `3`
- Quote-anchor candidate events: `5`
- Price-context candidate events: `3`
- Liquidity-context candidate events: `0`
- Market-cap context candidate events: `0`
- Proof-ready events: `0`

Two exact-signature rows had Dune DEX amount and quote context but no candidate-token amount, so the corrected SQL leaves `price_usd` empty for those rows instead of carrying SOL price as token price.

## Interpretation

Dune is useful for candidate-only historical testing because it can provide historical DEX trade rows, token-transfer rows, and token price coverage for the frozen candidate wallets. These rows can help build older training windows and identify same-transaction quote-anchor candidates.

Dune does not, by itself, clear the current proof blocker. The project still needs decision-time-safe liquidity and market-cap context for score-ready proof rows. Market cap still requires reliable historical token supply or equivalent trusted evidence, and liquidity still needs pool/vault reserve evidence rather than only trade amount.

## Next Step

Use the Dune probe output as a backfill source for a candidate-only join layer keyed by wallet, token mint, transaction signature, and time window. Keep Dune-derived rows out of trust metrics until the existing resolver marks them clean for price, liquidity, market cap, and outcome context.

The next implementation step is a review-only resolver adapter that can consume `dune_candidate_join_events_*.csv/json`, preserve quote/price candidates, and keep rows blocked until liquidity and market-cap fields are reconstructed.

## Verification

```bash
python3 -m pytest tests/test_dune_candidate_feasibility.py -q
python3 -m pytest tests/test_dune_candidate_feasibility.py tests/test_dune_candidate_join.py -q
```

Result: `7 passed` for the focused Dune tests.
