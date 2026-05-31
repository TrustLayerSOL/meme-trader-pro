"""Walk-forward validator for rule-based backtests."""

from __future__ import annotations

from statistics import mean, median

from research.mtp_research.backtest.rule_backtest_models import (
    RuleBacktestConfig,
    RuleDefinition,
)
from research.mtp_research.backtest.rule_backtester import RuleBacktester
from research.mtp_research.validation.research_dataset_builder import _quality_rank
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.walk_forward_models import (
    FoldRuleResult,
    RuleWalkForwardSummary,
    WalkForwardConfig,
    WalkForwardFold,
    WalkForwardValidationResult,
    make_validation_id,
    utc_now_iso,
)
from research.mtp_research.validation.walk_forward_splitter import WalkForwardSplitter


class WalkForwardValidator:
    """Run fixed rule definitions through chronological train/test folds."""

    def __init__(
        self,
        config: WalkForwardConfig,
        rule_backtest_config: RuleBacktestConfig | None = None,
    ):
        self.config = config
        self.rule_backtest_config = rule_backtest_config or RuleBacktestConfig(
            config_id=f"{config.config_id}__rule_backtest"
        )

    def prefilter_rows(self, rows: list[ResearchDatasetRow]) -> list[ResearchDatasetRow]:
        output = []
        min_quality_rank = _quality_rank(self.config.min_label_quality)
        for row in rows:
            if self.config.horizon_name and row.horizon_name != self.config.horizon_name:
                continue
            if self.config.window_name and row.window_name != self.config.window_name:
                continue
            if _quality_rank(row.label_quality) < min_quality_rank:
                continue
            if self.config.require_entry_price and row.entry_price is None:
                continue
            if self.config.require_forward_return and row.forward_return is None:
                continue
            output.append(row)
        return sorted(output, key=lambda row: (row.snapshot_ts, row.row_id))

    def validate_rule_on_fold(
        self,
        rule: RuleDefinition,
        train_rows: list[ResearchDatasetRow],
        test_rows: list[ResearchDatasetRow],
        fold: WalkForwardFold,
    ) -> FoldRuleResult:
        train_config = self._fold_rule_backtest_config(fold, "train")
        test_config = self._fold_rule_backtest_config(fold, "test")
        backtester = RuleBacktester()
        train_result = backtester.run_backtest(train_rows, rule, config=train_config)
        test_result = backtester.run_backtest(test_rows, rule, config=test_config)
        train_summary = train_result.summary
        test_summary = test_result.summary
        warning_flags = []
        if len(train_rows) < self.config.min_train_rows:
            warning_flags.append("small_train_fold")
        if len(test_rows) < self.config.min_test_rows:
            warning_flags.append("small_test_fold")
        if test_summary.selected_count == 0:
            warning_flags.append("no_test_trades")
        if (
            train_summary.avg_net_return is not None
            and train_summary.avg_net_return > 0
            and (test_summary.avg_net_return is None or test_summary.avg_net_return <= 0)
        ):
            warning_flags.append("train_only_pattern")
        return FoldRuleResult(
            fold_id=fold.fold_id,
            fold_index=fold.fold_index,
            rule_id=rule.rule_id,
            rule_name=rule.name,
            train_result_id=train_result.result_id,
            test_result_id=test_result.result_id,
            train_selected_count=train_summary.selected_count,
            test_selected_count=test_summary.selected_count,
            train_avg_net_return=train_summary.avg_net_return,
            test_avg_net_return=test_summary.avg_net_return,
            train_median_net_return=train_summary.median_net_return,
            test_median_net_return=test_summary.median_net_return,
            train_win_rate=train_summary.win_rate,
            test_win_rate=test_summary.win_rate,
            train_profit_factor=train_summary.profit_factor,
            test_profit_factor=test_summary.profit_factor,
            train_cumulative_net_return=train_summary.cumulative_net_return,
            test_cumulative_net_return=test_summary.cumulative_net_return,
            train_max_equity_drawdown=train_summary.max_equity_drawdown,
            test_max_equity_drawdown=test_summary.max_equity_drawdown,
            train_rug_like_drop_rate=train_summary.rug_like_drop_rate,
            test_rug_like_drop_rate=test_summary.rug_like_drop_rate,
            warning_flags=warning_flags,
            metadata_json={
                "train_row_count": len(train_rows),
                "test_row_count": len(test_rows),
            },
        )

    def summarize_rule_results(
        self,
        rule: RuleDefinition,
        fold_results: list[FoldRuleResult],
    ) -> RuleWalkForwardSummary:
        valid = [
            result for result in fold_results
            if result.test_selected_count > 0 and result.test_avg_net_return is not None
        ]
        test_returns = [result.test_avg_net_return for result in valid if result.test_avg_net_return is not None]
        test_win_rates = [result.test_win_rate for result in valid if result.test_win_rate is not None]
        test_profit_factors = [result.test_profit_factor for result in valid if result.test_profit_factor is not None]
        test_cumulative = [
            result.test_cumulative_net_return for result in valid
            if result.test_cumulative_net_return is not None
        ]
        test_drawdowns = [
            result.test_max_equity_drawdown for result in valid
            if result.test_max_equity_drawdown is not None
        ]
        test_rug_rates = [
            result.test_rug_like_drop_rate for result in valid
            if result.test_rug_like_drop_rate is not None
        ]
        positive_count = sum(1 for result in valid if (result.test_avg_net_return or 0.0) > 0)
        negative_count = sum(1 for result in valid if (result.test_avg_net_return or 0.0) <= 0)
        valid_count = len(valid)
        total_selected = sum(result.test_selected_count for result in fold_results)
        positive_rate = (positive_count / valid_count) if valid_count else None
        avg_return = mean(test_returns) if test_returns else None
        consistency_score = None
        if positive_rate is not None and avg_return is not None:
            consistency_score = positive_rate * max(avg_return, 0.0)
        warning_flags = []
        if valid_count == 0:
            warning_flags.append("no_valid_test_folds")
        if positive_rate is not None and positive_rate < 0.5:
            warning_flags.append("low_consistency")
        if total_selected < self.config.min_test_rows * 2:
            warning_flags.append("small_total_test_sample")
        return RuleWalkForwardSummary(
            rule_id=rule.rule_id,
            rule_name=rule.name,
            fold_count=len(fold_results),
            valid_test_fold_count=valid_count,
            total_test_selected_count=total_selected,
            avg_test_selected_count=(total_selected / len(fold_results)) if fold_results else None,
            avg_test_net_return=avg_return,
            median_test_net_return=median(test_returns) if test_returns else None,
            positive_test_fold_count=positive_count,
            negative_test_fold_count=negative_count,
            positive_test_fold_rate=positive_rate,
            avg_test_win_rate=mean(test_win_rates) if test_win_rates else None,
            avg_test_profit_factor=mean(test_profit_factors) if test_profit_factors else None,
            avg_test_cumulative_net_return=mean(test_cumulative) if test_cumulative else None,
            worst_test_cumulative_net_return=min(test_cumulative) if test_cumulative else None,
            avg_test_max_drawdown=mean(test_drawdowns) if test_drawdowns else None,
            avg_test_rug_like_drop_rate=mean(test_rug_rates) if test_rug_rates else None,
            consistency_score=consistency_score,
            warning_flags=warning_flags,
            metadata_json={"summary_version": "walk_forward_summary_v0"},
        )

    def validate(
        self,
        rows: list[ResearchDatasetRow],
        rules: list[RuleDefinition],
        dataset_path: str = "",
    ) -> WalkForwardValidationResult:
        filtered = self.prefilter_rows(rows)
        splitter = WalkForwardSplitter(self.config)
        folds = splitter.generate_folds(filtered)
        fold_rule_results: list[FoldRuleResult] = []
        for fold in folds:
            train_rows = splitter.rows_for_train_fold(filtered, fold)
            test_rows = splitter.rows_for_test_fold(filtered, fold)
            for rule in rules:
                fold_rule_results.append(
                    self.validate_rule_on_fold(rule, train_rows, test_rows, fold)
                )
        rule_summaries = [
            self.summarize_rule_results(
                rule,
                [result for result in fold_rule_results if result.rule_id == rule.rule_id],
            )
            for rule in rules
        ]
        warning_flags = [
            "exploratory_walk_forward_not_live_signal",
            "no_live_trading_enabled",
            "heuristic_trade_labels_v0",
            "cost_model_v0_simple_bps",
        ]
        if not folds:
            warning_flags.append("no_folds_generated")
        if len(filtered) < self.config.min_train_rows + self.config.min_test_rows:
            warning_flags.append("small_dataset")
        return WalkForwardValidationResult(
            validation_id=make_validation_id(self.config.config_id),
            created_at=utc_now_iso(),
            config=self.config,
            dataset_path=dataset_path,
            row_count=len(rows),
            filtered_row_count=len(filtered),
            fold_count=len(folds),
            rules_tested=len(rules),
            folds=folds,
            fold_rule_results=fold_rule_results,
            rule_summaries=rule_summaries,
            top_findings=self._top_findings(rule_summaries),
            warning_flags=warning_flags,
            metadata_json={
                "validator_version": "walk_forward_validator_v0",
                "chronological_split_only": True,
                "rules_not_optimized": True,
            },
        )

    def _fold_rule_backtest_config(
        self,
        fold: WalkForwardFold,
        split_name: str,
    ) -> RuleBacktestConfig:
        base = self.rule_backtest_config
        return RuleBacktestConfig(
            config_id=f"{base.config_id}__{fold.fold_id}__{split_name}",
            horizon_name=self.config.horizon_name,
            window_name=self.config.window_name,
            min_label_quality=self.config.min_label_quality,
            require_entry_price=self.config.require_entry_price,
            require_forward_return=self.config.require_forward_return,
            min_rows=base.min_rows,
            cost_assumptions=base.cost_assumptions,
            metadata_json={
                **base.metadata_json,
                "walk_forward_fold_id": fold.fold_id,
                "split_name": split_name,
            },
        )

    def _top_findings(self, summaries: list[RuleWalkForwardSummary]) -> list[str]:
        ranked = [
            summary for summary in summaries
            if summary.valid_test_fold_count > 0 and summary.consistency_score is not None
        ]
        ranked.sort(key=lambda summary: summary.consistency_score or 0.0, reverse=True)
        return [
            (
                f"Exploratory: {summary.rule_id} produced consistency score "
                f"{summary.consistency_score:.6f} across {summary.valid_test_fold_count} "
                "validation folds; not a trading recommendation."
            )
            for summary in ranked[:5]
        ]
