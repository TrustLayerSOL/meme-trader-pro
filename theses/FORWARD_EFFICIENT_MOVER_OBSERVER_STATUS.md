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

`forward_observer_ready_for_dry_run`

Live observation requires a read-only live candidate source configuration. Mock and local JSONL sources are implemented for schema checks and deterministic tests.
