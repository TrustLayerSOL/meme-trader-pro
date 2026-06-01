"""CLI for planning bounded evidence expansion from sample adequacy gaps."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.pipeline.sample_adequacy_expansion_planner import (
    SampleAdequacyExpansionPlanner,
)
from research.mtp_research.pipeline.sample_adequacy_expansion_report import (
    write_expansion_plan_json,
    write_expansion_plan_markdown,
)


def main() -> int:
    args = parse_args()
    planner = SampleAdequacyExpansionPlanner(
        min_real_token_count=args.min_real_token_count,
        min_time_span_seconds=args.min_time_span_seconds,
        min_valid_test_folds=args.min_valid_test_folds,
        min_total_test_selected_count=args.min_total_test_selected_count,
        min_independent_batches=args.min_independent_batches,
    )
    plan = planner.build_plan(
        registry_path=args.registry_path,
        dataset_path=args.dataset_path,
        walk_forward_store_path=args.walk_forward_store_path,
        candidate_limit=args.candidate_limit,
        min_liquidity_usd=args.min_liquidity_usd,
        recommended_signature_limit=args.recommended_signature_limit,
        recommended_transaction_limit=args.recommended_transaction_limit,
        raw_store_path=args.raw_store_path,
        event_store_path=args.event_store_path,
        feature_store_path=args.feature_store_path,
        outcome_store_path=args.outcome_store_path,
    )
    output_dir = Path(args.output_dir)
    markdown_path = write_expansion_plan_markdown(plan, output_dir / f"{plan.plan_id}.md")
    json_path = write_expansion_plan_json(plan, output_dir / f"{plan.plan_id}.json")
    print(f"sample_adequate={plan.sample_adequate}")
    print(f"real_token_count={plan.sample_adequacy.real_token_count}")
    print(f"time_span_seconds={plan.sample_adequacy.time_span_seconds}")
    print(f"valid_test_fold_count={plan.sample_adequacy.valid_test_fold_count}")
    print(f"total_test_selected_count={plan.sample_adequacy.total_test_selected_count}")
    print(f"token_shortfall={plan.token_shortfall}")
    print(f"time_span_shortfall_seconds={plan.time_span_shortfall_seconds}")
    print(f"selected_count_shortfall={plan.selected_count_shortfall}")
    print(f"plan_item_count={len(plan.time_span_plan.plan_items)}")
    print(f"estimated_signature_requests={plan.time_span_plan.estimated_signature_requests}")
    print(f"estimated_transaction_requests={plan.time_span_plan.estimated_transaction_requests}")
    print(f"recommended_next_action={plan.recommended_next_action}")
    print(f"recommended_bounded_command={plan.recommended_bounded_command}")
    print(f"markdown_path={markdown_path}")
    print(f"json_path={json_path}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan bounded evidence expansion.")
    parser.add_argument("--registry-path")
    parser.add_argument("--dataset-path", default="data/backtests/diagnostics/research_dataset_nearest300.jsonl")
    parser.add_argument("--walk-forward-store-path", default="data/backtests/diagnostics/walk_forward_best_diagnostic.jsonl")
    parser.add_argument("--raw-store-path", default=None)
    parser.add_argument("--event-store-path", default=None)
    parser.add_argument("--feature-store-path", default=None)
    parser.add_argument("--outcome-store-path", default=None)
    parser.add_argument("--output-dir", default="data/backtests/diagnostics/reports")
    parser.add_argument("--candidate-limit", type=int, default=10)
    parser.add_argument("--min-liquidity-usd", type=float, default=10_000)
    parser.add_argument("--recommended-signature-limit", type=int, default=75)
    parser.add_argument("--recommended-transaction-limit", type=int, default=75)
    parser.add_argument("--min-real-token-count", type=int, default=10)
    parser.add_argument("--min-time-span-seconds", type=int, default=43_200)
    parser.add_argument("--min-valid-test-folds", type=int, default=10)
    parser.add_argument("--min-total-test-selected-count", type=int, default=100)
    parser.add_argument("--min-independent-batches", type=int, default=1)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
