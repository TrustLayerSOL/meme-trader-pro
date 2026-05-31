"""Run diagnostic validation stack against nearest-entry fallback data."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from research.mtp_research.backtest.rule_backtest_models import (
    CostAssumptions,
    RuleBacktestConfig,
)
from research.mtp_research.backtest.rule_backtest_report import (
    write_multi_result_markdown,
    write_result_json as write_rule_result_json,
    write_result_markdown as write_rule_result_markdown,
)
from research.mtp_research.backtest.rule_backtest_store import RuleBacktestStore
from research.mtp_research.backtest.rule_backtester import RuleBacktester
from research.mtp_research.backtest.rule_library import default_rule_library
from research.mtp_research.validation.baseline_edge_analyzer import BaselineEdgeAnalyzer
from research.mtp_research.validation.baseline_report_writer import (
    write_report_json as write_baseline_json,
    write_report_markdown as write_baseline_markdown,
)
from research.mtp_research.validation.diagnostic_validation_models import DIAGNOSTIC_FALLBACK_WARNING
from research.mtp_research.validation.diagnostic_validation_report import (
    write_review_json,
    write_review_markdown,
)
from research.mtp_research.validation.diagnostic_validation_review import DiagnosticValidationReviewer
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.thesis_decision_store import ThesisDecisionStore
from research.mtp_research.validation.sample_adequacy import SampleAdequacyAnalyzer
from research.mtp_research.validation.thesis_evaluator import ThesisEvaluator
from research.mtp_research.validation.thesis_registry import ThesisRegistry
from research.mtp_research.validation.thesis_report import (
    write_thesis_evaluation_json,
    write_thesis_evaluation_markdown,
)
from research.mtp_research.validation.walk_forward_models import (
    WalkForwardConfig,
    make_walk_forward_config_id,
)
from research.mtp_research.validation.walk_forward_report import (
    write_result_json as write_walk_forward_json,
    write_result_markdown as write_walk_forward_markdown,
)
from research.mtp_research.validation.walk_forward_store import WalkForwardValidationStore
from research.mtp_research.validation.walk_forward_validator import WalkForwardValidator


DEFAULT_DIAGNOSTIC_DATASET = "data/backtests/diagnostics/research_dataset_nearest300.jsonl"
DEFAULT_DIAGNOSTIC_OUTPUT_DIR = "data/backtests/diagnostics/reports"
DEFAULT_DIAGNOSTIC_RULE_STORE = "data/backtests/diagnostics/rule_backtest_results_nearest300.jsonl"
DEFAULT_DIAGNOSTIC_WALK_FORWARD_STORE = "data/backtests/diagnostics/walk_forward_results_nearest300.jsonl"
DEFAULT_DIAGNOSTIC_THESIS_STORE = "data/backtests/diagnostics/thesis_decisions_nearest300.jsonl"


def main() -> int:
    args = _parse_args()
    result = run_diagnostic_validation_review(args)
    print(f"clean_row_count={result['review'].clean_dataset.row_count}")
    print(f"diagnostic_row_count={result['review'].diagnostic_dataset.row_count}")
    print(f"nearest_fallback_row_count={result['review'].nearest_fallback_row_count}")
    print(f"rule_selected_row_gains={result['rule_selected_row_gains']}")
    print(f"walk_forward_valid_fold_summary={result['walk_forward_valid_fold_summary']}")
    print(f"thesis_status_changes={result['thesis_status_changes']}")
    print(f"recommended_next_action={result['review'].recommended_next_action}")
    print(f"baseline_report_paths={','.join(str(path) for path in result['baseline_report_paths'])}")
    print(f"rule_report_paths={','.join(str(path) for path in result['rule_report_paths'])}")
    print(f"walk_forward_report_paths={','.join(str(path) for path in result['walk_forward_report_paths'])}")
    print(f"thesis_report_paths={','.join(str(path) for path in result['thesis_report_paths'])}")
    print(f"review_markdown_path={result['review_markdown_path']}")
    print(f"review_json_path={result['review_json_path']}")
    print("network_calls=0")
    return 0


def run_diagnostic_validation_review(args: argparse.Namespace) -> dict[str, Any]:
    clean_dataset_path = str(args.clean_dataset_path)
    diagnostic_dataset_path = str(args.diagnostic_dataset_path)
    output_dir = Path(args.diagnostic_output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    clean_rows = ResearchDatasetStore(clean_dataset_path).load_all()
    diagnostic_rows = ResearchDatasetStore(diagnostic_dataset_path).load_all()
    rules = default_rule_library()

    baseline_paths = _run_baseline_report(args, diagnostic_rows, diagnostic_dataset_path, output_dir)
    diagnostic_rule_results, rule_paths = _run_rule_backtests(args, diagnostic_rows, output_dir)
    diagnostic_walk_forward_result, walk_paths = _run_walk_forward(args, diagnostic_rows, rules, output_dir)
    diagnostic_decisions, thesis_paths = _run_thesis_evaluation(
        args,
        [diagnostic_walk_forward_result],
        diagnostic_rows,
        output_dir,
    )

    reviewer = DiagnosticValidationReviewer()
    review = reviewer.build_review(
        clean_dataset_rows=clean_rows,
        diagnostic_dataset_rows=diagnostic_rows,
        clean_rule_results=RuleBacktestStore(args.clean_rule_store_path).load_all(),
        diagnostic_rule_results=diagnostic_rule_results,
        clean_walk_forward_results=WalkForwardValidationStore(args.clean_walk_forward_store_path).load_all(),
        diagnostic_walk_forward_results=[diagnostic_walk_forward_result],
        clean_thesis_decisions=ThesisDecisionStore(args.clean_decision_store_path).load_all(),
        diagnostic_thesis_decisions=diagnostic_decisions,
        clean_dataset_path=clean_dataset_path,
        diagnostic_dataset_path=diagnostic_dataset_path,
    )
    review_markdown_path = write_review_markdown(review, output_dir / f"{review.review_id}.md")
    review_json_path = write_review_json(review, output_dir / f"{review.review_id}.json")

    all_report_paths = [
        *baseline_paths,
        *rule_paths,
        *walk_paths,
        *thesis_paths,
        review_markdown_path,
        review_json_path,
    ]
    _mark_diagnostic_reports(all_report_paths)

    return {
        "review": review,
        "baseline_report_paths": baseline_paths,
        "rule_report_paths": rule_paths,
        "walk_forward_report_paths": walk_paths,
        "thesis_report_paths": thesis_paths,
        "review_markdown_path": review_markdown_path,
        "review_json_path": review_json_path,
        "rule_selected_row_gains": {
            item.rule_id: item.selected_count_gain for item in review.rule_comparisons
        },
        "walk_forward_valid_fold_summary": {
            item.rule_id: {
                "clean": item.clean_valid_test_fold_count,
                "diagnostic": item.diagnostic_valid_test_fold_count,
            }
            for item in review.walk_forward_comparisons
        },
        "thesis_status_changes": {
            item.thesis_id: {
                "clean": item.clean_recommended_status,
                "diagnostic": item.diagnostic_recommended_status,
            }
            for item in review.thesis_comparisons
            if item.changed
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run diagnostic validation review v0.")
    parser.add_argument("--clean-dataset-path", default="data/backtests/research_dataset.jsonl")
    parser.add_argument("--diagnostic-dataset-path", default=DEFAULT_DIAGNOSTIC_DATASET)
    parser.add_argument("--diagnostic-output-dir", default=DEFAULT_DIAGNOSTIC_OUTPUT_DIR)
    parser.add_argument("--diagnostic-rule-store-path", default=DEFAULT_DIAGNOSTIC_RULE_STORE)
    parser.add_argument("--diagnostic-walk-forward-store-path", default=DEFAULT_DIAGNOSTIC_WALK_FORWARD_STORE)
    parser.add_argument("--diagnostic-decision-store-path", default=DEFAULT_DIAGNOSTIC_THESIS_STORE)
    parser.add_argument("--clean-rule-store-path", default="data/backtests/rule_backtest_results.jsonl")
    parser.add_argument("--clean-walk-forward-store-path", default="data/backtests/walk_forward_results.jsonl")
    parser.add_argument("--clean-decision-store-path", default="data/backtests/thesis_decisions.jsonl")
    parser.add_argument("--theses-dir", default="theses")
    parser.add_argument("--min-label-quality", default="sparse")
    parser.add_argument("--horizon-name")
    parser.add_argument("--window-name")
    parser.add_argument("--train-window-seconds", type=int, default=86400)
    parser.add_argument("--test-window-seconds", type=int, default=21600)
    parser.add_argument("--step-seconds", type=int, default=21600)
    parser.add_argument("--min-train-rows", type=int, default=10)
    parser.add_argument("--min-test-rows", type=int, default=5)
    parser.add_argument("--min-rule-rows", type=int, default=10)
    parser.add_argument("--entry-fee-bps", type=float, default=125.0)
    parser.add_argument("--exit-fee-bps", type=float, default=125.0)
    parser.add_argument("--slippage-bps", type=float, default=200.0)
    parser.add_argument("--priority-fee-bps", type=float, default=0.0)
    parser.add_argument("--failure-penalty-bps", type=float, default=0.0)
    parser.add_argument("--min-total-test-selected-count", type=int, default=50)
    parser.add_argument("--min-positive-test-fold-rate", type=float, default=0.6)
    parser.add_argument("--min-avg-test-net-return", type=float, default=0.0)
    parser.add_argument("--min-consistency-score", type=float, default=0.0)
    return parser.parse_args()


def _run_baseline_report(
    args: argparse.Namespace,
    diagnostic_rows,
    diagnostic_dataset_path: str,
    output_dir: Path,
) -> list[Path]:
    analyzer = BaselineEdgeAnalyzer(
        min_label_quality=args.min_label_quality,
        require_forward_return=True,
    )
    rows_for_analysis = analyzer.filter_dataset_rows(
        diagnostic_rows,
        window_names=[args.window_name] if args.window_name else None,
        horizon_names=[args.horizon_name] if args.horizon_name else None,
        min_label_quality=args.min_label_quality,
        require_forward_return=True,
    )
    report = analyzer.analyze(rows_for_analysis)
    report.dataset_path = diagnostic_dataset_path
    report.warning_flags = sorted(set(report.warning_flags + [DIAGNOSTIC_FALLBACK_WARNING]))
    markdown_path = write_baseline_markdown(report, output_dir / f"{report.report_id}.md")
    json_path = write_baseline_json(report, output_dir / f"{report.report_id}.json")
    return [markdown_path, json_path]


def _run_rule_backtests(args: argparse.Namespace, diagnostic_rows, output_dir: Path):
    cost = CostAssumptions(
        entry_fee_bps=args.entry_fee_bps,
        exit_fee_bps=args.exit_fee_bps,
        slippage_bps=args.slippage_bps,
        priority_fee_bps=args.priority_fee_bps,
        failure_penalty_bps=args.failure_penalty_bps,
    )
    config = RuleBacktestConfig(
        config_id=_rule_config_id(args),
        horizon_name=args.horizon_name,
        window_name=args.window_name,
        min_label_quality=args.min_label_quality,
        min_rows=args.min_rule_rows,
        cost_assumptions=cost,
        metadata_json={
            "diagnostic_mode": True,
            "diagnostic_warning": DIAGNOSTIC_FALLBACK_WARNING,
        },
    )
    backtester = RuleBacktester(config)
    results = []
    for rule in default_rule_library():
        result = backtester.run_backtest(diagnostic_rows, rule, config=config)
        result.warning_flags = sorted(set(result.warning_flags + [DIAGNOSTIC_FALLBACK_WARNING]))
        results.append(result)
    RuleBacktestStore(args.diagnostic_rule_store_path).upsert_many(results)
    multi_path = write_multi_result_markdown(
        results,
        output_dir / f"rule_backtest_comparison_{config.config_id}.md",
    )
    output_paths = [multi_path]
    for result in results:
        output_paths.append(write_rule_result_json(result, output_dir / f"{result.result_id}.json"))
        output_paths.append(write_rule_result_markdown(result, output_dir / f"{result.result_id}.md"))
    return results, output_paths


def _run_walk_forward(args: argparse.Namespace, diagnostic_rows, rules, output_dir: Path):
    config_id = make_walk_forward_config_id(
        args.train_window_seconds,
        args.test_window_seconds,
        args.step_seconds,
        0,
    )
    walk_config = WalkForwardConfig(
        config_id=config_id,
        train_window_seconds=args.train_window_seconds,
        test_window_seconds=args.test_window_seconds,
        step_seconds=args.step_seconds,
        gap_seconds=0,
        min_train_rows=args.min_train_rows,
        min_test_rows=args.min_test_rows,
        horizon_name=args.horizon_name,
        window_name=args.window_name,
        min_label_quality=args.min_label_quality,
        metadata_json={
            "diagnostic_mode": True,
            "diagnostic_warning": DIAGNOSTIC_FALLBACK_WARNING,
        },
    )
    rule_config = RuleBacktestConfig(
        config_id=f"{config_id}__rule_backtest",
        horizon_name=args.horizon_name,
        window_name=args.window_name,
        min_label_quality=args.min_label_quality,
        min_rows=args.min_test_rows,
        cost_assumptions=CostAssumptions(
            entry_fee_bps=args.entry_fee_bps,
            exit_fee_bps=args.exit_fee_bps,
            slippage_bps=args.slippage_bps,
            priority_fee_bps=args.priority_fee_bps,
            failure_penalty_bps=args.failure_penalty_bps,
        ),
        metadata_json={"diagnostic_mode": True},
    )
    result = WalkForwardValidator(walk_config, rule_config).validate(
        diagnostic_rows,
        rules,
        dataset_path=str(args.diagnostic_dataset_path),
    )
    result.warning_flags = sorted(set(result.warning_flags + [DIAGNOSTIC_FALLBACK_WARNING]))
    WalkForwardValidationStore(args.diagnostic_walk_forward_store_path).upsert(result)
    markdown_path = write_walk_forward_markdown(result, output_dir / f"{result.validation_id}.md")
    json_path = write_walk_forward_json(result, output_dir / f"{result.validation_id}.json")
    return result, [markdown_path, json_path]


def _run_thesis_evaluation(
    args: argparse.Namespace,
    diagnostic_walk_forward_results,
    diagnostic_rows,
    output_dir: Path,
):
    theses = ThesisRegistry(args.theses_dir).load_theses()
    sample_adequacy_report = SampleAdequacyAnalyzer().build_report(
        diagnostic_rows,
        diagnostic_walk_forward_results,
    )
    evaluator = ThesisEvaluator(
        min_total_test_selected_count=args.min_total_test_selected_count,
        min_positive_test_fold_rate=args.min_positive_test_fold_rate,
        min_avg_test_net_return=args.min_avg_test_net_return,
        min_consistency_score=args.min_consistency_score,
        sample_adequacy_report=sample_adequacy_report,
    )
    summaries = evaluator.evaluate_all(theses, diagnostic_walk_forward_results)
    decisions = [
        evaluator.summary_to_decision(thesis, summary)
        for thesis, summary in zip(theses, summaries)
    ]
    for decision in decisions:
        decision.warning_flags = sorted(set(decision.warning_flags + [DIAGNOSTIC_FALLBACK_WARNING]))
        decision.metadata_json["diagnostic_mode"] = True
        decision.metadata_json["diagnostic_warning"] = DIAGNOSTIC_FALLBACK_WARNING
        decision.metadata_json["sample_adequacy_report"] = sample_adequacy_report.to_dict()
    ThesisDecisionStore(args.diagnostic_decision_store_path).upsert_many(decisions)
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
    return decisions, [markdown_path, json_path]


def _rule_config_id(args: argparse.Namespace) -> str:
    parts = [
        "diagnostic_rule_backtest_v0",
        f"window_{args.window_name or 'any'}",
        f"horizon_{args.horizon_name or 'any'}",
        f"quality_{args.min_label_quality}",
        f"cost_{int(args.entry_fee_bps)}_{int(args.exit_fee_bps)}_{int(args.slippage_bps)}_{int(args.priority_fee_bps)}_{int(args.failure_penalty_bps)}",
    ]
    return "__".join(parts)


def _mark_diagnostic_reports(paths: list[Path]) -> None:
    for path in paths:
        if path.suffix == ".md":
            text = path.read_text(encoding="utf-8")
            if DIAGNOSTIC_FALLBACK_WARNING not in text[:500]:
                path.write_text(
                    f"> Warning: {DIAGNOSTIC_FALLBACK_WARNING}\n\n{text}",
                    encoding="utf-8",
                )
        elif path.suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                payload["diagnostic_warning"] = DIAGNOSTIC_FALLBACK_WARNING
                path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _status_counts(decisions) -> dict[str, int]:
    return dict(sorted(Counter(decision.recommended_status for decision in decisions).items()))


if __name__ == "__main__":
    raise SystemExit(main())
