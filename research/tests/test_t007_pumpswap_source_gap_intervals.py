from __future__ import annotations

from research.mtp_research.validation.helius_transaction_subscribe_source import HeliusPumpSwapTransactionSubscribeSource


def test_pumpswap_source_records_signature_bounded_gap_interval() -> None:
    source = HeliusPumpSwapTransactionSubscribeSource(websocket_url="ws://example", ws_connect=lambda *a, **k: None)

    source._record_seen_transaction_for_gap_tracking({"signature": "sig-before", "slot": 100, "received_at": 10.0})
    interval = source._start_source_gap_interval(RuntimeError("keepalive ping timeout"))
    assert interval["last_seen_signature_before_gap"] == "sig-before"
    assert interval["last_seen_slot_before_gap"] == 100
    assert interval["backfill_status"] == "not_attempted"

    source._record_seen_transaction_for_gap_tracking({"signature": "sig-after", "slot": 105, "received_at": 15.0})

    assert source.source_gap_intervals[0]["first_seen_signature_after_gap"] == "sig-after"
    assert source.source_gap_intervals[0]["first_seen_slot_after_gap"] == 105
    assert source.source_gap_intervals[0]["backfill_status"] == "not_attempted"
