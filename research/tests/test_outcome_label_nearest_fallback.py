from research.mtp_research.features.feature_models import FeatureSnapshot
from research.mtp_research.ingestion.normalization_models import NormalizedEvent
from research.mtp_research.validation.outcome_label_builder import OutcomeLabelBuilder
from research.mtp_research.validation.outcome_models import OutcomeHorizon


def test_outcome_label_builder_marks_nearest_research_fallback() -> None:
    snapshot = FeatureSnapshot(
        snapshot_id="snapshot-1",
        token_mint="token-a",
        snapshot_ts=100,
        window_name="1m",
        window_seconds=60,
    )
    events = [
        NormalizedEvent(
            event_id="e1",
            signature="sig-1",
            slot=1,
            block_time=110,
            event_type="possible_buy",
            token_mint="token-a",
            price_quote=1.0,
        ),
        NormalizedEvent(
            event_id="e2",
            signature="sig-2",
            slot=2,
            block_time=120,
            event_type="possible_sell",
            token_mint="token-a",
            price_quote=1.2,
        ),
    ]
    builder = OutcomeLabelBuilder(
        horizons=[OutcomeHorizon("1m", 60)],
        entry_max_staleness_sec=5,
        allow_nearest_entry_fallback=True,
        nearest_entry_max_staleness_sec=30,
    )

    label = builder.build_labels([snapshot], events)[0]

    assert label.entry_price == 1.0
    assert label.entry_price_source == "nearest_research_fallback"
    assert "entry_price_uses_nearest_research_fallback" in label.metadata_json["warning_flags"]
