import sqlite3

from research.mtp_research.validation.t007_event_store import T007EventStore


def test_event_store_writes_domain_events_and_identity_indexes(tmp_path):
    db = tmp_path / "lifecycle.sqlite"
    store = T007EventStore(db)
    store.append_domain_event({
        "collector_run_id": "run-1",
        "event_type": "pump_birth_verified",
        "mint": "Mint111",
        "signature": "sig1",
        "feature_observed_at": 1.0,
        "decision_time_safe": True,
    })
    store.append_domain_event({
        "collector_run_id": "run-1",
        "event_type": "pumpswap_pool_verified",
        "mint": "Mint111",
        "pool_address": "Pool111",
        "feature_observed_at": 2.0,
        "decision_time_safe": True,
    })
    store.close()
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM domain_events").fetchone()[0] == 2
        mint = connection.execute("SELECT migration_seen FROM mint_identity WHERE mint = 'Mint111'").fetchone()
        assert mint == (1,)
        pool = connection.execute("SELECT pool_verified FROM pool_identity WHERE pool_address = 'Pool111'").fetchone()
        assert pool == (1,)


def test_event_store_raw_source_envelope_is_append_only(tmp_path):
    db = tmp_path / "lifecycle.sqlite"
    store = T007EventStore(db)
    store.insert_raw_envelope({"collector_run_id": "run-1", "lane": "pump_transaction_subscribe", "signature": "sig1", "mint": "Mint111"})
    store.close()
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT lane FROM raw_source_envelopes").fetchone()[0] == "pump_transaction_subscribe"
