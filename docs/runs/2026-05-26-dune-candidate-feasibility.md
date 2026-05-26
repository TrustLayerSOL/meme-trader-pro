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
- `data/reports/forward_testing/candidate_walk_forward/dune_candidate_resolver_adapter_20260526-dune-resolver-adapter-live-v4.json`
- `data/reports/forward_testing/candidate_walk_forward/dune_candidate_resolver_adapter_events_20260526-dune-resolver-adapter-live-v4.csv`
- `data/reports/forward_testing/candidate_walk_forward/dune_candidate_context_candidate_records_20260526-dune-resolver-adapter-live-v4.jsonl`
- `data/reports/forward_testing/candidate_walk_forward/dune_candidate_resolver_adapter_20260526-dune-resolver-adapter-live-v4.md`

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

The review-only resolver adapter attached the joined Dune context candidates to local forward rows while keeping every adapted row blocked:

- Forward records scanned: `4,219`
- Joined events scanned: `5`
- Context candidate records: `5`
- Price candidate records: `3`
- Quote-only candidate records: `2`
- Liquidity candidate records: `0`
- Market-cap candidate records: `0`
- Proof-ready records: `0`
- Promotions allowed: `0`
- Wallet-list mutations: `0`
- Wallet-trust mutations: `0`

## Interpretation

Dune is useful for candidate-only historical testing because it can provide historical DEX trade rows, token-transfer rows, and token price coverage for the frozen candidate wallets. These rows can help build older training windows and identify same-transaction quote-anchor candidates.

Dune does not, by itself, clear the current proof blocker. The project still needs decision-time-safe liquidity and market-cap context for score-ready proof rows. Market cap still requires reliable historical token supply or equivalent trusted evidence, and liquidity still needs pool/vault reserve evidence rather than only trade amount.

## Next Step

Use the Dune probe, join, and resolver-adapter outputs as historical context candidates only. The next implementation step is reconstructing decision-time-safe liquidity and market-cap context for the five joined candidate events, then rerunning the candidate-only walk-forward validation with those rows still excluded from proof metrics unless the resolver marks them complete.

## Verification

```bash
python3 -m pytest tests/test_dune_candidate_feasibility.py -q
python3 -m pytest tests/test_dune_candidate_feasibility.py tests/test_dune_candidate_join.py -q
python3 -m pytest tests/test_dune_candidate_resolver_adapter.py -q
python3 -m pytest tests/test_dune_candidate_feasibility.py tests/test_dune_candidate_join.py tests/test_dune_candidate_resolver_adapter.py tests/test_candidate_walk_forward_validation.py tests/test_candidate_walk_forward_survivor_review.py tests/test_candidate_walk_forward_paper_readiness_gate.py -q
```

Result: `3 passed` for the resolver adapter tests and `22 passed` for the combined Dune/candidate validation tests.
