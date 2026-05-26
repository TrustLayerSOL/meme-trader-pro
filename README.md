# MemeTraderPro / Quant Wallet Tracker V2

MemeTraderPro is a paper-safe wallet-intelligence research system. It studies wallet behavior under replay-safe and forward-evidence conditions to decide whether any wallet deserves continued trust validation.

It is not a trading bot, signal feed, or live execution engine. Live execution remains locked, and review artifacts must not promote wallets, mutate wallet trust, mutate wallet lists, or claim profitability.

## Current Research Thesis

The working thesis is that a small number of wallets may show repeatable behavior that is visible before the market fully reacts. The project is trying to prove or disprove that with clean evidence:

- wallet activity captured at observation time
- decision-time market context
- fixed outcome windows
- blocked/no-trade rows preserved instead of guessed
- conservative wallet buckets
- manual review before any trust discussion

## First Forward Wallet Trust Review Packet

The current milestone is the First Forward Wallet Trust Review Packet. It summarizes the top review-only behavioral wallets, creates row-level event evidence, analyzes missing entry context, checks public-RPC collection health, verifies safety locks, and updates Obsidian review pages when a vault is available.

Run it with:

```bash
python3 -m utils.build_forward_wallet_trust_review_packet --bucket review_behavioral_signal --limit 3
```

The deterministic run used for the current review packet is:

```bash
python3 -m utils.build_forward_wallet_trust_review_packet --bucket review_behavioral_signal --limit 3 --run-id 20260524-forward-wallet-trust-review
```

Primary output:

```text
data/reports/forward_testing/wallet_trust_review/forward_wallet_trust_review_packet_20260524-forward-wallet-trust-review.json
```

## How To Read The Packet

- `continue_trust_validation` means the wallet deserves more clean forward validation. It does not mean trusted.
- `likely_flat_noise` means the known sample is mostly flat and should be held as negative evidence unless future forward rows change the picture.
- `fix_context_before_review` means missing decision-time context blocks review.
- `manual_review_required` means a human must inspect the evidence rows before interpreting behavior.

Context gaps are the main validation blocker. A blocked record is not discarded, but it cannot support trust validation until the missing context is repaired or explicitly classified.

## Context Blocker Reduction

After the trust review packet, use the context blocker reduction packet to prioritize the `fix_context` wallets by missing evidence type:

```bash
python3 -m utils.build_forward_context_blocker_reduction
```

Deterministic current run:

```bash
python3 -m utils.build_forward_context_blocker_reduction --run-id 20260524-context-blocker-reduction
```

Primary output:

```text
data/reports/forward_testing/context_blocker_reduction/forward_context_blocker_reduction_20260524-context-blocker-reduction.json
```

The output separates rows that need later market snapshots from rows that need a valid execution-price quote or timestamp anchor. It is still review-only and cannot mutate trust, wallet lists, or execution.

## Helius Quote Probe

Helius can be used for a tiny review-only probe against `missing_valid_execution_price_quote` rows. Dry-run is the default and makes no RPC calls:

```bash
python3 -m utils.run_forward_helius_quote_probe --wallet 6b86E2apHeeHoLeeZs5bRSW8gFGDNqYH468mqVGuccdi --max-rows 3
```

Paid-RPC execution requires both switches:

```bash
python3 -m utils.run_forward_helius_quote_probe --wallet 6b86E2apHeeHoLeeZs5bRSW8gFGDNqYH468mqVGuccdi --max-rows 3 --execute --allow-paid-rpc
```

The probe only tests whether Helius transaction bodies expose same-transaction quote anchors that the parser can use, including native SOL balance-delta anchors with fee adjustment. It writes reports under `data/reports/forward_testing/helius_quote_probe/`; it does not repair records, mutate wallet trust, mutate wallet lists, promote wallets, or execute trades.

Recovered Helius quote anchors can be routed through the existing entry-context resolver in an isolated review run:

```bash
python3 -m utils.build_forward_helius_quote_anchor_merge --quote-probe data/reports/forward_testing/helius_quote_probe/forward_helius_quote_probe_20260524-helius-native-quote-probe-25.json
```

This writes review-only merge outputs under `data/reports/forward_testing/helius_quote_anchor_merge/`. Canonical resolver files are not overwritten.

Rows that still fail because they need later market snapshots can be grouped into a targeted repair queue:

```bash
python3 -m utils.build_forward_market_snapshot_repair_queue --rejected-records data/reports/forward_testing/helius_quote_anchor_merge/forward_helius_quote_anchor_merge_rejected_20260524-helius-quote-anchor-merge-250.jsonl
```

The queue writes review-only JSON/CSV/Markdown under `data/reports/forward_testing/market_snapshot_repair_queue/`.

Use the queue for a bounded market snapshot capture pass. Dry-run is the default and makes no market-data calls:

```bash
python3 -m utils.capture_forward_market_snapshot_repair_queue --repair-queue data/reports/forward_testing/market_snapshot_repair_queue/forward_market_snapshot_repair_queue_20260524-market-snapshot-repair-queue-250.json --max-mints 10 --max-market-context-calls 10
```

