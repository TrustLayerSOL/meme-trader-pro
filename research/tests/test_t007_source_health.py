from research.mtp_research.validation.t007_source_health import T007SourceHealth


def test_required_lane_blocks_when_queue_drops():
    health = T007SourceHealth.default()
    lane = health.ensure_lane("pump_transaction_subscribe")
    lane.mark_connected(now=1.0)
    lane.record_message(decoded=True, now=2.0)
    lane.record_queue(size=10, dropped=1)
    assert health.ready() is False
    assert any("queue_dropped" in reason for reason in health.blocking_reasons())


def test_optional_bounded_replay_does_not_block_readiness():
    health = T007SourceHealth.default()
    for name, lane in health.lanes.items():
        if name != "bounded_readonly_replay":
            lane.mark_connected(now=1.0)
    health.ensure_lane("bounded_readonly_replay", required=False).mark_stalled("idle")
    assert health.ready() is True
