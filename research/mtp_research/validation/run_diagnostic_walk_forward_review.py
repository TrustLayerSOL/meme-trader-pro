"""CLI for diagnostic-only walk-forward review."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.pipeline.real_candidate_filter import real_token_mints_from_registry
from research.mtp_research.validation.diagnostic_walk_forward_report import (
    write_review_json,
    write_review_markdown,
)
from research.mtp_research.validation.diagnostic_walk_forward_review import (
    DiagnosticWalkForwardReviewer,
)
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.walk_forward_store import WalkForwardValidationStore


def main() -> int:
    args = parse_args()
    dataset_rows = ResearchDatasetStore(args.dataset_path).load_all()
    if args.real_only:
        real_mints = real_token_mints_from_registry(min_liquidity_usd=args.min_liquidity_usd)
        dataset_rows = [row for row in dataset_rows if row.token_mint in real_mints]
    validation_results = WalkForwardValidationStore(args.walk_forward_store_path).load_all()
    if not validation_results:
        raise SystemExit(f"No diagnostic walk-forward results found at {args.walk_forward_store_path}")
    validation_result = sorted(validation_results, key=lambda item: item.created_at)[-1]
    review = DiagnosticWalkForwardReviewer().build_review(
        dataset_rows=dataset_rows,
        validation_result=validation_result,
        dataset_path=args.dataset_path,
        result_path=args.walk_forward_store_path,
    )
    output_dir = Path(args.output_dir)
    markdown_path = write_review_markdown(review, output_dir / f"{review.review_id}.md")
    json_path = write_review_json(review, output_dir / f"{review.review_id}.json")

    print(f"row_count={review.row_count}")
    print(f"token_count={review.token_count}")
    print(f"time_span_seconds={review.time_span_seconds}")
    print(f"nearest_fallback_row_count={review.nearest_fallback_row_count}")
    print(f"rules_with_valid_folds={review.rules_with_valid_folds}")
    print(f"best_rule_by_consistency={review.best_rule_by_consistency}")
    print(f"best_rule_by_avg_test_net={review.best_rule_by_avg_test_net}")
    print(f"recommended_next_action={review.recommended_next_action}")
    print(f"markdown_path={markdown_path}")
    print(f"json_path={json_path}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build diagnostic walk-forward review.")
    parser.add_argument("--dataset-path", default="data/backtests/diagnostics/research_dataset_nearest300.jsonl")
    parser.add_argument("--walk-forward-store-path", default="data/backtests/diagnostics/walk_forward_best_diagnostic.jsonl")
    parser.add_argument("--output-dir", default="data/backtests/diagnostics/reports")
    parser.add_argument("--real-only", action="store_true")
    parser.add_argument("--min-liquidity-usd", type=float)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
