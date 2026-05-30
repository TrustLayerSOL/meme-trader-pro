"""Join feature snapshots to outcome labels for research datasets."""

from __future__ import annotations

from research.mtp_research.features.feature_models import FeatureSnapshot
from research.mtp_research.validation.outcome_models import OutcomeLabel
from research.mtp_research.validation.research_dataset_models import (
    ResearchDatasetRow,
    make_research_row_id,
)


LABEL_QUALITY_RANK = {
    "unknown": 0,
    "no_price": 1,
    "no_future_events": 2,
    "sparse": 3,
    "good": 4,
}


class ResearchDatasetBuilder:
    """Build clean joined rows from local features and local labels."""

    def join_snapshots_to_outcomes(
        self,
        snapshots: list[FeatureSnapshot],
        labels: list[OutcomeLabel],
        token_mints: list[str] | None = None,
        window_names: list[str] | None = None,
        horizon_names: list[str] | None = None,
        min_label_quality: str | None = None,
    ) -> list[ResearchDatasetRow]:
        labels_by_snapshot = {}
        for label in labels:
            labels_by_snapshot.setdefault(label.snapshot_id, []).append(label)

        rows: list[ResearchDatasetRow] = []
        for snapshot in snapshots:
            for label in labels_by_snapshot.get(snapshot.snapshot_id, []):
                if label.token_mint != snapshot.token_mint:
                    continue
                if label.snapshot_ts != snapshot.snapshot_ts:
                    continue
                rows.append(self.snapshot_and_label_to_row(snapshot, label))

        return self.filter_rows(
            rows,
            token_mints=token_mints,
            window_names=window_names,
            horizon_names=horizon_names,
            min_label_quality=min_label_quality,
        )

    def snapshot_and_label_to_row(
        self,
        snapshot: FeatureSnapshot,
        label: OutcomeLabel,
    ) -> ResearchDatasetRow:
        return ResearchDatasetRow(
            row_id=make_research_row_id(snapshot.snapshot_id, label.outcome_id),
            snapshot_id=snapshot.snapshot_id,
            outcome_id=label.outcome_id,
            token_mint=snapshot.token_mint,
            snapshot_ts=snapshot.snapshot_ts,
            window_name=snapshot.window_name,
            window_seconds=snapshot.window_seconds,
            horizon_name=label.horizon_name,
            horizon_seconds=label.horizon_seconds,
            age_sec=snapshot.age_sec,
            venue=snapshot.venue,
            event_count=snapshot.event_count,
            possible_buy_count=snapshot.possible_buy_count,
            possible_sell_count=snapshot.possible_sell_count,
            token_accumulation_count=snapshot.token_accumulation_count,
            token_distribution_count=snapshot.token_distribution_count,
            unique_actor_count=snapshot.unique_actor_count,
            base_volume=snapshot.base_volume,
            quote_volume=snapshot.quote_volume,
            net_base_flow=snapshot.net_base_flow,
            net_quote_flow=snapshot.net_quote_flow,
            buy_sell_imbalance=snapshot.buy_sell_imbalance,
            confidence_weighted_buy_flow=snapshot.confidence_weighted_buy_flow,
            confidence_weighted_sell_flow=snapshot.confidence_weighted_sell_flow,
            confidence_weighted_net_flow=snapshot.confidence_weighted_net_flow,
            avg_event_confidence=snapshot.avg_event_confidence,
            max_event_confidence=snapshot.max_event_confidence,
            entry_price=label.entry_price,
            entry_price_ts=label.entry_price_ts,
            entry_price_source=label.entry_price_source,
            end_price=label.end_price,
            end_price_ts=label.end_price_ts,
            forward_return=label.forward_return,
            max_runup=label.max_runup,
            max_drawdown=label.max_drawdown,
            price_points_count=label.price_points_count,
            future_event_count=label.future_event_count,
            future_possible_buy_count=label.future_possible_buy_count,
            future_possible_sell_count=label.future_possible_sell_count,
            future_token_accumulation_count=label.future_token_accumulation_count,
            future_token_distribution_count=label.future_token_distribution_count,
            future_unique_actor_count=label.future_unique_actor_count,
            future_quote_volume=label.future_quote_volume,
            future_base_volume=label.future_base_volume,
            survived_horizon=label.survived_horizon,
            rug_like_drop=label.rug_like_drop,
            no_future_liquidity=label.no_future_liquidity,
            label_quality=label.label_quality,
            venue_counts=dict(snapshot.venue_counts),
            event_type_counts=dict(snapshot.event_type_counts),
            feature_metadata_json=dict(snapshot.metadata_json),
            outcome_metadata_json=dict(label.metadata_json),
            metadata_json={
                "builder_version": "research_dataset_builder_v0",
                "feature_snapshot_id": snapshot.snapshot_id,
                "outcome_label_id": label.outcome_id,
            },
        )

    def filter_rows(
        self,
        rows: list[ResearchDatasetRow],
        token_mints: list[str] | None = None,
        window_names: list[str] | None = None,
        horizon_names: list[str] | None = None,
        min_label_quality: str | None = None,
        require_entry_price: bool = False,
        require_forward_return: bool = False,
    ) -> list[ResearchDatasetRow]:
        token_set = set(token_mints or [])
        window_set = set(window_names or [])
        horizon_set = set(horizon_names or [])
        min_quality_rank = _quality_rank(min_label_quality) if min_label_quality else None
        output: list[ResearchDatasetRow] = []
        for row in rows:
            if token_set and row.token_mint not in token_set:
                continue
            if window_set and row.window_name not in window_set:
                continue
            if horizon_set and row.horizon_name not in horizon_set:
                continue
            if require_entry_price and row.entry_price is None:
                continue
            if require_forward_return and row.forward_return is None:
                continue
            if min_quality_rank is not None and _quality_rank(row.label_quality) < min_quality_rank:
                continue
            output.append(row)
        return output


def _quality_rank(label_quality: str | None) -> int:
    return LABEL_QUALITY_RANK.get(label_quality or "unknown", 0)
