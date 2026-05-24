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

## Safety Boundary

The system must remain paper-safe:

- no live trading
- no execution
- no auto-promotion
- no wallet trust mutation
- no wallet list mutation
- no edge/profitability claim
- no trusted-wallet claim
