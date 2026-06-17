import sqlite3

from research.mtp_research.validation.t007_decision_snapshot import persist_hashed_decision_snapshot
from research.mtp_research.validation.t007_event_store import T007EventStore
from research.mtp_research.validation.t007_invariants import check_lifecycle_invariants
from research.mtp_research.validation.t007_proof_ladder import evaluate_l2_live_no_migration, evaluate_l3_controlled_migration
from research.mtp_research.validation.t007_run_manifest import RunManifest
from research.mtp_research.validation.t007_watcher_contract import production_readiness_from_watcher_payload


def test_event_store_schema_has_commitment_manifest_layout_and_snapshot_tables(tmp_path):
    db = tmp_path / 'state.sqlite'
    with sqlite3.connect(db) as connection:
        T007EventStore.initialize_schema(connection)
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert 'run_manifest' in tables
        assert 'protocol_layout_versions' in tables
        assert 'lifecycle_invariant_violations' in tables
        assert 'decision_snapshots' in tables
        raw_columns = {row[1] for row in connection.execute('PRAGMA table_info(raw_source_envelopes)')}
        assert 'observed_commitment' in raw_columns
        assert 'payload_hash' in raw_columns


def test_invariants_reject_decision_safe_replay_and_full_path_missing_flags():
    violations = check_lifecycle_invariants({'decision_time_safe': True, 'replay_source': True})
    assert any(v.code == 'decision_safe_replay_source' for v in violations)
    violations = check_lifecycle_invariants({'decision_safe_full_path': True, 'birth_verified': True})
    assert any(v.code == 'full_path_missing_required_flags' for v in violations)


def test_proof_ladder_l2_and_l3_semantics():
    l2 = evaluate_l2_live_no_migration({
        'event_first_sqlite_enabled': True,
        'db_ledger_consistent': True,
        'verified_births': 5,
        'curve_state_decoded': 5,
        'market_cap_available': 5,
        'required_watcher_fields_present': True,
    })
    assert l2.passed is True
    l3 = evaluate_l3_controlled_migration({
        'event_first_sqlite_enabled': True,
        'db_ledger_consistent': True,
        'verified_births': 5,
        'curve_state_decoded': 5,
        'market_cap_available': 5,
        'required_watcher_fields_present': True,
        'global_migration_mints_seen': 1,
        'decision_safe_full_paths': 0,
    })
    assert l3.passed is False
    assert 'no_decision_safe_full_path_migrations' in l3.blockers


def test_watcher_gate_requires_manifest_layout_registry_and_latency_histograms():
    result = production_readiness_from_watcher_payload({
        'event_first_sqlite_enabled': True,
        'db_ledger_consistent': True,
        'verified_births': 5,
        'curve_state_decoded': 5,
        'market_cap_available': 5,
        'required_watcher_fields_present': True,
    })
    assert 'run_manifest_missing' in result['blockers']
    assert 'protocol_layout_registry_missing' in result['blockers']
    assert 'latency_histograms_missing' in result['blockers']


def test_run_manifest_is_hashable_and_reproducible():
    manifest = RunManifest(collector_run_id='run-1', commitment_config='processed')
    payload = manifest.as_dict()
    assert payload['collector_run_id'] == 'run-1'
    assert payload['manifest_hash']


def test_hashed_decision_snapshot_persists_without_execution_fields(tmp_path):
    db = tmp_path / 'state.sqlite'
    store = T007EventStore(db)
    store.append_domain_event({'event_type': 'pump_birth_verified', 'mint': 'Mint111', 'feature_observed_at': 1.0, 'decision_time_safe': True})
    store.close()
    payload = persist_hashed_decision_snapshot(db, mint='Mint111', cutoff_time=2.0)
    assert payload['snapshot_id']
    assert payload['snapshot_payload_hash']
    with sqlite3.connect(db) as connection:
        assert connection.execute('SELECT COUNT(*) FROM decision_snapshots').fetchone()[0] == 1
