import sqlite3

from research.mtp_research.validation.t007_db_readiness import build_db_readiness_summary
from research.mtp_research.validation.t007_production_event_bus import T007ProductionEventFirstWriter
from research.mtp_research.validation.t007_sqlite_writer import T007SqliteWriter
from research.mtp_research.validation.t007_watcher_contract import normalize_watcher_payload


def test_sqlite_writer_bootstraps_manifest_and_layouts_on_internal_db(tmp_path):
    writer = T007SqliteWriter(tmp_path, run_id='run-1', use_internal_db=True)
    writer.start()
    writer.bootstrap_run({'collector_run_id': 'run-1', 'run_id': 'run-1'})
    counts = writer.counts()
    assert counts['run_manifest'] == 1
    assert counts['protocol_layout_versions'] >= 2
    assert writer.db_path != tmp_path / 't007_lifecycle_state.sqlite'
    assert (tmp_path / 'canonical_sqlite_db_pointer.json').exists()
    writer.close()


def test_event_bus_exports_only_after_db_commit_and_adds_ids(tmp_path):
    bus = T007ProductionEventFirstWriter(tmp_path)
    row = bus.record_artifact_row('birth_audit.jsonl', {
        'run_id': 'run-1',
        'mint': 'Mint111',
        'creator': 'Creator111',
        'bonding_curve': 'Curve111',
        'associated_bonding_curve': 'Ata111',
        'quote_asset': 'SOL',
        'signature': 'Sig111',
    }, context={'run_id': 'run-1', 'collector_run_id': 'run-1'})
    assert row['exported_after_db_commit'] is True
    assert row['raw_envelope_id']
    assert row['domain_event_id']
    assert row['canonical_db_path']


def test_db_readiness_uses_canonical_counts(tmp_path):
    bus = T007ProductionEventFirstWriter(tmp_path)
    for idx in range(3):
        bus.record_artifact_row('birth_audit.jsonl', {
            'run_id': 'run-1',
            'mint': f'Mint{idx}',
            'creator': 'Creator111',
            'bonding_curve': f'Curve{idx}',
            'associated_bonding_curve': f'Ata{idx}',
            'quote_asset': 'SOL',
            'signature': f'Sig{idx}',
        }, context={'run_id': 'run-1', 'collector_run_id': 'run-1'})
    summary = build_db_readiness_summary(tmp_path, {'raw_notifications': 3, 'unique_birth_mints_live_source': 3})
    assert summary['db_raw_envelope_capture_ratio'] == 1.0
    assert summary['db_birth_capture_ratio'] == 1.0
    assert summary['run_manifest_present'] is True
    assert summary['protocol_layout_registry_present'] is True


def test_watcher_maps_existing_summary_fields_to_proof_fields():
    payload = normalize_watcher_payload({
        'birth_candidate_seen_count': 384,
        'create_instruction_verified_count': 384,
        'decode_success_count': 409,
        'valuation_present_count': 409,
        'trade_flow_available_count': 4234,
        'organic_flow_available_count': 3592,
        'global_migration_events_deduped': 1,
        'post_migration_pool_state_available_count': 1,
        'price_impact_available_count': 4,
    })
    assert payload['raw_birth_candidates'] == 384
    assert payload['verified_births'] == 384
    assert payload['curve_state_decoded'] == 409
    assert payload['market_cap_available'] == 409
    assert payload['global_migration_mints_seen'] == 1
    assert payload['quote_ready_verified'] == 4


def test_noncanonical_event_names_are_normalized_or_rejected(tmp_path):
    from research.mtp_research.validation.t007_sqlite_writer import T007SqliteWriter
    writer = T007SqliteWriter(tmp_path, run_id='run-event-gate', use_internal_db=True)
    writer.start()
    writer.bootstrap_run({'collector_run_id': 'run-event-gate', 'run_id': 'run-event-gate'})
    committed = writer.record_artifact_row({'lane': 'test', 'collector_run_id': 'run-event-gate'}, {'event_type': 'curve_observed', 'collector_run_id': 'run-event-gate', 'mint': 'Mint111'})
    assert committed.domain_event_id
    try:
        writer.record_artifact_row({'lane': 'test', 'collector_run_id': 'run-event-gate'}, {'event_type': 'not_allowed', 'collector_run_id': 'run-event-gate', 'mint': 'Mint111'})
    except ValueError as exc:
        assert 'Non-canonical domain event type' in str(exc)
    else:
        raise AssertionError('expected noncanonical event rejection')
    writer.close()


def test_missing_associated_bonding_curve_is_derivable_when_possible():
    from research.mtp_research.validation.t007_birth_verification import verify_birth_candidate
    result = verify_birth_candidate({
        'mint': 'Mint111111111111111111111111111111111111111',
        'creator': 'Creator111',
        'bonding_curve': 'Curve11111111111111111111111111111111111111',
        'quote_asset': 'SOL',
        'signature': 'Sig111',
    })
    assert result.status in {'verified_create', 'birth_candidate_excluded'}
    assert 'associated_bonding_curve_source' in result.normalized
