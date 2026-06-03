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

## Live Collection Start

The create-scanner bridge was implemented and started against the main ORICO forward observation root.

- Data root: `/Volumes/ORICO/MemeTraderPro`
- Observation root: `/Volumes/ORICO/MemeTraderPro/data/forward_observation/efficient_movers`
- Source mode: `helius-pumpfun-create-scanner`
- Birth-watch enabled: `true`
- Setup audit: passed
- Projected scanner requests per iteration: `1020`
- Helius cap used for the live-start command: `8000`, covering the existing checkpoint count plus the bounded scanner run
- Target candidates: `310`
- Total candidates observed: `310`
- Existing FDV-trigger candidates: `300`
- Pump.fun birth-watch candidates added: `10`
- Candidate/source row-family coverage: `10/10` birth-watch rows in candidates, paths, events, metadata, holders, and drawdowns
- Checkpoint Helius request estimate after run: `7479`
- Checkpoint warnings: `[]`
- Latest birth-watch mint: `334oqN1C3SsfNoWwZBf3TPT8482MhA8a5oG3uUYcpump`

Scanner reports saved under:

- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/forward_observation/efficient_movers/birth_watch_create_scanner/`

Most recent scanner reports:

- `pumpfun_create_scan_3c8e7971c001.json`: `7` verified creates, `947` signatures, `947` hydrated transactions, `967` estimated requests, viability `viable`
- `pumpfun_create_scan_df42b84571c0.json`: `6` verified creates, `905` signatures, `905` hydrated transactions, `925` estimated requests, viability `viable`

## Current State

- The birth-watch source bridge is working.
- Live collection has started and reached the first scanner-backed checkpoint.
- The active data root now contains a mixed forward set: `300` original FDV-trigger candidates plus `10` Pump.fun scanner birth-watch candidates.
- Next step is to monitor whether the 10 birth-watch mints later receive FDV-trigger/path updates, then decide whether to continue beyond `310`.

## Birth-to-Trigger Follow-up Audit and Collector

A read-only follow-up audit and bounded follow-up collector were added and run against the ORICO forward observation root.

- Data root: `/Volumes/ORICO/MemeTraderPro`
- Birth-watch candidates audited: `10`
- Unique birth-watch mints: `10`
- Follow-up collector execute pass: `true`
- Follow-up collector network calls: `92`
- Follow-up collector rows written: `290`
- Follow-up collector warnings: `[]`
- Birth-watch mints with later FDV evidence: `8`
- Birth-watch mints with any trigger crossing: `0`
- Follow-up status counts: `{'fdv_followup_below_trigger': 8, 'needs_followup_collection': 2}`
- Readiness classification: `birth_to_trigger_fdv_followup_below_trigger`
- Target trigger-qualified progress at `10k`: `0/300`
- Target trigger-qualified progress at `20k`: `0/300`
- Birth-to-FDV follow-up rate: `0.8`
- Birth-to-10k conversion rate: `0.0`
- Birth-to-20k conversion rate: `0.0`
- Network/Helius calls made by audit: `0`

Reports:

- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/forward_observation/efficient_movers/birth_to_trigger_followup_audit.json`
- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/forward_observation/efficient_movers/birth_to_trigger_followup_audit.md`
- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/forward_observation/efficient_movers/birth_to_trigger_followup_audit.csv`
- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/forward_observation/efficient_movers/birth_watch_followup_collector/birth_watch_followup_collection_summary.json`
- `/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/forward_observation/efficient_movers/birth_watch_followup_collector/birth_watch_followup_collection_summary.md`

Interpretation:

- The create-scanner bridge is producing birth-watch rows correctly.
- The bounded follow-up collector can recheck current birth-watch mints and append FDV/path rows without adding duplicate candidate rows.
- The first follow-up pass found deterministic FDV evidence for `8` of `10` birth-watch mints, but all observed FDV values remain below the `10k` trigger.
- Status reporting must keep two targets separate: birth inventory size and trigger-qualified birth-to-FDV sample size.
- The next useful checkpoint is a larger birth inventory, then repeated bounded follow-up passes to estimate the real birth-to-trigger conversion funnel.

## Parallel Scanner Scale-up Attempt

A larger scanner expansion was attempted with bounded parallel Helius transaction hydration.

- Data root: `/Volumes/ORICO/MemeTraderPro`
- Scanner source: `helius-pumpfun-create-scanner`
- Parallel hydration setting used: `HELIUS_TRANSACTION_WORKERS=16`
- Target total forward candidates: `800`
- Intended birth inventory checkpoint: about `500` birth-watch mints
- Final total forward candidates observed: `416`
- Final birth-watch mints observed: `116`
- Estimated Helius requests after scanner run: `26387`
- Scanner warnings: `[]`
- Duplicate mints after interrupted slow run repair: `0`
- Checkpoint repair note: `checkpoint_seen_mints_repaired_after_interrupted_birth_scan`

The scanner did not reach the `500` birth inventory checkpoint because the currently available Pump.fun program-signature window stopped returning enough new signatures/candidates before the target was reached. This is a live collection-rate/source-window limit, not a parser failure.

## Current Birth-to-Trigger Funnel

The follow-up collector was then run against the expanded birth-watch inventory.

- Follow-up selected mints: `108`
- Follow-up projected requests: `1188`
- Follow-up actual network calls: `1122`
- Follow-up rows written: `1925`
- Follow-up warnings: `[]`
- Birth-watch mints: `116`
- Births with deterministic FDV follow-up: `100`
- Crossed `10k`: `9`
- Crossed `15k`: `8`
- Crossed `20k`: `8`
- Crossed `30k`: `8`
- Crossed `50k`: `7`
- Crossed `100k`: `6`
- Crossed `500k`: `4`
- Crossed `1m`: `4`
- Birth-to-FDV follow-up rate: `0.862069`
- Birth-to-10k conversion rate: `0.077586`
- Birth-to-20k conversion rate: `0.068966`
- 10k-to-20k conversion rate: `0.888889`
- 20k-to-100k conversion rate: `0.75`
- Target trigger-qualified progress at `10k`: `9/300`
- Target trigger-qualified progress at `20k`: `8/300`
- Estimated births needed for `300` crossed-10k observations at the current rate: `3867`
- Estimated births needed for `300` crossed-20k observations at the current rate: `4350`

Current recommendation:

- Keep the two targets separate in every report: birth inventory and trigger-qualified observations.
- Continue live/new-signature birth collection over time instead of repeatedly rescanning an exhausted signature window.
- Run bounded follow-up after each new birth inventory batch.
- Do not run thesis tests or strategy analysis from this forward funnel yet; the trigger-qualified sample is still only `9/300` at `10k`.

## Signature-cache Scanner Scale-up

The scanner was updated to persist processed Pump.fun signatures in the forward checkpoint so future scanner runs can skip already-hydrated signatures.

- Commit: `23b72f6`
- Efficiency change: `birth_scan_processed_signatures` persisted in `/Volumes/ORICO/MemeTraderPro/data/forward_observation/efficient_movers/checkpoint.json`
- Parallel hydration setting used: `HELIUS_TRANSACTION_WORKERS=16`
- Final processed signature cache size: `87451`
- Final estimated Helius requests: `118787`
- Final scanner warnings: `[]`
- ORICO free space after run: about `351Gi`

Final current funnel after additional bounded scanner and follow-up passes:

- Total forward candidates: `768`
- Birth-watch mints: `468`
- Birth inventory checkpoint progress: `468/500`
- Births with deterministic FDV follow-up: `374`
- Crossed `10k`: `53`
- Crossed `15k`: `51`
- Crossed `20k`: `49`
- Crossed `30k`: `44`
- Crossed `50k`: `37`
- Crossed `100k`: `32`
- Crossed `200k`: `28`
- Crossed `500k`: `27`
- Crossed `1m`: `25`
- Birth-to-FDV follow-up rate: `0.799145`
- Birth-to-10k conversion rate: `0.113248`
- Birth-to-20k conversion rate: `0.104701`
- 10k-to-20k conversion rate: `0.924528`
- 20k-to-100k conversion rate: `0.653061`
- Target trigger-qualified progress at `10k`: `53/300`
- Target trigger-qualified progress at `20k`: `49/300`
- Estimated births needed for `300` crossed-10k observations at the current rate: `2650`
- Estimated births needed for `300` crossed-20k observations at the current rate: `2866`

The run stopped just short of the first `500` birth inventory checkpoint. The remaining gap was `32` birth-watch mints.

## First 500-Birth Checkpoint

A final bounded scanner top-off and follow-up pass reached the first birth inventory checkpoint.

- Total forward candidates: `800`
- Birth-watch mints: `500`
- Birth inventory checkpoint progress: `500/500`
- Births with deterministic FDV follow-up: `404`
- Births still needing follow-up: `96`
- Crossed `10k`: `53`
- Crossed `15k`: `51`
- Crossed `20k`: `49`
- Crossed `30k`: `44`
- Crossed `50k`: `37`
- Crossed `100k`: `32`
- Crossed `200k`: `28`
- Crossed `500k`: `27`
- Crossed `1m`: `25`
- Birth-to-FDV follow-up rate: `0.808`
- Birth-to-10k conversion rate: `0.106`
- Birth-to-20k conversion rate: `0.098`
- 10k-to-20k conversion rate: `0.924528`
- 20k-to-100k conversion rate: `0.653061`
- Target trigger-qualified progress at `10k`: `53/300`
- Target trigger-qualified progress at `20k`: `49/300`
- Estimated births needed for `300` crossed-10k observations at the current rate: `2831`
- Estimated births needed for `300` crossed-20k observations at the current rate: `3062`
- Final estimated Helius requests: `126726`
- Final processed signature cache size: `94932`
- Final warnings: `[]`

The birth observation infrastructure is working and the first inventory checkpoint is complete. The trigger-qualified sample remains too small for thesis testing or strategy conclusions.
