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
