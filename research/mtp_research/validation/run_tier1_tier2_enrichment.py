"""CLI for Tier 1 / Tier 2 structural enrichment."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.tier1_tier2_enrichment import (
    DEFAULT_ENTITY_PROXY_PATH,
    DEFAULT_EVENTS_PATH,
    DEFAULT_HOLDER_STATE_PATH,
    DEFAULT_MASTER_PATH,
    DEFAULT_METADATA_QUALITY_PATH,
    DEFAULT_TOPICALITY_PATH,
    DEFAULT_VISIBILITY_PATH,
    run_tier1_tier2_enrichment,
)


def main() -> int:
    args = parse_args()
    input_paths = {
        "master": Path(args.master_path),
        "events": Path(args.events_path),
        "holder_state": Path(args.holder_state_path),
        "entity_proxy": Path(args.entity_proxy_path),
        "visibility": Path(args.visibility_path),
        "metadata_quality": Path(args.metadata_quality_path),
        "topicality": Path(args.topicality_path),
    }
    output_paths = {"status_path": Path(args.status_path)} if args.status_path else None
    report, paths = run_tier1_tier2_enrichment(
        data_root=Path(args.data_root) if args.data_root else None,
        input_paths=input_paths,
        output_paths=output_paths,
        max_helius_credits=args.max_helius_credits,
        execute=args.execute,
    )
    print(f"report_id={report['report_id']}")
    print(f"readiness_classification={report['readiness_classification']}")
    print(f"execute={args.execute}")
    print(f"launches_enriched={report.get('launches_enriched', 0)}")
    print(f"projected_helius_credits={report['budget']['projected_helius_credits']}")
    print(f"helius_requests_used={report['helius']['requests_used']}")
    print(f"helius_credits_used={report['helius']['credits_used']}")
    print(f"dexscreener_calls_used={report['dexscreener']['calls_used']}")
    print(f"warnings={report.get('warnings', [])}")
    print(f"master_parquet_path={paths['master_parquet_path']}")
    print(f"master_jsonl_path={paths['master_jsonl_path']}")
    print(f"coverage_json_path={paths['coverage_json_path']}")
    print(f"coverage_markdown_path={paths['coverage_markdown_path']}")
    print(f"status_path={paths['status_path']}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Tier 1 / Tier 2 structural enrichment.")
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--master-path", default=DEFAULT_MASTER_PATH)
    parser.add_argument("--events-path", default=DEFAULT_EVENTS_PATH)
    parser.add_argument("--holder-state-path", default=DEFAULT_HOLDER_STATE_PATH)
    parser.add_argument("--entity-proxy-path", default=DEFAULT_ENTITY_PROXY_PATH)
    parser.add_argument("--visibility-path", default=DEFAULT_VISIBILITY_PATH)
    parser.add_argument("--metadata-quality-path", default=DEFAULT_METADATA_QUALITY_PATH)
    parser.add_argument("--topicality-path", default=DEFAULT_TOPICALITY_PATH)
    parser.add_argument("--status-path", default=None)
    parser.add_argument("--max-helius-credits", type=int, default=500_000)
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
