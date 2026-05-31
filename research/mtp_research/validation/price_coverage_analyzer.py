"""Analyze local price proxy coverage before scaling evidence backfills."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone

from research.mtp_research.ingestion.normalization_models import NormalizedEvent
from research.mtp_research.validation.outcome_models import OutcomeLabel
from research.mtp_research.validation.price_coverage_models import (
    PriceCoverageByToken,
    PriceCoverageReport,
    make_price_coverage_report_id,
)


TRADE_EVENT_TYPES = {"possible_buy", "possible_sell"}


class PriceCoverageAnalyzer:
    def build_report(
        self,
        events: list[NormalizedEvent],
        outcome_labels: list[OutcomeLabel] | None = None,
    ) -> PriceCoverageReport:
        labels = outcome_labels or []
        priced_events = [event for event in events if _has_price(event)]
        event_type_counts = Counter(event.event_type for event in events)
        priced_event_type_counts = Counter(event.event_type for event in priced_events)
        by_token = self.summarize_by_token(events)
        label_quality_counts = Counter(label.label_quality for label in labels)
        likely_no_price_causes = self.count_likely_no_price_causes(labels)
        report = PriceCoverageReport(
            report_id=make_price_coverage_report_id(),
            created_at=datetime.now(timezone.utc).isoformat(),
            event_count=len(events),
            events_with_price_quote=len(priced_events),
            price_coverage_rate=_ratio(len(priced_events), len(events)),
            token_count=len({event.token_mint for event in events if event.token_mint}),
            tokens_with_price=sum(1 for token in by_token if token.events_with_price_quote > 0),
            event_type_counts=dict(sorted(event_type_counts.items())),
            priced_event_type_counts=dict(sorted(priced_event_type_counts.items())),
            by_token=by_token,
            no_price_label_count=sum(1 for label in labels if label.label_quality == "no_price"),
            label_quality_counts=dict(sorted(label_quality_counts.items())),
            likely_no_price_causes=likely_no_price_causes,
        )
        if report.price_coverage_rate is not None and report.price_coverage_rate < 0.25:
            report.warning_flags.append("low_price_coverage")
        for event_type in TRADE_EVENT_TYPES:
            total = report.event_type_counts.get(event_type, 0)
            priced = report.priced_event_type_counts.get(event_type, 0)
            if total and (priced / total) < 0.5:
                report.warning_flags.append(f"low_{event_type}_price_coverage")
        if likely_no_price_causes.get("missing_entry_price", 0) > 0:
            report.warning_flags.append("missing_entry_price_drives_no_price")
        report.recommended_next_actions = self.recommend_next_actions(report)
        return report

    def summarize_by_token(self, events: list[NormalizedEvent]) -> list[PriceCoverageByToken]:
        grouped: dict[str, list[NormalizedEvent]] = defaultdict(list)
        for event in events:
            if event.token_mint:
                grouped[event.token_mint].append(event)

        summaries: list[PriceCoverageByToken] = []
        for token_mint, token_events in grouped.items():
            priced_events = [event for event in token_events if _has_price(event)]
            prices = [event.price_quote for event in priced_events if event.price_quote is not None]
            priced_ts = [event.block_time for event in priced_events if event.block_time is not None]
            warning_flags: list[str] = []
            coverage = _ratio(len(priced_events), len(token_events))
            if coverage is not None and coverage < 0.25:
                warning_flags.append("low_token_price_coverage")
            summaries.append(
                PriceCoverageByToken(
                    token_mint=token_mint,
                    event_count=len(token_events),
                    events_with_price_quote=len(priced_events),
                    price_coverage_rate=coverage,
                    min_price_quote=min(prices) if prices else None,
                    max_price_quote=max(prices) if prices else None,
                    first_price_ts=min(priced_ts) if priced_ts else None,
                    last_price_ts=max(priced_ts) if priced_ts else None,
                    event_type_counts=dict(sorted(Counter(event.event_type for event in token_events).items())),
                    priced_event_type_counts=dict(sorted(Counter(event.event_type for event in priced_events).items())),
                    warning_flags=warning_flags,
                )
            )
        return sorted(summaries, key=lambda item: (item.events_with_price_quote == 0, item.token_mint))

    def count_likely_no_price_causes(self, labels: list[OutcomeLabel]) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for label in labels:
            if label.label_quality != "no_price":
                continue
            if label.entry_price is None:
                counts["missing_entry_price"] += 1
            if label.end_price is None:
                counts["missing_end_price"] += 1
            if label.price_points_count == 0:
                counts["no_price_points_in_horizon"] += 1
            if label.entry_price_source == "missing":
                counts["missing_entry_price_source"] += 1
        return dict(sorted(counts.items()))

    def recommend_next_actions(self, report: PriceCoverageReport) -> list[str]:
        actions: list[str] = []
        if any(warning.startswith("low_possible_") for warning in report.warning_flags):
            actions.append("improve trade event normalizer price inference")
        if report.likely_no_price_causes.get("missing_entry_price", 0):
            actions.append("inspect missing entry prices and consider diagnostic nearest-price fallback")
        if report.likely_no_price_causes.get("no_price_points_in_horizon", 0):
            actions.append("increase backfill horizon or candidate transaction sample after target quality is confirmed")
        if report.event_type_counts.get("transaction_observed", 0) and not report.priced_event_type_counts.get("transaction_observed", 0):
            actions.append("ignore transaction_observed events for price labeling")
        if any(token.events_with_price_quote == 0 for token in report.by_token):
            actions.append("inspect raw token balance deltas for tokens with no priced events")
        return actions or ["price coverage is adequate for current diagnostic sample"]


def _has_price(event: NormalizedEvent) -> bool:
    return event.price_quote is not None and event.price_quote > 0


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator
