"""Walk-forward fold sufficiency diagnostics."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from research.mtp_research.backtest.rule_backtest_models import (
    RuleBacktestConfig,
    RuleDefinition,
)
from research.mtp_research.backtest.rule_backtester import RuleBacktester
from research.mtp_research.validation.fold_sufficiency_models import (
    FOLD_SUFFICIENCY_WARNING,
    FoldConfigCandidate,
    FoldConfigSufficiencyResult,
    FoldSufficiencyReport,
    RuleFoldSufficiency,
    make_fold_sufficiency_report_id,
)
from research.mtp_research.validation.research_dataset_builder import _quality_rank
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.walk_forward_models import WalkForwardConfig
from research.mtp_research.validation.walk_forward_splitter import WalkForwardSplitter


class FoldSufficiencyAnalyzer:
    """Evaluate whether local rows support chronological walk-forward folds."""

    def default_config_candidates(self) -> list[FoldConfigCandidate]:
        return [
            FoldConfigCandidate(
                name="ultra_short_15m_train_5m_test",
                train_window_seconds=900,
                test_window_seconds=300,
                step_seconds=300,
                min_train_rows=5,
                min_test_rows=3,
            ),
            FoldConfigCandidate(
                name="short_30m_train_10m_test",
                train_window_seconds=1800,
                test_window_seconds=600,
                step_seconds=600,
                min_train_rows=10,
                min_test_rows=5,
            ),
            FoldConfigCandidate(
                name="one_hour_train_15m_test",
                train_window_seconds=3600,
                test_window_seconds=900,
                step_seconds=900,
                min_train_rows=15,
                min_test_rows=5,
            ),
            FoldConfigCandidate(
                name="six_hour_train_one_hour_test",
                train_window_seconds=21600,
                test_window_seconds=3600,
                step_seconds=3600,
                min_train_rows=20,
                min_test_rows=5,
            ),
            FoldConfigCandidate(
                name="one_day_train_six_hour_test",
                train_window_seconds=86400,
                test_window_seconds=21600,
                step_seconds=21600,
                min_train_rows=25,
                min_test_rows=10,
            ),
        ]

    def summarize_dataset_time(self, rows: list[ResearchDatasetRow]) -> dict[str, Any]:
        if not rows:
            return {
                "row_count": 0,
                "token_count": 0,
                "time_min": None,
                "time_max": None,
                "time_span_seconds": None,
                "rows_by_hour": {},
            }
        timestamps = [row.snapshot_ts for row in rows]
        time_min = min(timestamps)
        time_max = max(timestamps)
        return {
            "row_count": len(rows),
            "token_count": len({row.token_mint for row in rows}),
            "time_min": time_min,
            "time_max": time_max,
            "time_span_seconds": time_max - time_min,
            "rows_by_hour": dict(sorted(Counter(ts // 3600 for ts in timestamps).items())),
        }

    def evaluate_config(
        self,
        rows: list[ResearchDatasetRow],
        rules: list[RuleDefinition],
        config_candidate: FoldConfigCandidate,
        horizon_name: str | None = None,
        window_name: str | None = None,
        min_label_quality: str = "sparse",
        require_forward_return: bool = True,
    ) -> FoldConfigSufficiencyResult:
        filtered = _filter_rows(
            rows,
            horizon_name=horizon_name,
            window_name=window_name,
            min_label_quality=min_label_quality,
            require_forward_return=require_forward_return,
        )
        time_summary = self.summarize_dataset_time(filtered)
        walk_config = WalkForwardConfig(
            config_id=f"fold_sufficiency__{config_candidate.name}",
            train_window_seconds=config_candidate.train_window_seconds,
            test_window_seconds=config_candidate.test_window_seconds,
            step_seconds=config_candidate.step_seconds,
            gap_seconds=config_candidate.gap_seconds,
            min_train_rows=config_candidate.min_train_rows,
            min_test_rows=config_candidate.min_test_rows,
            horizon_name=horizon_name,
            window_name=window_name,
            min_label_quality=min_label_quality,
            require_forward_return=require_forward_return,
            metadata_json={"diagnostic_only": True},
        )
        splitter = WalkForwardSplitter(walk_config)
        folds = splitter.generate_folds(filtered)
        valid_fold_count = sum(
            1 for fold in folds
            if fold.train_row_count >= config_candidate.min_train_rows
            and fold.test_row_count >= config_candidate.min_test_rows
        )
        rule_sufficiency = [
            self._evaluate_rule(filtered, splitter, folds, rule, config_candidate)
            for rule in rules
        ]
        warning_flags = ["diagnostic_only_not_strategy_optimization", FOLD_SUFFICIENCY_WARNING]
        if not folds:
            warning_flags.append("no_folds_generated")
        if (
            time_summary["time_span_seconds"] is not None
            and time_summary["time_span_seconds"]
            < config_candidate.train_window_seconds + config_candidate.gap_seconds + config_candidate.test_window_seconds
        ):
            warning_flags.append("time_span_too_short")
        if not any(item.rows_selected_total > 0 for item in rule_sufficiency):
            warning_flags.append("no_rule_selected_rows")
        if not any(item.valid_test_fold_count > 0 for item in rule_sufficiency):
            warning_flags.append("no_valid_test_folds")
        if sum(item.total_test_selected_count for item in rule_sufficiency) < config_candidate.min_test_rows:
            warning_flags.append("low_total_test_selected_count")

        return FoldConfigSufficiencyResult(
            config_name=config_candidate.name,
            train_window_seconds=config_candidate.train_window_seconds,
            test_window_seconds=config_candidate.test_window_seconds,
            step_seconds=config_candidate.step_seconds,
            gap_seconds=config_candidate.gap_seconds,
            min_train_rows=config_candidate.min_train_rows,
            min_test_rows=config_candidate.min_test_rows,
            fold_count=len(folds),
            valid_fold_count=valid_fold_count,
            row_count=len(filtered),
            token_count=len({row.token_mint for row in filtered}),
            time_span_seconds=time_summary["time_span_seconds"],
            rule_sufficiency=rule_sufficiency,
            warning_flags=sorted(set(warning_flags)),
            metadata_json={
                "diagnostic_only": True,
                "window_name": window_name,
                "horizon_name": horizon_name,
                "min_label_quality": min_label_quality,
                "require_forward_return": require_forward_return,
            },
        )

    def analyze(
        self,
        rows: list[ResearchDatasetRow],
        rules: list[RuleDefinition],
        configs: list[FoldConfigCandidate] | None = None,
        dataset_path: str = "",
        horizon_name: str | None = None,
        window_name: str | None = None,
        min_label_quality: str = "sparse",
        require_forward_return: bool = True,
    ) -> FoldSufficiencyReport:
        selected_configs = configs or self.default_config_candidates()
        filtered = _filter_rows(
            rows,
            horizon_name=horizon_name,
            window_name=window_name,
            min_label_quality=min_label_quality,
            require_forward_return=require_forward_return,
        )
        time_summary = self.summarize_dataset_time(filtered)
        config_results = [
            self.evaluate_config(
                filtered,
                rules,
                config,
                horizon_name=horizon_name,
                window_name=window_name,
                min_label_quality=min_label_quality,
                require_forward_return=require_forward_return,
            )
            for config in selected_configs
        ]
        best = _best_config(config_results)
        if best:
            best.recommended = True
        report = FoldSufficiencyReport(
            report_id=make_fold_sufficiency_report_id(),
            created_at=datetime.now(timezone.utc).isoformat(),
            dataset_path=dataset_path,
            row_count=time_summary["row_count"],
            token_count=time_summary["token_count"],
            time_min=time_summary["time_min"],
            time_max=time_summary["time_max"],
            time_span_seconds=time_summary["time_span_seconds"],
            config_results=config_results,
            best_config_name=best.config_name if best else None,
            warning_flags=[
                FOLD_SUFFICIENCY_WARNING,
                "diagnostic_only_not_strategy_optimization",
            ],
            metadata_json={
                "rows_by_hour": time_summary["rows_by_hour"],
                "window_name": window_name,
                "horizon_name": horizon_name,
                "min_label_quality": min_label_quality,
                "require_forward_return": require_forward_return,
            },
        )
        report.recommended_next_action = self._recommend_next_action(report)
        return report

    def _evaluate_rule(
        self,
        rows: list[ResearchDatasetRow],
        splitter: WalkForwardSplitter,
        folds,
        rule: RuleDefinition,
        config_candidate: FoldConfigCandidate,
    ) -> RuleFoldSufficiency:
        backtester = RuleBacktester(RuleBacktestConfig(config_id=f"fold_sufficiency__{rule.rule_id}"))
        selected_rows = [row for row in rows if backtester.row_passes_rule(row, rule)]
        test_selected_counts: list[int] = []
        train_selected_counts: list[int] = []
        valid_test_fold_count = 0
        folds_with_train_rows = 0
        folds_with_test_rows = 0
        for fold in folds:
            train_rows = splitter.rows_for_train_fold(rows, fold)
            test_rows = splitter.rows_for_test_fold(rows, fold)
            selected_train = [row for row in train_rows if backtester.row_passes_rule(row, rule)]
            selected_test = [row for row in test_rows if backtester.row_passes_rule(row, rule)]
            train_selected_counts.append(len(selected_train))
            test_selected_counts.append(len(selected_test))
            if len(train_rows) >= config_candidate.min_train_rows:
                folds_with_train_rows += 1
            if len(test_rows) >= config_candidate.min_test_rows:
                folds_with_test_rows += 1
            if (
                len(train_rows) >= config_candidate.min_train_rows
                and len(test_rows) >= config_candidate.min_test_rows
                and len(selected_test) > 0
            ):
                valid_test_fold_count += 1

        warning_flags = []
        if not selected_rows:
            warning_flags.append("no_rule_selected_rows")
        if valid_test_fold_count == 0:
            warning_flags.append("no_valid_test_folds")
        total_test_selected = sum(test_selected_counts)
        if total_test_selected < config_candidate.min_test_rows:
            warning_flags.append("low_total_test_selected_count")
        return RuleFoldSufficiency(
            rule_id=rule.rule_id,
            rule_name=rule.name,
            rows_selected_total=len(selected_rows),
            folds_with_train_rows=folds_with_train_rows,
            folds_with_test_rows=folds_with_test_rows,
            folds_with_selected_train_trades=sum(1 for count in train_selected_counts if count > 0),
            folds_with_selected_test_trades=sum(1 for count in test_selected_counts if count > 0),
            valid_test_fold_count=valid_test_fold_count,
            total_test_selected_count=total_test_selected,
            avg_test_selected_count=(
                total_test_selected / len(test_selected_counts) if test_selected_counts else None
            ),
            max_test_selected_count=max(test_selected_counts) if test_selected_counts else 0,
            warning_flags=warning_flags,
            metadata_json={"diagnostic_only": True},
        )

    def _recommend_next_action(self, report: FoldSufficiencyReport) -> str:
        if report.row_count < 200:
            return "scale_bounded_backfill"
        shortest = min(report.config_results, key=lambda item: item.train_window_seconds, default=None)
        if shortest and "time_span_too_short" in shortest.warning_flags:
            return "scale_bounded_backfill_for_more_time_span"
        if report.config_results and not any(
            sum(rule.rows_selected_total for rule in config.rule_sufficiency) > 0
            for config in report.config_results
        ):
            return "inspect_or_refine_rule_definitions"
        best_valid_configs = [
            config for config in report.config_results
            if _total_valid_rule_folds(config) > 0
        ]
        default_config = next(
            (
                config for config in report.config_results
                if config.config_name == "one_day_train_six_hour_test"
            ),
            None,
        )
        if best_valid_configs and (default_config is None or _total_valid_rule_folds(default_config) == 0):
            return "use_shorter_diagnostic_folds_until_dataset_scales"
        if len(best_valid_configs) > 1:
            return "run_walk_forward_with_best_diagnostic_config"
        return "scale_bounded_backfill_cautiously"


def _filter_rows(
    rows: list[ResearchDatasetRow],
    horizon_name: str | None,
    window_name: str | None,
    min_label_quality: str,
    require_forward_return: bool,
) -> list[ResearchDatasetRow]:
    min_rank = _quality_rank(min_label_quality)
    output = []
    for row in rows:
        if horizon_name and row.horizon_name != horizon_name:
            continue
        if window_name and row.window_name != window_name:
            continue
        if _quality_rank(row.label_quality) < min_rank:
            continue
        if require_forward_return and row.forward_return is None:
            continue
        output.append(row)
    return sorted(output, key=lambda item: (item.snapshot_ts, item.row_id))


def _best_config(results: list[FoldConfigSufficiencyResult]) -> FoldConfigSufficiencyResult | None:
    if not results:
        return None
    best = sorted(
        results,
        key=lambda item: (
            _total_valid_rule_folds(item),
            _total_test_selected_count(item),
            item.train_window_seconds,
        ),
        reverse=True,
    )[0]
    if _total_valid_rule_folds(best) == 0:
        return None
    return best


def _total_valid_rule_folds(result: FoldConfigSufficiencyResult) -> int:
    return sum(rule.valid_test_fold_count for rule in result.rule_sufficiency)


def _total_test_selected_count(result: FoldConfigSufficiencyResult) -> int:
    return sum(rule.total_test_selected_count for rule in result.rule_sufficiency)
