from __future__ import annotations

import pytest

from research.mtp_research.validation.t007_source_gap_backfill import (
    ReadOnlyBackfillConfig,
    SourceLaneRuntime,
    evaluate_source_gap_health,
)


def test_source_gap_health_passes_when_disconnects_are_backfilled() -> None:
    result = evaluate_source_gap_health(
        [
            SourceLaneRuntime(
                lane="pumpswap_create_pool_lane",
                requested_duration_seconds=600,
                actual_duration_seconds=599,
                reconnect_count=2,
                disconnected_intervals=[{"start_slot": 10, "end_slot": 20, "backfill_status": "succeeded"}],
            )
        ]
    )

    assert result["source_gap_gate_passed"] is True
    assert result["unbackfilled_gap_count"] == 0
    assert result["lane_statuses"][0]["duration_ratio"] >= 0.98


def test_source_gap_health_blocks_unbackfilled_gaps() -> None:
    result = evaluate_source_gap_health(
        [
            SourceLaneRuntime(
                lane="pumpswap_create_pool_lane",
                requested_duration_seconds=600,
                actual_duration_seconds=540,
                reconnect_count=1,
                disconnected_intervals=[{"start_slot": 10, "end_slot": 20, "backfill_status": "not_attempted"}],
            )
        ]
    )

    assert result["source_gap_gate_passed"] is False
    assert result["unbackfilled_gap_count"] == 1
    assert "pumpswap_create_pool_lane_duration_ratio_below_0_98" in result["blocking_reasons"]
    assert "unbackfilled_source_gap" in result["blocking_reasons"]


def test_read_only_backfill_requires_explicit_flag_and_cap() -> None:
    assert ReadOnlyBackfillConfig(enabled=False).enabled is False
    with pytest.raises(ValueError, match="explicit"):
        ReadOnlyBackfillConfig(enabled=True, explicit_read_only_rpc_flag=False)
    with pytest.raises(ValueError, match="max_signatures"):
        ReadOnlyBackfillConfig(enabled=True, explicit_read_only_rpc_flag=True, max_signatures=101)
