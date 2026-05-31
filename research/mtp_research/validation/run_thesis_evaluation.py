"""CLI for evaluating research thesis status from walk-forward results."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from research.mtp_research.validation.thesis_decision_store import ThesisDecisionStore
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.sample_adequacy import SampleAdequacyAnalyzer
from research.mtp_research.validation.thesis_evaluator import ThesisEvaluator
from research.mtp_research.validation.thesis_registry import ThesisRegistry
from research.mtp_research.validation.thesis_report import (
    write_thesis_evaluation_json,
    write_thesis_evaluation_markdown,
)
from research.mtp_research.validation.walk_forward_store import WalkForwardValidationStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate MemeTraderPro v3 theses.")
    parser.add_argument("--theses-dir", default="theses")
    parser.add_argument("--walk-forward-store-path", default="data/backtests/walk_forward_results.jsonl")
    parser.add_argument("--decision-store-path", default="data/backtests/thesis_decisions.jsonl")
    parser.add_argument("--output-dir", default="data/backtests/reports")
    parser.add_argument("--min-total-test-selected-count", type=int, default=50)
    parser.add_argument("--min-positive-test-fold-rate", type=float, default=0.6)
    parser.add_argument("--min-avg-test-net-return", type=float, default=0.0)
    parser.add_argument("--min-consistency-score", type=float, default=0.0)
    parser.add_argument("--sample-adequacy-dataset-path")
    parser.add_argument("--sample-min-real-token-count", type=int, default=10)
    parser.add_argument("--sample-min-time-span-seconds", type=int, default=43_200)
    parser.add_argument("--sample-min-valid-test-folds", type=int, default=10)
    parser.add_argument("--sample-min-total-test-selected-count", type=int, default=100)
    parser.add_argument("--sample-min-independent-batches", type=int, default=1)
    args = parser.parse_args()

    registry = ThesisRegistry(args.theses_dir)
    theses = registry.load_theses()
    validation_results = WalkForwardValidationStore(args.walk_forward_store_path).load_all()
    sample_adequacy_report = None
    if args.sample_adequacy_dataset_path:
        sample_rows = ResearchDatasetStore(args.sample_adequacy_dataset_path).load_all()
        sample_adequacy_report = SampleAdequacyAnalyzer(
            min_real_token_count=args.sample_min_real_token_count,
            min_time_span_seconds=args.sample_min_time_span_seconds,
            min_valid_test_folds=args.sample_min_valid_test_folds,
            min_total_test_selected_count=args.sample_min_total_test_selected_count,
            min_independent_batches=args.sample_min_independent_batches,
        ).build_report(sample_rows, validation_results)
    evaluator = ThesisEvaluator(
        min_total_test_selected_count=args.min_total_test_selected_count,
        min_positive_test_fold_rate=args.min_positive_test_fold_rate,
        min_avg_test_net_return=args.min_avg_test_net_return,
        min_consistency_score=args.min_consistency_score,
        sample_adequacy_report=sample_adequacy_report,
    )
    summaries = evaluator.evaluate_all(theses, validation_results)
    decisions = [
        evaluator.summary_to_decision(thesis, summary)
        for thesis, summary in zip(theses, summaries)
    ]
    decision_store = ThesisDecisionStore(args.decision_store_path)
    decision_store.upsert_many(decisions)
    output_dir = Path(args.output_dir)
    markdown_path = write_thesis_evaluation_markdown(
        summaries,
        decisions,
        output_dir / "thesis_evaluation_report.md",
    )
    json_path = write_thesis_evaluation_json(
        summaries,
        decisions,
        output_dir / "thesis_evaluation_report.json",
    )
    status_counts = Counter(summary.recommended_status for summary in summaries)
    warning_flags = sorted({flag for summary in summaries for flag in summary.warning_flags})
    print(f"theses_loaded={len(theses)}")
    print(f"validation_results_loaded={len(validation_results)}")
    print(f"decisions_generated={len(decisions)}")
    print(f"recommended_status_counts={dict(sorted(status_counts.items()))}")
    print(f"markdown_report_path={markdown_path}")
    print(f"json_report_path={json_path}")
    print(f"decision_store_path={decision_store.path}")
    print(f"warning_flags={warning_flags}")
    if sample_adequacy_report:
        print(f"sample_adequacy_recommended_data_expansion={sample_adequacy_report.recommended_data_expansion}")
        print(f"sample_adequacy_adequate_for_rejection={sample_adequacy_report.adequate_for_rejection}")
        print(f"sample_adequacy_adequate_for_promotion={sample_adequacy_report.adequate_for_promotion}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
