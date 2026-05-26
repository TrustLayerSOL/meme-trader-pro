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
- `data/reports/forward_testing/candidate_walk_forward/dune_candidate_context_completion_20260526-dune-context-completion-live-v1.json`
- `data/reports/forward_testing/candidate_walk_forward/dune_candidate_context_completion_events_20260526-dune-context-completion-live-v1.csv`
- `data/reports/forward_testing/candidate_walk_forward/dune_candidate_context_completed_records_20260526-dune-context-completion-live-v1.jsonl`
- `data/reports/forward_testing/candidate_walk_forward/dune_candidate_context_blocked_records_20260526-dune-context-completion-live-v1.jsonl`
- `data/reports/forward_testing/candidate_walk_forward/dune_candidate_context_completion_20260526-dune-context-completion-live-v1.md`

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

The candidate-only context completion layer then merged those Dune context candidates with near-event forward market snapshots using a 120-second lag cap:

- Candidate records scanned: `5`
- Context-complete records: `3`
- Proof-ready candidate records: `3`
- Blocked records: `2`
- Blocked missing price records: `2`
- Blocked missing liquidity records: `2`
- Blocked missing market-cap records: `2`
- Promotions allowed: `0`
- Wallet-list mutations: `0`
- Wallet-trust mutations: `0`

The three completed rows all belong to `2tgUbS9UMoQD6GkDZBiqKYCURnGrSb6ocYwRABrSJUvY` and had near-event market snapshots inside 20 seconds. The two blocked rows remain excluded because they have no Dune token price and no acceptable near snapshot inside the 120-second window.

## Interpretation

Dune is useful for candidate-only historical testing because it can provide historical DEX trade rows, token-transfer rows, and token price coverage for the frozen candidate wallets. These rows can help build older training windows and identify same-transaction quote-anchor candidates.

Dune does not, by itself, clear the current proof blocker. It becomes more useful when paired with forward market snapshots, but rows must still satisfy the candidate-only context-completion checks before they are eligible for walk-forward proof metrics.

## Next Step

Rerun the candidate-only walk-forward validation with the three context-complete Dune candidate rows as a separate validation input. Keep the two blocked rows excluded from proof metrics and continue collecting fresh forward evidence for the candidate wallets.

## Verification

```bash
python3 -m pytest tests/test_dune_candidate_feasibility.py -q
python3 -m pytest tests/test_dune_candidate_feasibility.py tests/test_dune_candidate_join.py -q
python3 -m pytest tests/test_dune_candidate_resolver_adapter.py -q
python3 -m pytest tests/test_dune_candidate_context_completion.py -q
python3 -m pytest tests/test_dune_candidate_feasibility.py tests/test_dune_candidate_join.py tests/test_dune_candidate_resolver_adapter.py tests/test_candidate_walk_forward_validation.py tests/test_candidate_walk_forward_survivor_review.py tests/test_candidate_walk_forward_paper_readiness_gate.py -q
```

Result: `3 passed` for the resolver adapter tests, `3 passed` for the context-completion tests, and `22 passed` for the combined Dune/candidate validation tests.
