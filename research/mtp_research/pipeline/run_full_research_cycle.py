"""CLI for running a full local research cycle."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.backtest.rule_backtest_models import RuleBacktestConfig
from research.mtp_research.backtest.rule_backtest_report import write_multi_result_markdown
from research.mtp_research.backtest.rule_backtester import RuleBacktester
from research.mtp_research.backtest.rule_library import default_rule_library
from research.mtp_research.pipeline.evidence_models import (
    EvidenceRunConfig,
    make_evidence_run_id,
)
from research.mtp_research.pipeline.evidence_pipeline import EvidencePipeline
from research.mtp_research.validation.baseline_edge_analyzer import BaselineEdgeAnalyzer
from research.mtp_research.validation.baseline_report_writer import (
    write_report_json as write_baseline_json,
    write_report_markdown as write_baseline_markdown,
)
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.thesis_decision_store import ThesisDecisionStore
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Run full v3 research cycle.")
    parser.add_argument("--skip-backfill", action="store_true")
    parser.add_argument("--execute-backfill", action="store_true")
    parser.add_argument("--candidate-limit", type=int, default=5)
    parser.add_argument("--max-signatures-per-target", type=int, default=25)
    parser.add_argument("--max-transactions-per-target", type=int, default=25)
    parser.add_argument("--parse-limit", type=int)
    parser.add_argument("--normalize-limit", type=int)
    parser.add_argument("--max-snapshots", type=int)
    parser.add_argument("--min-label-quality", default="sparse")
    parser.add_argument("--walk-forward-train-window-seconds", type=int, default=86400)
    parser.add_argument("--walk-forward-test-window-seconds", type=int, default=21600)
    parser.add_argument("--walk-forward-step-seconds", type=int, default=21600)
    args = parser.parse_args()

    output_dir = Path("data/backtests/reports")
    output_dir.mkdir(parents=True, exist_ok=True)
    pipeline = EvidencePipeline()
    backfill_summary = None
    if not args.skip_backfill:
        candidates = pipeline.select_candidates(args.candidate_limit)
        targets = pipeline.plan_targets(candidates, ["mint", "pool", "creator"])
        backfill_config = EvidenceRunConfig(
            run_id=make_evidence_run_id(),
            candidate_limit=args.candidate_limit,
            max_signatures_per_target=args.max_signatures_per_target,
            max_transactions_per_target=args.max_transactions_per_target,
            dry_run=not args.execute_backfill,
        )
        backfill_summary = pipeline.run_backfill_targets(
            targets,
            backfill_config,
            execute=args.execute_backfill,
        )
        backfill_summary.candidates_selected = len(candidates)
        if not args.execute_backfill:
            print("backfill_note=backfill_not_executed_results_depend_on_existing_local_data")

    offline_summary = pipeline.run_offline_rebuild(
        EvidenceRunConfig(run_id=make_evidence_run_id(), dry_run=False),
        parse_limit=args.parse_limit,
        normalize_limit=args.normalize_limit,
        max_snapshots=args.max_snapshots,
    )
    rows = ResearchDatasetStore().load_all()

    baseline = BaselineEdgeAnalyzer(min_label_quality=args.min_label_quality).analyze(rows)
    baseline_md = write_baseline_markdown(baseline, output_dir / f"{baseline.report_id}.md")
    baseline_json = write_baseline_json(baseline, output_dir / f"{baseline.report_id}.json")

    rules = default_rule_library()
    rule_config = RuleBacktestConfig(config_id="full_research_cycle_rule_backtest", min_label_quality=args.min_label_quality)
    rule_results = [RuleBacktester(rule_config).run_backtest(rows, rule, config=rule_config) for rule in rules]
    rule_report = write_multi_result_markdown(rule_results, output_dir / "full_research_cycle_rule_backtests.md")

    wf_config_id = make_walk_forward_config_id(
        args.walk_forward_train_window_seconds,
        args.walk_forward_test_window_seconds,
        args.walk_forward_step_seconds,
        0,
    )
    wf_config = WalkForwardConfig(
        config_id=wf_config_id,
        train_window_seconds=args.walk_forward_train_window_seconds,
        test_window_seconds=args.walk_forward_test_window_seconds,
        step_seconds=args.walk_forward_step_seconds,
        min_label_quality=args.min_label_quality,
    )
    wf_result = WalkForwardValidator(wf_config, rule_backtest_config=rule_config).validate(
        rows,
        rules,
        dataset_path=str(ResearchDatasetStore().path),
    )
    WalkForwardValidationStore().upsert(wf_result)
    wf_md = write_walk_forward_markdown(wf_result, output_dir / f"{wf_result.validation_id}.md")
    wf_json = write_walk_forward_json(wf_result, output_dir / f"{wf_result.validation_id}.json")

    theses = ThesisRegistry().load_theses()
    thesis_summaries = ThesisEvaluator().evaluate_all(theses, [wf_result])
    thesis_decisions = [
        ThesisEvaluator().summary_to_decision(thesis, summary)
        for thesis, summary in zip(theses, thesis_summaries)
    ]
    ThesisDecisionStore().upsert_many(thesis_decisions)
    thesis_md = write_thesis_evaluation_markdown(thesis_summaries, thesis_decisions, output_dir / "thesis_evaluation_report.md")
    thesis_json = write_thesis_evaluation_json(thesis_summaries, thesis_decisions, output_dir / "thesis_evaluation_report.json")

    print(f"offline_warning_flags={offline_summary.warning_flags}")
    print(f"backfill_warning_flags={backfill_summary.warning_flags if backfill_summary else []}")
    print(f"baseline_report_paths={[str(baseline_md), str(baseline_json)]}")
    print(f"rule_report_path={rule_report}")
    print(f"walk_forward_report_paths={[str(wf_md), str(wf_json)]}")
    print(f"thesis_report_paths={[str(thesis_md), str(thesis_json)]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
