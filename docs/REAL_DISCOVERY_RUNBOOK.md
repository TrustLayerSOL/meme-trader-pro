# Real Discovery Runbook

## Purpose

Stage 16 adds bounded public-source candidate discovery so v3 can move beyond mock rows. The goal is to get real Solana token mints and pool/pair addresses into `CandidateRegistry` before spending Helius credits on historical evidence backfills.

## Mock vs Real Ingestors

The original DexScreener, Jupiter, and Raydium placeholder ingestors return deterministic mock data for tests. Real discovery lives in `dexscreener_real_ingest.py` and uses public DexScreener endpoints only when the discovery CLI is explicitly run.

Mock/manual candidates should not be used for scaled Helius backfills.

## Dry-Run DexScreener Discovery

```bash
./trading_env/bin/python -m research.mtp_research.ingestion.run_dexscreener_discovery --limit 10 --min-liquidity-usd 10000
```

Dry-run is the default and does not write to the registry.

## Write Real Candidates

```bash
./trading_env/bin/python -m research.mtp_research.ingestion.run_dexscreener_discovery --limit 10 --min-liquidity-usd 10000 --write
```

This writes real DexScreener-derived candidates to `data/normalized/candidate_registry.jsonl`.

## Inspect Candidate Quality

```bash
./trading_env/bin/python -m research.mtp_research.ingestion.run_candidate_quality_filter --exclude-mock --require-pool-address --min-liquidity-usd 10000
```

Use this before target planning. Candidates should have `token_mint`, `pool_address`, non-mock metadata, and enough liquidity for a useful bounded test.

## Plan Backfill Targets

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_plan_backfill_targets --candidate-limit 3 --require-pool-address --min-liquidity-usd 10000
```

Target planning excludes mock candidates by default.

## Tiny Helius Evidence Run

```bash
./trading_env/bin/python -m research.mtp_research.pipeline.run_evidence_backfill --candidate-limit 1 --require-pool-address --min-liquidity-usd 10000 --max-signatures-per-target 10 --max-transactions-per-target 10 --execute
```

Only run this after real candidate quality is confirmed.

## Safety Notes

- Public APIs only for discovery.
- No wallet signing.
- No live trading.
- No auto-buy or auto-sell.
- Helius is used only after candidate quality checks.
- Start with `--limit 10`.
- Start with `--min-liquidity-usd` to avoid low-quality noise.

## Recommended First Sequence

```bash
./trading_env/bin/python -m research.mtp_research.ingestion.run_dexscreener_discovery --limit 10 --min-liquidity-usd 10000
./trading_env/bin/python -m research.mtp_research.ingestion.run_dexscreener_discovery --limit 10 --min-liquidity-usd 10000 --write
./trading_env/bin/python -m research.mtp_research.ingestion.run_candidate_quality_filter --exclude-mock --require-pool-address --min-liquidity-usd 10000
./trading_env/bin/python -m research.mtp_research.pipeline.run_plan_backfill_targets --candidate-limit 3 --require-pool-address --min-liquidity-usd 10000
./trading_env/bin/python -m research.mtp_research.pipeline.run_evidence_backfill --candidate-limit 1 --require-pool-address --min-liquidity-usd 10000 --max-signatures-per-target 10 --max-transactions-per-target 10 --execute
```
