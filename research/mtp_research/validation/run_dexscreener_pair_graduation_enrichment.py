"""CLI for DexScreener pair-detection graduation enrichment."""

from __future__ import annotations

import argparse

from research.mtp_research.validation.dexscreener_pair_graduation_enrichment import (
    DEFAULT_CANDIDATES_PATH,
    DEFAULT_JSONL_PATH,
    DEFAULT_PARQUET_PATH,
    DEFAULT_REPORT_DIR,
    run_dexscreener_pair_graduation_enrichment,
)


def main() -> int:
    args = parse_args()
    result = run_dexscreener_pair_graduation_enrichment(
        candidates_path=args.candidates_path,
        mint_limit=args.mint_limit,
        batch_size=args.batch_size,
        request_ceiling=args.request_ceiling,
        execute=args.execute,
        output_paths={
            "jsonl_path": args.jsonl_path,
            "parquet_path": args.parquet_path,
            "report_dir": args.report_dir,
        },
    )
    collection = result.get("collection", {})
    print(f"report_id={result['report_id']}")
    print(f"mode={result['execution']['mode']}")
    print(f"readiness_classification={result['readiness_classification']}")
    print(f"selected_mints={result['scope']['selected_mints']}")
    print(f"projected_requests={result['requests']['projected_requests']}")
    print(f"requests_used={result['requests']['requests_used']}")
    print(f"dex_pair_detected_count={collection.get('dex_pair_detected_count', 0)}")
    print(f"liquidity_pool_created_after_launch_count={collection.get('liquidity_pool_created_after_launch_count', 0)}")
    print(f"unique_pair_mints_detected={collection.get('unique_pair_mints_detected', 0)}")
    print(f"dex_counts={collection.get('dex_counts', {})}")
    print(f"warnings={result.get('warnings', [])}")
    print(f"jsonl_path={result['outputs']['jsonl_path']}")
    print(f"parquet_path={result['outputs']['parquet_path']}")
    print(f"summary_json={result['outputs']['report_dir']}/dexscreener_pair_graduation_enrichment.json")
    print(f"summary_md={result['outputs']['report_dir']}/dexscreener_pair_graduation_enrichment.md")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run DexScreener pair-detection graduation enrichment.")
    parser.add_argument("--candidates-path", default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument("--mint-limit", type=int, default=3000)
    parser.add_argument("--batch-size", type=int, default=30)
    parser.add_argument("--request-ceiling", type=int, default=150)
    parser.add_argument("--jsonl-path", default=DEFAULT_JSONL_PATH)
    parser.add_argument("--parquet-path", default=DEFAULT_PARQUET_PATH)
    parser.add_argument("--report-dir", default=DEFAULT_REPORT_DIR)
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
