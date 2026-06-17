from research.mtp_research.validation.t007_decision_snapshot import build_decision_snapshot
from research.mtp_research.validation.t007_event_store import T007EventStore


def test_decision_snapshot_excludes_replay_and_future_events(tmp_path):
    db = tmp_path / "lifecycle.sqlite"
    store = T007EventStore(db)
    store.append_domain_event({"event_type": "pump_birth_verified", "mint": "Mint111", "feature_observed_at": 1.0, "decision_time_safe": True})
    store.append_domain_event({"event_type": "curve_state_decoded", "mint": "Mint111", "feature_observed_at": 2.0, "decision_time_safe": True})
    store.append_domain_event({"event_type": "trade_flow_window_updated", "mint": "Mint111", "feature_observed_at": 3.0, "decision_time_safe": True})
    store.append_domain_event({"event_type": "pumpswap_pool_verified", "mint": "Mint111", "feature_observed_at": 4.0, "decision_time_safe": True})
    store.append_domain_event({"event_type": "replay_birth_context_seen", "mint": "Mint111", "feature_observed_at": 5.0, "replay_source": True})
    store.append_domain_event({"event_type": "quote_observation_seen", "mint": "Mint111", "feature_observed_at": 99.0, "decision_time_safe": True})
    store.close()
    snapshot = build_decision_snapshot(db, mint="Mint111", cutoff_time=4.5)
    assert snapshot.decision_time_safe is True
    assert "replay_birth_context_seen" not in snapshot.features
    assert "quote_observation_seen" not in snapshot.features
