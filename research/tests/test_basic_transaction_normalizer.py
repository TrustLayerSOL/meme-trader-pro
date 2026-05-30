from datetime import datetime, timezone

from research.mtp_research.ingestion.basic_transaction_normalizer import (
    raw_transaction_to_observed_event,
)
from research.mtp_research.ingestion.raw_transaction_store import RawTransactionRecord


def test_basic_normalizer_converts_raw_transaction_to_observed_event() -> None:
    raw = RawTransactionRecord(
        signature="sig-1",
        slot=1,
        block_time=100,
        success=True,
        address="address-1",
        role="wallet",
        token_mint="mint-1",
        fetched_at=datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc),
        raw_json={"signature": "sig-1"},
    )

    event = raw_transaction_to_observed_event(raw)

    assert event.event_type == "transaction_observed"
    assert event.signature == "sig-1"
    assert event.slot == 1
    assert event.block_time == 100
    assert event.token_mint == "mint-1"
    assert event.metadata_json["address"] == "address-1"
    assert event.metadata_json["role"] == "wallet"
    assert event.metadata_json["success"] is True
