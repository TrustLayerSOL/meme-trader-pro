from research.mtp_research.validation.launch_timestamp_confidence import (
    confidence_rank,
    classify_launch_timestamp_source,
    is_verified_launch_timestamp,
)


def test_event_inferred_launch_timestamp_is_classified_as_inferred() -> None:
    source = classify_launch_timestamp_source(
        {"metadata_json": {"launch_timestamp_quality": "first_observed_event_not_verified_pair_creation"}}
    )

    assert source == "inferred_first_normalized_event"
    assert is_verified_launch_timestamp(source) is False


def test_verified_pair_creation_ranks_above_inferred_normalized_event() -> None:
    assert confidence_rank("verified_pair_creation") > confidence_rank("inferred_first_normalized_event")
    assert is_verified_launch_timestamp("verified_pair_creation") is True


def test_registry_first_seen_is_classified_as_inferred() -> None:
    assert classify_launch_timestamp_source({"source": "dexscreener_real", "metadata_json": {}}) == "inferred_registry_first_seen"
