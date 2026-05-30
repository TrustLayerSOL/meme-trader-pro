# MemeTraderPro v3 (Research-First)

MemeTraderPro v3 is a research-first Solana meme coin trading intelligence project.

## Structure

- `legacy/v2/` — preserved current v2 prototype
- `legacy/v1/` — placeholder for historical v1 code if found later
- `docs/` — strategy, data, validation, and risk documentation
- `configs/` — strategy, venue, fees, and risk presets
- `research/mtp_research/` — research pipeline modules and backtesting scaffold
- `trader/` — v3 execution surface and adapter scaffolding
- `shared/` — shared schema artifacts
- `data/` — managed datasets for new v3 workflows

## Principles

v3 is not a live trading bot yet.

Initial focus is historical backtesting and step-forward validation under strict research controls.

Primary MVP strategy is post-launch momentum with quality/risk filters.

Secondary future strategies (not started):

- post-flush mean reversion
- migration/graduation event trading

Avoid for MVP:

- pure first-block sniping
- generalized copy trading
- MEV/bundle racing

## Milestone 2: Candidate Registry

Research discovery is now backed by a v3 candidate registry:

- `LaunchCandidate` model in `research/mtp_research/ingestion/models.py`
- JSONL persistence in `data/normalized/candidate_registry.jsonl`
- Upsert-by-mint merge semantics (earliest first-seen + merged metadata)

Run candidate ingestion and registry update:

```bash
./trading_env/bin/python -m research.mtp_research.ingestion.run_candidate_registry
```

Fallback (if virtualenv path differs):

```bash
python3 -m research.mtp_research.ingestion.run_candidate_registry
```

Run the focused registry tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_candidate_registry.py
```

Fallback (if virtualenv path differs):

```bash
python3 -m pytest research/tests/test_candidate_registry.py
```

## Milestone 3: Helius Historical Adapter Foundation

v3 now has a low-cost Helius JSON-RPC adapter foundation for historical signature discovery. The first supported method is `getSignaturesForAddress`; full transaction-body hydration comes later.

Run the focused Helius adapter tests:

```bash
./trading_env/bin/python -m pytest research/tests/test_helius_backfill.py
```

Example real probe command:

```bash
./trading_env/bin/python -m research.mtp_research.ingestion.run_helius_backfill_probe <ADDRESS> --limit 10
```
