# Forward Pump.fun Birth Watch Repair Status

Status date: 2026-06-03

Guardrail: this is forward-observation source repair only. It is not paper trading, live trading, backtesting, validation, strategy generation, threshold optimization, or thesis promotion.

## Milestone Status

- Milestone: Pump.fun birth/pre-trigger freshness repair
- Completion: 100%
- Broad Helius collection run: no
- Network calls made by this repair: 0
- Source lane changed: Pump.fun create/birth watch only
- Normal FDV-trigger lane changed: no, still requires a non-quote mint and FDV proxy at or above the configured start trigger

## What Changed

- Pump.fun hydrated create transactions can now extract birth fields from the direct program instruction layout:
  - mint
  - bonding curve
  - associated bonding curve
  - creator
- Birth candidates remain opt-in through `--enable-birth-watch-candidates`.
- Birth-watch candidates can be persisted without an FDV proxy.
- Birth-watch rows are marked separately from active FDV-trigger candidates:
  - `freshness_lane= birth_watch`
  - `candidate_classification=pumpfun_birth_candidate_observed`
  - `status=watching_pre_trigger`
  - `trigger_timestamp=null`
  - `trigger_level=null`
- Missing FDV remains rejected by default for non-birth events.

## Why This Was Needed

The first-50 freshness audit showed that the current forward set did not prove birth/pre-trigger observation. Pump.fun create events were recognizable, but they were dropped because the mover observer required an FDV proxy before writing a candidate row.

## Next Action

Run a tiny bounded Pump.fun birth-watch smoke collection before scaling:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_forward_efficient_mover_observer \
  --mode observe \
  --source helius-pumpfun \
  --target-candidates 10 \
  --max-observe-iterations 5 \
  --max-helius-credits 100 \
  --enable-birth-watch-candidates
```

After the smoke run, audit whether created mints later receive FDV-trigger updates before resuming the larger forward collector.

## Smoke Results

Two smoke paths were checked after the source repair:

1. Generic forward observer Pump.fun program polling:
   - Result: `0` candidate rows
   - Helius request estimate: `30`
   - Raw normalized rows: `25`
   - Finding: recent generic Pump.fun program traffic was mostly trades below the `10k` FDV trigger, not launch-create events.

2. Pump.fun create scanner:
   - Signatures seen: `840`
   - Transactions hydrated: `840`
   - Direct Pump.fun instructions: `440`
   - Verified create candidates: `2`
   - Viability: `maybe_viable`
   - Helius request estimate: `860`
   - JSON report: `/Volumes/ORICO/MemeTraderPro/smoke_runs/pumpfun_create_scanner_20260603_larger/reports/pumpfun_create_scan_60559955c855.json`
   - Markdown report: `/Volumes/ORICO/MemeTraderPro/smoke_runs/pumpfun_create_scanner_20260603_larger/reports/pumpfun_create_scan_60559955c855.md`

## Updated Interpretation

- The generic forward observer is not the right primary source for birth discovery because it samples mixed program traffic.
- The Pump.fun create scanner is the correct source path for launch birth discovery.
- Create density in the recent Pump.fun signature stream is low enough that future birth collection should use the scanner/census path with pagination, not repeated generic observer polls.
- The next implementation step is to bridge verified create scanner output into a forward birth-watch queue, then observe those mints for first FDV-trigger updates.
