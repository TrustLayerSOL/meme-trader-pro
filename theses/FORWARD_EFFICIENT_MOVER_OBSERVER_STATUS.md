# Forward Efficient Mover Observer Status

This observer was created to collect forward, high-resolution data for tokens that enter the high-FDV-efficiency / efficient-mover candidate universe.

It is observation-only. It does not create paper trades, live trades, wallet execution, order routing, alerts, buy rules, sell rules, validation, backtests, optimization, or strategy logic.

## What It Watches

- Read-only candidate sources that can surface tokens crossing fixed FDV/valuation-proxy levels.
- Fixed trigger levels: 10k, 15k, 20k, and 30k FDV proxy.
- Candidate classification: `efficient_mover_candidate_observed`.

## What It Logs

- Candidate identity and source metadata.
- Trigger and FDV/valuation-proxy path rows.
- Wallet/flow rows when the source provides them.
- Metadata snapshots.
- Holder/top-holder snapshots when the source provides them.
- Drawdown state snapshots.
- Checkpoint and status files.

## Storage Paths

- Observation root: `/Volumes/ORICO/MemeTraderPro/data/forward_observation/efficient_movers/`
- Raw root: `/Volumes/ORICO/MemeTraderPro/data/raw/forward_observation/efficient_movers/`
- Reports root: `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/forward_observation/efficient_movers/`

## Commands

Dry run:

```bash
MEMETRADER_DATA_ROOT=/Volumes/ORICO/MemeTraderPro ./trading_env/bin/python -m research.mtp_research.validation.run_forward_efficient_mover_observer --mode dry-run
```

Observe with a configured source:

```bash
MEMETRADER_DATA_ROOT=/Volumes/ORICO/MemeTraderPro ./trading_env/bin/python -m research.mtp_research.validation.run_forward_efficient_mover_observer --mode observe --target-candidates 300 --poll-seconds 2 --max-runtime-minutes 240
```

Status:

```bash
MEMETRADER_DATA_ROOT=/Volumes/ORICO/MemeTraderPro ./trading_env/bin/python -m research.mtp_research.validation.run_forward_efficient_mover_observer --mode status
```

## Target Sample Sizes

- 50 candidates: sanity check.
- 100 candidates: early pattern review.
- 300 candidates: meaningful review.
- 500 candidates: stronger review.

## Current Readiness Classification

`forward_observer_ready_for_observation`

Helius RPC and WebSocket endpoint resolution are wired through the existing `HELIUS_API_KEY`/Helius URL configuration, with endpoint masking in reports.

Current live source state:

- Helius RPC health: ready in the latest live-readiness check.
- Helius WS connectivity: ready in the latest live-readiness check.
- Pump.fun adapter: ready for bounded read-only signature polling.
- PumpSwap adapter: present but marked `needs_probe_verification`.
- Raydium adapter: present but marked `needs_probe_verification`.
- DexScreener metadata: disabled by default; secondary enrichment only.

The live layer now hydrates bounded Pump.fun transactions, extracts mint/side/token/SOL deltas, applies local SOL/USD valuation conversion when available, and writes efficient-mover candidate rows only after fixed trigger levels are crossed.

Latest bounded smoke result:

- Target: `3`
- Candidates observed: `4`
- Raw Helius RPC rows: `40`
- Helius request-equivalent credits used: `43`
- Reached 20k: `1`
- Reached 50k: `1`
- Reached 100k: `1`
- Reached 500k: `1`
- Reached 1m: `1`
- Stop/review flag: `target_reached_review_before_continuing`

Current implementation completion: Pump.fun Helius forward observation is live and writing ORICO candidate/path/event/metadata/holder/drawdown rows. PumpSwap and Raydium remain present but unverified until their source semantics are confirmed with tiny probes.
