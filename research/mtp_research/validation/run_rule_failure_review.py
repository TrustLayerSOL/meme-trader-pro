"""CLI for Stage 25 rule failure anatomy review."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from research.mtp_research.pipeline.real_candidate_filter import real_token_mints_from_registry
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.rule_failure_analyzer import RuleFailureAnalyzer
from research.mtp_research.validation.rule_failure_report import (
    write_review_json,
    write_review_markdown,
)
from research.mtp_research.validation.walk_forward_store import WalkForwardValidationStore


def main() -> int:
    args = parse_args()
    rows = ResearchDatasetStore(args.dataset_path).load_all()
    if args.real_only:
        real_mints = real_token_mints_from_registry(min_liquidity_usd=args.min_liquidity_usd)
        rows = [row for row in rows if row.token_mint in real_mints]
    results = WalkForwardValidationStore(args.walk_forward_store_path).load_all()
    if not results:
        raise SystemExit(f"No walk-forward results found at {args.walk_forward_store_path}")
    result = sorted(results, key=lambda item: item.created_at)[-1]
    review = RuleFailureAnalyzer().build_review(
        rows,
        result,
        dataset_path=args.dataset_path,
        walk_forward_path=args.walk_forward_store_path,
    )
    output_dir = Path(args.output_dir)
    markdown_path = write_review_markdown(review, output_dir / f"{review.review_id}.md")
    json_path = write_review_json(review, output_dir / f"{review.review_id}.json")
    top_causes = {
        anatomy.rule_id: anatomy.likely_failure_causes
        for anatomy in review.rule_anatomies
    }
    cause_counts = Counter(cause for anatomy in review.rule_anatomies for cause in anatomy.likely_failure_causes)

    print(f"row_count={review.row_count}")
    print(f"token_count={review.token_count}")
    print(f"time_span_seconds={review.time_span_seconds}")
    print(f"nearest_fallback_row_count={review.nearest_fallback_row_count}")
    print(f"recommended_next_action={review.recommended_next_action}")
    print(f"evidence_scale_recommendation={review.evidence_scale_recommendation}")
    print(f"rule_review_recommendation={review.rule_review_recommendation}")
    print(f"top_failure_causes_by_rule={top_causes}")
    print(f"failure_cause_counts={dict(sorted(cause_counts.items()))}")
    print(f"markdown_path={markdown_path}")
    print(f"json_path={json_path}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build rule failure anatomy review.")
    parser.add_argument("--dataset-path", default="data/backtests/diagnostics/research_dataset_nearest300.jsonl")
    parser.add_argument("--walk-forward-store-path", default="data/backtests/diagnostics/walk_forward_best_diagnostic.jsonl")
    parser.add_argument("--output-dir", default="data/backtests/diagnostics/reports")
    parser.add_argument("--real-only", action="store_true")
    parser.add_argument("--min-liquidity-usd", type=float)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