Execution requires `--execute` and writes isolated snapshot files under `data/reports/forward_testing/market_snapshot_capture/`:

```bash
python3 -m utils.capture_forward_market_snapshot_repair_queue --repair-queue data/reports/forward_testing/market_snapshot_repair_queue/forward_market_snapshot_repair_queue_20260524-market-snapshot-repair-queue-250.json --max-mints 10 --max-market-context-calls 10 --execute --run-id 20260524-market-snapshot-capture-top10
```

Use `--start-index` plus the prior combined context file to process the next bounded batch without re-querying the same queue rows:

```bash
python3 -m utils.capture_forward_market_snapshot_repair_queue --repair-queue data/reports/forward_testing/market_snapshot_repair_queue/forward_market_snapshot_repair_queue_20260524-market-snapshot-repair-queue-250.json --existing-market-context data/reports/forward_testing/market_snapshot_capture/forward_market_snapshot_capture_combined_market_context_20260524-market-snapshot-capture-top10.jsonl --start-index 10 --max-mints 10 --max-market-context-calls 10 --execute --run-id 20260524-market-snapshot-capture-batch2
```

## Dune Candidate Feasibility Probe

Dune can be evaluated as a candidate-only historical backfill source without changing trust, wallet lists, recommendations, or execution settings. Dry-run writes the SQL bundle and deterministic report without making API calls:

```bash
python3 -m utils.build_dune_candidate_feasibility_probe --run-id 20260526-dune-candidate-feasibility
```

Live Dune execution requires an explicit environment variable and remains review-only:

```bash
DUNE_API_KEY=... python3 -m utils.build_dune_candidate_feasibility_probe --execute --run-id 20260526-dune-candidate-feasibility-live
```

The probe checks whether Dune can provide historical wallet activity, DEX-trade quote-anchor candidates, token-transfer context, and price-context candidates for the three frozen candidate wallets. It deliberately keeps `proof_ready_rows` at zero unless price, liquidity, and market-cap context are all complete. Dune rows are evidence candidates, not trust proof.

Join Dune DEX rows to local candidate events after a live probe emits the row artifact:

```bash
python3 -m utils.build_dune_candidate_join \
  --dune-rows data/reports/forward_testing/candidate_walk_forward/dune_candidate_feasibility_rows_20260526-dune-candidate-feasibility-live-v4.json \
  --run-id 20260526-dune-candidate-join-live-v4
```

The join uses exact transaction signatures first, then a wallet/token/time-window fallback. Joined rows remain `dune_quote_price_candidate_not_score_ready` until liquidity and market-cap evidence are complete.

Attach joined Dune context candidates to local forward rows without making them proof-ready:

```bash
python3 -m utils.build_dune_candidate_resolver_adapter \
  --dune-join data/reports/forward_testing/candidate_walk_forward/dune_candidate_join_20260526-dune-candidate-join-live-v4.json \
  --run-id 20260526-dune-resolver-adapter-live-v4
```

The resolver adapter preserves Dune quote and price candidates for manual review, but keeps every adapted row blocked until decision-time-safe liquidity and market-cap context are reconstructed. It does not change trust, wallet lists, scoring thresholds, recommendations, execution settings, or proof metrics.

Complete Dune candidate context with near-event forward market snapshots when price, liquidity, and market cap are all present inside the configured lag window:

```bash
python3 -m utils.build_dune_candidate_context_completion \
  --candidate-records data/reports/forward_testing/candidate_walk_forward/dune_candidate_context_candidate_records_20260526-dune-resolver-adapter-live-v4.jsonl \
  --market-snapshots data/wallet_backfills/forward_market_context_snapshots.jsonl \
  --max-snapshot-lag-seconds 120 \
  --run-id 20260526-dune-context-completion-live-v1
```

This completion layer is still candidate-only and review-only. It can identify context-complete candidate rows, but it cannot promote wallets, mutate trust, mutate wallet lists, change scoring thresholds, or unlock execution.

Pass context-complete Dune rows into the candidate walk-forward validator as a separate validation input:

```bash
python3 -m utils.build_candidate_walk_forward_validation \
  --dune-completed-records data/reports/forward_testing/candidate_walk_forward/dune_candidate_context_completed_records_20260526-dune-context-completion-live-v1.jsonl \
  --run-id 20260526-candidate-wfv-with-dune-context-defaults-v2
```

The validator reports Dune overlap separately with `dune_existing_event_matches` and `dune_new_event_appends` so historical context candidates are not mistaken for fresh forward evidence.

Stop broad batching when a batch captures zero usable snapshots or stops reducing isolated blocked records. At that point, switch to a smarter target-selection pass instead of spending more provider calls on low-yield current snapshots.

Captured snapshots can be passed into the isolated Helius quote-anchor merge with `--market-context`. This is still review-only; it does not overwrite canonical market context, resolver outputs, wallet trust, wallet lists, promotions, or execution settings.

## Safety Boundary

The system must remain paper-safe:

- no live trading
- no execution
- no auto-promotion
- no wallet trust mutation
- no wallet list mutation
- no edge/profitability claim
- no trusted-wallet claim
