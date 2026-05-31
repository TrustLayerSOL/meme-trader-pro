"""Diagnostic price-quality gate for research rows."""

from __future__ import annotations

from collections import Counter

from research.mtp_research.validation.price_quality_models import (
    PriceQualityConfig,
    PriceQualityDecision,
    PriceQualityGateReport,
    make_price_quality_gate_report_id,
    utc_now_iso,
)
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow


LABEL_QUALITY_RANK = {
    "unknown": 0,
    "no_price": 0,
    "no_future_events": 0,
    "sparse": 1,
    "good": 2,
}


class PriceQualityGate:
    """Filter rows into a stricter diagnostic price-quality subset."""

    def evaluate_row(
        self,
        row: ResearchDatasetRow,
        config: PriceQualityConfig,
    ) -> PriceQualityDecision:
        reasons: list[str] = []
        entry_staleness = _entry_staleness(row)

        if _label_rank(row.label_quality) < _label_rank(config.min_label_quality):
            reasons.append("failed_label_quality")
        if row.entry_price is None:
            reasons.append("missing_entry_price")
        if row.forward_return is None:
            reasons.append("missing_forward_return")
        if row.entry_price_source == "nearest_research_fallback" and not config.allow_nearest_fallback:
            reasons.append("nearest_fallback_disallowed")
        if entry_staleness is not None and entry_staleness > config.max_entry_staleness_sec:
            reasons.append("stale_entry_price")
        if row.price_points_count < config.min_future_price_points:
            reasons.append("insufficient_future_price_points")
        if row.no_future_liquidity and not config.allow_no_future_liquidity:
            reasons.append("no_future_liquidity_disallowed")
        if row.rug_like_drop and not config.allow_rug_like_drop:
            reasons.append("rug_like_drop_disallowed")
        if (
            config.max_forward_return_abs is not None
            and row.forward_return is not None
            and abs(row.forward_return) > config.max_forward_return_abs
        ):
            reasons.append("extreme_forward_return")
        if (
            config.max_runup_abs is not None
            and row.max_runup is not None
            and abs(row.max_runup) > config.max_runup_abs
        ):
            reasons.append("extreme_runup")

        return PriceQualityDecision(
            row_id=row.row_id,
            token_mint=row.token_mint,
            passed=not reasons,
            reasons_failed=reasons,
            warning_flags=list(reasons),
            entry_staleness_sec=entry_staleness,
            future_price_points=row.price_points_count,
            entry_price_source=row.entry_price_source,
            label_quality=row.label_quality,
            metadata_json={
                "snapshot_ts": row.snapshot_ts,
                "entry_price_ts": row.entry_price_ts,
                "forward_return": row.forward_return,
                "max_runup": row.max_runup,
            },
        )

    def filter_rows(
        self,
        rows: list[ResearchDatasetRow],
        config: PriceQualityConfig,
        dataset_path: str = "",
    ) -> tuple[list[ResearchDatasetRow], list[PriceQualityDecision], PriceQualityGateReport]:
        decisions = [self.evaluate_row(row, config) for row in rows]
        passed_ids = {decision.row_id for decision in decisions if decision.passed}
        passed_rows = [row for row in rows if row.row_id in passed_ids]
        report = self.build_report(rows, decisions, passed_rows, config, dataset_path)
        return passed_rows, decisions, report

    def build_report(
        self,
        rows: list[ResearchDatasetRow],
        decisions: list[PriceQualityDecision],
        passed_rows: list[ResearchDatasetRow],
        config: PriceQualityConfig,
        dataset_path: str,
    ) -> PriceQualityGateReport:
        failure_reasons: Counter[str] = Counter()
        for decision in decisions:
            failure_reasons.update(decision.reasons_failed)

        input_count = len(rows)
        passed_count = len(passed_rows)
        return PriceQualityGateReport(
            report_id=make_price_quality_gate_report_id(),
            created_at=utc_now_iso(),
            dataset_path=dataset_path,
            input_row_count=input_count,
            passed_row_count=passed_count,
            failed_row_count=input_count - passed_count,
            pass_rate=(passed_count / input_count) if input_count else None,
            token_count_input=len({row.token_mint for row in rows}),
            token_count_passed=len({row.token_mint for row in passed_rows}),
            failure_reason_counts=dict(sorted(failure_reasons.items())),
            entry_source_counts_input=dict(sorted(Counter(row.entry_price_source or "missing" for row in rows).items())),
            entry_source_counts_passed=dict(sorted(Counter(row.entry_price_source or "missing" for row in passed_rows).items())),
            label_quality_counts_input=dict(sorted(Counter(row.label_quality for row in rows).items())),
            label_quality_counts_passed=dict(sorted(Counter(row.label_quality for row in passed_rows).items())),
            config=config,
            warning_flags=["diagnostic_only_not_trading_signal"],
        )


def _entry_staleness(row: ResearchDatasetRow) -> int | None:
    if row.snapshot_ts is None or row.entry_price_ts is None:
        return None
    return abs(row.snapshot_ts - row.entry_price_ts)


def _label_rank(label_quality: str | None) -> int:
    return LABEL_QUALITY_RANK.get(label_quality or "unknown", 0)
