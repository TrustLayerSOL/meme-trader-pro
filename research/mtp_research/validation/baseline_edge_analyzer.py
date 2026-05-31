"""Exploratory baseline edge analysis over research dataset rows."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from statistics import mean, median

from research.mtp_research.validation.baseline_report_models import (
    BaselineEdgeReport,
    BucketOutcomeSummary,
    FeatureBucket,
    FeatureBucketResult,
    FeatureReport,
    make_report_id,
)
from research.mtp_research.validation.research_dataset_builder import _quality_rank
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow


class BaselineEdgeAnalyzer:
    """Descriptive feature-bucket analyzer. Not a strategy validator."""

    def __init__(
        self,
        min_bucket_size: int = 10,
        bucket_count: int = 5,
        min_label_quality: str | None = "sparse",
        require_forward_return: bool = True,
    ):
        self.min_bucket_size = min_bucket_size
        self.bucket_count = bucket_count
        self.min_label_quality = min_label_quality
        self.require_forward_return = require_forward_return

    @staticmethod
    def default_feature_names() -> list[str]:
        return [
            "age_sec",
            "event_count",
            "possible_buy_count",
            "possible_sell_count",
            "token_accumulation_count",
            "token_distribution_count",
            "unique_actor_count",
            "base_volume",
            "quote_volume",
            "net_base_flow",
            "net_quote_flow",
            "buy_sell_imbalance",
            "confidence_weighted_buy_flow",
            "confidence_weighted_sell_flow",
            "confidence_weighted_net_flow",
            "avg_event_confidence",
            "max_event_confidence",
        ]

    def filter_dataset_rows(
        self,
        rows: list[ResearchDatasetRow],
        token_mints: list[str] | None = None,
        window_names: list[str] | None = None,
        horizon_names: list[str] | None = None,
        min_label_quality: str | None = None,
        require_forward_return: bool = True,
    ) -> list[ResearchDatasetRow]:
        token_set = set(token_mints or [])
        window_set = set(window_names or [])
        horizon_set = set(horizon_names or [])
        min_quality = self.min_label_quality if min_label_quality is None else min_label_quality
        min_quality_rank = _quality_rank(min_quality) if min_quality else None
        output = []
        for row in rows:
            if token_set and row.token_mint not in token_set:
                continue
            if window_set and row.window_name not in window_set:
                continue
            if horizon_set and row.horizon_name not in horizon_set:
                continue
            if min_quality_rank is not None and _quality_rank(row.label_quality) < min_quality_rank:
                continue
            if require_forward_return and row.forward_return is None:
                continue
            output.append(row)
        return output

    def summarize_outcomes(self, rows: list[ResearchDatasetRow]) -> BucketOutcomeSummary:
        returns = [row.forward_return for row in rows if row.forward_return is not None]
        runups = [row.max_runup for row in rows if row.max_runup is not None]
        drawdowns = [row.max_drawdown for row in rows if row.max_drawdown is not None]
        row_count = len(rows)
        rug_count = sum(1 for row in rows if row.rug_like_drop is True)
        no_liquidity_count = sum(1 for row in rows if row.no_future_liquidity)
        survived_count = sum(1 for row in rows if row.survived_horizon is True)
        return BucketOutcomeSummary(
            row_count=row_count,
            token_count=len({row.token_mint for row in rows}),
            rows_with_forward_return=len(returns),
            avg_forward_return=mean(returns) if returns else None,
            median_forward_return=median(returns) if returns else None,
            positive_forward_return_count=sum(1 for value in returns if value > 0),
            negative_forward_return_count=sum(1 for value in returns if value < 0),
            win_rate=(sum(1 for value in returns if value > 0) / len(returns)) if returns else None,
            avg_max_runup=mean(runups) if runups else None,
            median_max_runup=median(runups) if runups else None,
            avg_max_drawdown=mean(drawdowns) if drawdowns else None,
            median_max_drawdown=median(drawdowns) if drawdowns else None,
            rug_like_drop_count=rug_count,
            rug_like_drop_rate=(rug_count / row_count) if row_count else None,
            no_future_liquidity_count=no_liquidity_count,
            no_future_liquidity_rate=(no_liquidity_count / row_count) if row_count else None,
            survived_horizon_count=survived_count,
            survived_horizon_rate=(survived_count / row_count) if row_count else None,
            avg_future_event_count=mean([row.future_event_count for row in rows]) if rows else None,
            avg_future_quote_volume=mean([row.future_quote_volume for row in rows]) if rows else None,
        )

    def make_numeric_buckets(
        self,
        rows: list[ResearchDatasetRow],
        feature_name: str,
        bucket_count: int | None = None,
    ) -> list[tuple[FeatureBucket, list[ResearchDatasetRow]]]:
        count = bucket_count or self.bucket_count
        valued_rows = [
            (float(value), row)
            for row in rows
            if (value := getattr(row, feature_name, None)) is not None
        ]
        valued_rows.sort(key=lambda item: (item[0], item[1].row_id))
        if not valued_rows:
            return []
        unique_values = {value for value, _row in valued_rows}
        if len(unique_values) < 2:
            bucket = FeatureBucket(
                feature_name=feature_name,
                bucket_name="all",
                lower_bound=valued_rows[0][0],
                upper_bound=valued_rows[-1][0],
                row_count=len(valued_rows),
                token_count=len({row.token_mint for _value, row in valued_rows}),
                metadata_json={"low_variance_feature": True},
            )
            return [(bucket, [row for _value, row in valued_rows])]

        actual_bucket_count = min(count, len(valued_rows))
        output = []
        for index in range(actual_bucket_count):
            start = index * len(valued_rows) // actual_bucket_count
            end = (index + 1) * len(valued_rows) // actual_bucket_count
            bucket_rows_with_values = valued_rows[start:end]
            bucket_rows = [row for _value, row in bucket_rows_with_values]
            lower = bucket_rows_with_values[0][0]
            upper = bucket_rows_with_values[-1][0]
            output.append(
                (
                    FeatureBucket(
                        feature_name=feature_name,
                        bucket_name=_bucket_name(index, actual_bucket_count),
                        lower_bound=lower,
                        upper_bound=upper,
                        row_count=len(bucket_rows),
                        token_count=len({row.token_mint for row in bucket_rows}),
                    ),
                    bucket_rows,
                )
            )
        return output

    def analyze_feature(
        self,
        rows: list[ResearchDatasetRow],
        feature_name: str,
        bucket_count: int | None = None,
        window_name: str | None = None,
        horizon_name: str | None = None,
    ) -> FeatureReport:
        buckets = self.make_numeric_buckets(rows, feature_name, bucket_count=bucket_count)
        bucket_results: list[FeatureBucketResult] = []
        warning_flags: list[str] = ["exploratory_only_not_strategy"]
        if not buckets:
            warning_flags.append("insufficient_rows")
        if len(buckets) == 1 and buckets[0][0].metadata_json.get("low_variance_feature"):
            warning_flags.append("low_variance_feature")

        for bucket, bucket_rows in buckets:
            flags = []
            if len(bucket_rows) < self.min_bucket_size:
                flags.append("small_bucket")
            bucket_results.append(
                FeatureBucketResult(
                    feature_name=feature_name,
                    window_name=window_name,
                    horizon_name=horizon_name,
                    bucket=bucket,
                    outcome_summary=self.summarize_outcomes(bucket_rows),
                    warning_flags=flags,
                )
            )

        valid = [
            result for result in bucket_results
            if result.outcome_summary.avg_forward_return is not None
        ]
        best = max(valid, key=lambda result: result.outcome_summary.avg_forward_return, default=None)
        worst = min(valid, key=lambda result: result.outcome_summary.avg_forward_return, default=None)
        spread_avg = None
        spread_median = None
        if best and worst:
            spread_avg = best.outcome_summary.avg_forward_return - worst.outcome_summary.avg_forward_return
            if best.outcome_summary.median_forward_return is not None and worst.outcome_summary.median_forward_return is not None:
                spread_median = best.outcome_summary.median_forward_return - worst.outcome_summary.median_forward_return

        return FeatureReport(
            feature_name=feature_name,
            row_count=len(rows),
            bucket_count=len(bucket_results),
            best_bucket_name=best.bucket.bucket_name if best else None,
            worst_bucket_name=worst.bucket.bucket_name if worst else None,
            spread_avg_forward_return=spread_avg,
            spread_median_forward_return=spread_median,
            bucket_results=bucket_results,
            warning_flags=warning_flags,
            metadata_json={"exploratory_only_not_strategy": True},
        )

    def analyze(
        self,
        rows: list[ResearchDatasetRow],
        feature_names: list[str] | None = None,
        token_mints: list[str] | None = None,
        window_names: list[str] | None = None,
        horizon_names: list[str] | None = None,
    ) -> BaselineEdgeReport:
        filtered = self.filter_dataset_rows(
            rows,
            token_mints=token_mints,
            window_names=window_names,
            horizon_names=horizon_names,
            min_label_quality=self.min_label_quality,
            require_forward_return=self.require_forward_return,
        )
        features = feature_names or self.default_feature_names()
        feature_reports = [
            self.analyze_feature(
                filtered,
                feature,
                bucket_count=self.bucket_count,
                window_name=window_names[0] if window_names and len(window_names) == 1 else None,
                horizon_name=horizon_names[0] if horizon_names and len(horizon_names) == 1 else None,
            )
            for feature in features
        ]
        report = BaselineEdgeReport(
            report_id=make_report_id(),
            created_at=datetime.now(timezone.utc).isoformat(),
            dataset_path="data/backtests/research_dataset.jsonl",
            row_count=len(rows),
            filtered_row_count=len(filtered),
            token_count=len({row.token_mint for row in filtered}),
            window_counts=dict(sorted(Counter(row.window_name for row in filtered).items())),
            horizon_counts=dict(sorted(Counter(row.horizon_name for row in filtered).items())),
            label_quality_counts=dict(sorted(Counter(row.label_quality for row in filtered).items())),
            feature_reports=feature_reports,
            warning_flags=[
                "exploratory_report_not_trading_signal",
                "no_walk_forward_validation_yet",
                "heuristic_trade_labels_v0",
            ],
            metadata_json={
                "analyzer_version": "baseline_edge_analyzer_v0",
                "min_bucket_size": self.min_bucket_size,
                "bucket_count": self.bucket_count,
                "min_label_quality": self.min_label_quality,
                "require_forward_return": self.require_forward_return,
            },
        )
        report.top_findings = self._top_findings(feature_reports)
        return report

    def _top_findings(self, reports: list[FeatureReport]) -> list[str]:
        ranked = [
            report for report in reports
            if report.bucket_count >= 2 and report.spread_avg_forward_return is not None
        ]
        ranked.sort(key=lambda report: report.spread_avg_forward_return or 0.0, reverse=True)
        return [
            (
                f"Exploratory: {report.feature_name} showed avg forward-return spread "
                f"{report.spread_avg_forward_return:.4f} between {report.best_bucket_name} "
                f"and {report.worst_bucket_name}; requires backtest and walk-forward validation."
            )
            for report in ranked[:5]
        ]


def _bucket_name(index: int, bucket_count: int) -> str:
    if bucket_count == 5:
        return ["q1_low", "q2", "q3", "q4", "q5_high"][index]
    if index == 0:
        return "q1_low"
    if index == bucket_count - 1:
        return f"q{bucket_count}_high"
    return f"q{index + 1}"
