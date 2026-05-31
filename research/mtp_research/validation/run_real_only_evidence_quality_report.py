"""CLI for real-only clean/fallback evidence quality comparison."""

from __future__ import annotations

import argparse

from research.mtp_research.pipeline.real_candidate_filter import real_token_mints_from_registry
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize real-only clean and diagnostic fallback dataset quality.")
    parser.add_argument("--registry-path", default="data/normalized/candidate_registry.jsonl")
    parser.add_argument("--clean-dataset-path", default="data/backtests/research_dataset.jsonl")
    parser.add_argument("--fallback-dataset-path", default="data/backtests/diagnostics/research_dataset_nearest300.jsonl")
    parser.add_argument("--min-liquidity-usd", type=float)
    args = parser.parse_args()

    real_mints = real_token_mints_from_registry(
        args.registry_path,
        min_liquidity_usd=args.min_liquidity_usd,
    )
    clean_rows = _real_rows(ResearchDatasetStore(args.clean_dataset_path).load_all(), real_mints)
    fallback_rows = _real_rows(ResearchDatasetStore(args.fallback_dataset_path).load_all(), real_mints)
    nearest_fallback_count = sum(1 for row in fallback_rows if row.entry_price_source == "nearest_research_fallback")
    recommendation = _recommend(clean_rows, fallback_rows, nearest_fallback_count)

    print(f"real_only_clean_rows={len(clean_rows)}")
    print(f"real_only_fallback_rows={len(fallback_rows)}")
    print(f"clean_rows_with_forward_return={sum(1 for row in clean_rows if row.forward_return is not None)}")
    print(f"fallback_rows_with_forward_return={sum(1 for row in fallback_rows if row.forward_return is not None)}")
    print(f"clean_sparse_or_better_rows={_sparse_or_better(clean_rows)}")
    print(f"fallback_sparse_or_better_rows={_sparse_or_better(fallback_rows)}")
    print(f"nearest_fallback_row_count={nearest_fallback_count}")
    print(f"recommendation={recommendation}")
    print("network_calls=0")
    return 0


def _real_rows(rows: list[ResearchDatasetRow], real_mints: set[str]) -> list[ResearchDatasetRow]:
    return [row for row in rows if row.token_mint in real_mints]


def _sparse_or_better(rows: list[ResearchDatasetRow]) -> int:
    return sum(1 for row in rows if row.label_quality in {"sparse", "good"})


def _recommend(
    clean_rows: list[ResearchDatasetRow],
    fallback_rows: list[ResearchDatasetRow],
    nearest_fallback_count: int,
) -> str:
    clean_forward = sum(1 for row in clean_rows if row.forward_return is not None)
    fallback_forward = sum(1 for row in fallback_rows if row.forward_return is not None)
    if fallback_forward >= clean_forward and nearest_fallback_count:
        return "accept fallback for research-only diagnostics"
    if fallback_forward == clean_forward:
        return "improve price inference"
    return "scale backfill only if coverage is adequate"


if __name__ == "__main__":
    raise SystemExit(main())
