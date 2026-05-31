"""CLI for bounded real DexScreener candidate discovery."""

from __future__ import annotations

import argparse

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.dexscreener_real_ingest import DexScreenerRealIngestor
from research.mtp_research.ingestion.discovery_models import DiscoveryRunConfig


def main() -> int:
    parser = argparse.ArgumentParser(description="Run bounded real DexScreener discovery.")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--profiles", action="store_true")
    parser.add_argument("--boosts", action="store_true")
    parser.add_argument("--top-boosts", action="store_true")
    parser.add_argument("--no-pair-enrichment", action="store_true")
    parser.add_argument("--min-liquidity-usd", type=float)
    parser.add_argument("--registry-path")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    selected_sources = args.profiles or args.boosts or args.top_boosts
    config = DiscoveryRunConfig(
        source="dexscreener_real",
        limit=args.limit,
        dry_run=args.dry_run or not args.write,
        write=args.write,
        include_profiles=args.profiles if selected_sources else True,
        include_boosts=args.boosts if selected_sources else True,
        include_top_boosts=args.top_boosts if selected_sources else True,
        enrich_pairs=not args.no_pair_enrichment,
        min_liquidity_usd=args.min_liquidity_usd,
    )
    registry = CandidateRegistry(args.registry_path) if args.registry_path else CandidateRegistry()
    summary = DexScreenerRealIngestor().run_discovery(config, registry=registry)

    print(f"raw_items_seen={summary.raw_items_seen}")
    print(f"solana_items_seen={summary.solana_items_seen}")
    print(f"token_addresses_seen={summary.token_addresses_seen}")
    print(f"pair_records_seen={summary.pair_records_seen}")
    print(f"candidates_built={summary.candidates_built}")
    print(f"candidates_after_filters={summary.candidates_after_filters}")
    print(f"candidates_inserted={summary.candidates_inserted}")
    print(f"candidates_updated={summary.candidates_updated}")
    print(f"warning_flags={summary.warning_flags}")
    for candidate in summary.metadata_json.get("candidate_summaries", [])[:5]:
        print(
            "candidate "
            f"token_mint={candidate.get('token_mint')} "
            f"venue={candidate.get('venue')} "
            f"pool_address={candidate.get('pool_address')} "
            f"liquidity_usd={candidate.get('liquidity_usd')} "
            f"dexscreener_url={candidate.get('dexscreener_url')}"
        )
    print("helius_calls=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
