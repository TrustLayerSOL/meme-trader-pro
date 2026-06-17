import json
import sqlite3

from research.mtp_research.validation.t007_production_event_bus import T007ProductionEventFirstWriter


def test_event_first_writer_records_raw_and_verified_birth_domain_event_before_artifact(tmp_path):
    writer = T007ProductionEventFirstWriter(tmp_path)
    row = {
        "run_id": "run-1",
        "mint": "Mint111",
        "creator": "Creator111",
        "bonding_curve": "Curve111",
        "associated_bonding_curve": "Ata111",
        "quote_asset": "SOL",
        "signature": "sig1",
    }
    enriched = writer.record_artifact_row("birth_candidates.jsonl", row, context={"run_id": "run-1"})
    assert enriched["event_type"] == "pump_birth_verified"
    assert enriched["decision_time_safe"] is True
    with sqlite3.connect(tmp_path / "t007_lifecycle_state.sqlite") as connection:
        assert connection.execute("SELECT COUNT(*) FROM raw_source_envelopes").fetchone()[0] == 1
        assert connection.execute("SELECT event_type FROM domain_events").fetchone()[0] == "pump_birth_verified"


def test_event_first_writer_rejects_weak_birth_candidate(tmp_path):
    writer = T007ProductionEventFirstWriter(tmp_path)
    enriched = writer.record_artifact_row("birth_candidates.jsonl", {"run_id": "run-1", "mint": "Mint111"}, context={"run_id": "run-1"})
    assert enriched["event_type"] == "pump_birth_rejected"
    assert enriched["decision_time_safe"] is False
    assert "missing_creator" in enriched["birth_verification_reasons"]


def test_migration_backfill_job_gets_campaign_window_and_replay_classification(tmp_path):
    writer = T007ProductionEventFirstWriter(tmp_path)
    enriched = writer.record_artifact_row(
        "migration_backfill_jobs.jsonl",
        {"mint": "Mint111", "pool_address": "Pool111", "quote_asset": "SOL"},
        context={"run_id": "run-1", "campaign_start_time": 10, "campaign_end_time": 20, "source_duration_seconds": 600},
    )
    assert enriched["campaign_start_time"] == 10
    assert enriched["campaign_end_time"] == 20
    assert enriched["source_duration_seconds"] == 600
    assert enriched["replay_source"] is True
    assert enriched["decision_time_safe"] is False
