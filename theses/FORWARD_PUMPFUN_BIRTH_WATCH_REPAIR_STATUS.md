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
