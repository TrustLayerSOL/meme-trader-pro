"""Offline reviewer for extreme selected-row price paths."""

from __future__ import annotations

from collections import Counter

from research.mtp_research.backtest.rule_backtest_models import RuleDefinition
from research.mtp_research.backtest.rule_backtester import RuleBacktester
from research.mtp_research.ingestion.normalization_models import NormalizedEvent
from research.mtp_research.validation.outlier_price_path_models import (
    OutlierPricePathReport,
    OutlierPricePathReview,
    PricePathPoint,
    make_outlier_price_path_report_id,
    utc_now_iso,
)
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow


class OutlierPricePathReviewer:
    def select_outlier_rows(
        self,
        rows: list[ResearchDatasetRow],
        rules: list[RuleDefinition],
        rule_ids: list[str],
        return_threshold: float = 1.0,
        limit_per_rule: int = 25,
    ) -> list[tuple[str, ResearchDatasetRow]]:
        backtester = RuleBacktester()
        rules_by_id = {rule.rule_id: rule for rule in rules}
        selected: list[tuple[str, ResearchDatasetRow]] = []
        for rule_id in rule_ids:
            rule = rules_by_id.get(rule_id)
            if rule is None:
                continue
            matching = [
                row for row in rows
                if row.forward_return is not None
                and row.forward_return >= return_threshold
                and backtester.row_passes_rule(row, rule)
            ]
            for row in sorted(matching, key=lambda item: item.forward_return or 0.0, reverse=True)[:limit_per_rule]:
                selected.append((rule_id, row))
        return selected

    def build_price_path(
        self,
        token_mint: str,
        snapshot_ts: int,
        horizon_seconds: int,
        events: list[NormalizedEvent],
        pre_window_seconds: int = 300,
        post_window_seconds: int | None = None,
    ) -> list[PricePathPoint]:
        end_ts = snapshot_ts + (post_window_seconds if post_window_seconds is not None else horizon_seconds)
        start_ts = snapshot_ts - pre_window_seconds
        points: list[PricePathPoint] = []
        for event in events:
            if event.token_mint != token_mint:
                continue
            if event.block_time is None or event.price_quote is None or event.price_quote <= 0:
                continue
            if not (start_ts <= event.block_time <= end_ts):
                continue
            points.append(
                PricePathPoint(
                    token_mint=token_mint,
                    ts=event.block_time,
                    price_quote=event.price_quote,
                    event_id=event.event_id,
                    event_type=event.event_type,
                    signature=event.signature,
                    actor=event.actor,
                    side=event.side,
                    base_qty=event.base_qty,
                    quote_qty=event.quote_qty,
                    confidence=event.metadata_json.get("confidence"),
                    entry_distance_sec=abs(event.block_time - snapshot_ts),
                    end_distance_sec=abs(event.block_time - (snapshot_ts + horizon_seconds)),
                    metadata_json=dict(event.metadata_json),
                )
            )
        return sorted(points, key=lambda item: (item.ts, item.event_id or ""))

    def review_row(
        self,
        rule_id: str,
        row: ResearchDatasetRow,
        events: list[NormalizedEvent],
        pre_window_seconds: int = 300,
        post_window_seconds: int | None = None,
    ) -> OutlierPricePathReview:
        points = self.build_price_path(
            row.token_mint,
            row.snapshot_ts,
            row.horizon_seconds,
            events,
            pre_window_seconds=pre_window_seconds,
            post_window_seconds=post_window_seconds,
        )
        before = [point for point in points if point.ts <= row.snapshot_ts]
        after = [point for point in points if point.ts > row.snapshot_ts]
        prices = [point.price_quote for point in points]
        gaps = [
            right.ts - left.ts
            for left, right in zip(points, points[1:], strict=False)
        ]
        recomputed = None
        if row.entry_price and row.end_price:
            recomputed = (row.end_price - row.entry_price) / row.entry_price
        elif points:
            first_after = after[0] if after else points[0]
            last_point = points[-1]
            if first_after.price_quote > 0:
                recomputed = (last_point.price_quote - first_after.price_quote) / first_after.price_quote
        review = OutlierPricePathReview(
            row_id=row.row_id,
            rule_id=rule_id,
            token_mint=row.token_mint,
            snapshot_ts=row.snapshot_ts,
            horizon_name=row.horizon_name,
            horizon_seconds=row.horizon_seconds,
            entry_price=row.entry_price,
            entry_price_ts=row.entry_price_ts,
            entry_price_source=row.entry_price_source,
            end_price=row.end_price,
            end_price_ts=row.end_price_ts,
            forward_return=row.forward_return,
            max_runup=row.max_runup,
            max_drawdown=row.max_drawdown,
            local_price_points_before=len(before),
            local_price_points_after=len(after),
            local_price_points_total=len(points),
            nearest_price_before_ts=before[-1].ts if before else None,
            nearest_price_after_ts=after[0].ts if after else None,
            max_gap_between_price_points_sec=max(gaps) if gaps else None,
            price_path_min=min(prices) if prices else None,
            price_path_max=max(prices) if prices else None,
            price_path_return_recomputed=recomputed,
            price_path_points=points,
            metadata_json={"pre_window_seconds": pre_window_seconds, "post_window_seconds": post_window_seconds},
        )
        review.outlier_classification = self.classify_review(review)
        review.warning_flags = self._warnings(review)
        return review

    def classify_review(self, review: OutlierPricePathReview) -> str:
        if review.entry_price_source == "nearest_research_fallback":
            return "fallback_dependent"
        if review.entry_price is None or review.end_price is None:
            return "unusable_for_validation"
        if review.local_price_points_total == 0:
            return "unusable_for_validation"
        if review.entry_price_ts is not None and abs(review.snapshot_ts - review.entry_price_ts) > 300:
            return "stale_or_misaligned_entry"
        if self._return_mismatch(review):
            return "unusable_for_validation"
        if review.local_price_points_after < 2:
            return "isolated_price_print"
        if (
            review.max_gap_between_price_points_sec is not None
            and review.max_gap_between_price_points_sec > max(300, review.horizon_seconds // 2)
        ):
            return "isolated_price_print"
        if (
            review.price_path_min is not None
            and review.price_path_min > 0
            and review.price_path_max is not None
            and review.price_path_max / review.price_path_min > 20
            and review.local_price_points_total < 5
        ):
            return "suspicious_price_jump"
        if review.local_price_points_after >= 3 and not self._return_mismatch(review, tolerance=0.25):
            return "plausible_price_path"
        return "unknown"

    def build_report(
        self,
        rows: list[ResearchDatasetRow],
        events: list[NormalizedEvent],
        rules: list[RuleDefinition],
        rule_ids: list[str],
        dataset_path: str,
        events_path: str,
        return_threshold: float = 1.0,
        limit_per_rule: int = 25,
        pre_window_seconds: int = 300,
        post_window_seconds: int | None = None,
    ) -> OutlierPricePathReport:
        selected = self.select_outlier_rows(
            rows,
            rules,
            rule_ids,
            return_threshold=return_threshold,
            limit_per_rule=limit_per_rule,
        )
        reviews = [
            self.review_row(
                rule_id,
                row,
                events,
                pre_window_seconds=pre_window_seconds,
                post_window_seconds=post_window_seconds,
            )
            for rule_id, row in selected
        ]
        classifications = Counter(review.outlier_classification for review in reviews)
        token_counts = Counter(review.token_mint for review in reviews)
        report = OutlierPricePathReport(
            report_id=make_outlier_price_path_report_id(),
            created_at=utc_now_iso(),
            dataset_path=dataset_path,
            events_path=events_path,
            reviewed_rule_ids=list(rule_ids),
            reviewed_count=len(reviews),
            plausible_count=classifications.get("plausible_price_path", 0),
            suspicious_count=classifications.get("suspicious_price_jump", 0),
            unusable_count=classifications.get("unusable_for_validation", 0),
            fallback_dependent_count=classifications.get("fallback_dependent", 0),
            isolated_price_print_count=classifications.get("isolated_price_print", 0),
            classification_counts=dict(sorted(classifications.items())),
            token_counts=dict(sorted(token_counts.items())),
            warning_flags=["diagnostic_only_not_trading_signal"],
            reviews=reviews,
            metadata_json={"return_threshold": return_threshold, "limit_per_rule": limit_per_rule},
        )
        if report.token_counts and max(report.token_counts.values()) / max(1, report.reviewed_count) > 0.5:
            report.warning_flags.append("token_concentration")
        report.recommended_next_action = self.recommend_next_action(report)
        return report

    def recommend_next_action(self, report: OutlierPricePathReport) -> str:
        if report.reviewed_count == 0:
            return "manual_review_required"
        counts = report.classification_counts
        majority = report.reviewed_count / 2
        if counts.get("plausible_price_path", 0) > majority:
            return "bounded_evidence_expansion_with_outlier_separation"
        if counts.get("fallback_dependent", 0) > majority:
            return "improve_clean_price_inference_before_scaling"
        if (counts.get("isolated_price_print", 0) + counts.get("suspicious_price_jump", 0)) > majority:
            return "tighten_price_quality_filters_before_scaling"
        if counts.get("unusable_for_validation", 0) >= max(1, report.reviewed_count * 0.25):
            return "exclude_unusable_outliers_from_diagnostic_metrics"
        return "manual_review_required"

    def _warnings(self, review: OutlierPricePathReview) -> list[str]:
        warnings: list[str] = ["diagnostic_only_not_trading_signal"]
        if review.entry_price_source == "nearest_research_fallback":
            warnings.append("nearest_research_fallback_entry")
        if review.local_price_points_after < 2:
            warnings.append("insufficient_future_price_points")
        if review.outlier_classification == "isolated_price_print":
            warnings.append("isolated_price_print")
        if review.outlier_classification == "suspicious_price_jump":
            warnings.append("suspicious_price_jump")
        if review.outlier_classification == "stale_or_misaligned_entry":
            warnings.append("stale_or_misaligned_entry")
        if self._return_mismatch(review):
            warnings.append("return_mismatch")
        return warnings

    def _return_mismatch(self, review: OutlierPricePathReview, tolerance: float = 0.5) -> bool:
        if review.forward_return is None or review.price_path_return_recomputed is None:
            return False
        return abs(review.forward_return - review.price_path_return_recomputed) > tolerance
