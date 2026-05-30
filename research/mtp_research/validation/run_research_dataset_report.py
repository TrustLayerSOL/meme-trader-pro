"""CLI for summarizing research dataset rows."""

from __future__ import annotations

import argparse

from research.mtp_research.validation.research_dataset_builder import ResearchDatasetBuilder
from research.mtp_research.validation.research_dataset_report import summarize_rows
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize v0 research dataset rows.")
    parser.add_argument("--dataset-path")
    parser.add_argument("--token-mint")
    parser.add_argument("--window-name")
    parser.add_argument("--horizon-name")
    parser.add_argument("--min-label-quality")
    parser.add_argument("--require-forward-return", action="store_true")
    args = parser.parse_args()

    rows = ResearchDatasetStore(path=args.dataset_path).load_all() if args.dataset_path else ResearchDatasetStore().load_all()
    rows = ResearchDatasetBuilder().filter_rows(
        rows,
        token_mints=[args.token_mint] if args.token_mint else None,
        window_names=[args.window_name] if args.window_name else None,
        horizon_names=[args.horizon_name] if args.horizon_name else None,
        min_label_quality=args.min_label_quality,
        require_forward_return=args.require_forward_return,
    )
    summary = summarize_rows(rows)

    print(f"row_count={summary['row_count']}")
    print(f"token_count={summary['token_count']}")
    print(f"horizon_counts={summary['horizon_counts']}")
    print(f"window_counts={summary['window_counts']}")
    print(f"label_quality_counts={summary['label_quality_counts']}")
    print(f"avg_forward_return={summary['avg_forward_return']}")
    print(f"median_forward_return={summary['median_forward_return']}")
    print(f"positive_forward_return_count={summary['positive_forward_return_count']}")
    print(f"negative_forward_return_count={summary['negative_forward_return_count']}")
    print(f"rug_like_drop_count={summary['rug_like_drop_count']}")
    print(f"no_future_liquidity_count={summary['no_future_liquidity_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
