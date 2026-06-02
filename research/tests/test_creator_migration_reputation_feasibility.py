import csv
import json
from pathlib import Path

from research.mtp_research.validation.creator_migration_reputation_feasibility import (
    READINESS_PARTIAL,
    build_creator_migration_reputation_report,
    write_creator_migration_reputation_outputs,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _candidate(index: int, creator: str, launch_ts: int) -> dict:
    return {
        "launch_id": f"launch-{index}",
        "token_mint": f"mint-{index}",
        "launch_ts": launch_ts,
        "metadata_json": {
            "creator_deployer": creator,
            "creation_signature": f"create-{index}",
        },
    }


def _migration_event(mint: str, block_time: int | None, signature: str = "migration-sig") -> dict:
    return {
        "token_mint": mint,
        "venue": "pumpfun_migrate",
        "event_type": "token_accumulation",
        "block_time": block_time,
        "signature": signature,
        "metadata_json": {"venue_reasons": ["matched_pumpfun_program_id_and_migrate_instruction_log"]},
    }


def test_leakage_safe_prior_migration_counts_same_creator_only(tmp_path: Path) -> None:
    all_candidates = [
        _candidate(1, "creator-a", 100),
        _candidate(2, "creator-a", 200),
        _candidate(3, "creator-a", 300),
        _candidate(4, "creator-b", 400),
    ]
    events = [
        _migration_event("mint-1", 150),
        _migration_event("mint-3", 350),
        _migration_event("mint-4", 50),
    ]

    report = build_creator_migration_reputation_report(
        strict_candidates_path=_write_jsonl(tmp_path / "strict.jsonl", all_candidates),
        all_candidates_path=_write_jsonl(tmp_path / "all.jsonl", all_candidates),
        events_path=_write_jsonl(tmp_path / "events.jsonl", events),
        strict_outcomes_path=_write_jsonl(tmp_path / "strict_outcomes.jsonl", []),
        all_outcomes_path=_write_jsonl(tmp_path / "all_outcomes.jsonl", []),
    )

    rows = {row["mint"]: row for row in report["sample_rows"]}
    assert rows["mint-1"]["creator_prior_migration_count"] == 0
    assert rows["mint-2"]["creator_prior_migration_count"] == 1
    assert rows["mint-3"]["creator_prior_migration_count"] == 1
    assert rows["mint-4"]["creator_prior_migration_count"] == 1
    assert rows["mint-3"]["creator_prior_last_migration_age_seconds"] == 150
    assert report["leakage_safe_computability"]["creator_prior_migration_count"]["classification"] == "computable_now"
    assert report["scope"]["network_calls_used"] == 0
    assert report["scope"]["thesis_runs"] == 0


def test_missing_migration_timestamp_is_not_counted(tmp_path: Path) -> None:
    candidates = [_candidate(1, "creator-a", 100), _candidate(2, "creator-a", 200)]
    events = [_migration_event("mint-1", None)]

    report = build_creator_migration_reputation_report(
        strict_candidates_path=_write_jsonl(tmp_path / "strict.jsonl", candidates),
        all_candidates_path=_write_jsonl(tmp_path / "all.jsonl", candidates),
        events_path=_write_jsonl(tmp_path / "events.jsonl", events),
        strict_outcomes_path=_write_jsonl(tmp_path / "strict_outcomes.jsonl", []),
        all_outcomes_path=_write_jsonl(tmp_path / "all_outcomes.jsonl", []),
    )

    rows = {row["mint"]: row for row in report["sample_rows"]}
    assert rows["mint-2"]["creator_prior_migration_count"] == 0
    assert rows["mint-2"]["missing_reason"] == "no_prior_migrations_for_creator"
    assert report["migration_observability"]["migration_timestamp_available_count"] == 0


def test_migration_labels_feed_prior_migration_counts(tmp_path: Path) -> None:
    candidates = [_candidate(1, "creator-a", 100), _candidate(2, "creator-a", 200)]
    labels = [
        {
            "mint": "mint-1",
            "creator": "creator-a",
            "pumpfun_migrate_event_observed": True,
            "migration_time": "1970-01-01T00:02:30+00:00",
            "migration_signature": "migration-from-label",
        }
    ]

    report = build_creator_migration_reputation_report(
        strict_candidates_path=_write_jsonl(tmp_path / "strict.jsonl", candidates),
        all_candidates_path=_write_jsonl(tmp_path / "all.jsonl", candidates),
        events_path=_write_jsonl(tmp_path / "events.jsonl", []),
        strict_outcomes_path=_write_jsonl(tmp_path / "strict_outcomes.jsonl", []),
        all_outcomes_path=_write_jsonl(tmp_path / "all_outcomes.jsonl", []),
        migration_labels_path=_write_jsonl(tmp_path / "migration_labels.jsonl", labels),
    )

    rows = {row["mint"]: row for row in report["sample_rows"]}
    assert rows["mint-2"]["creator_prior_migration_count"] == 1
    assert rows["mint-2"]["creator_prior_last_migration_age_seconds"] == 50
    assert report["migration_observability"]["deduped_migration_records"] == 1
    assert report["migration_observability"]["migration_timestamp_available_count"] == 1
    assert report["leakage_safe_computability"]["creator_prior_migration_count"]["classification"] == "computable_now"


def test_four_plus_prior_migration_flag(tmp_path: Path) -> None:
    candidates = [_candidate(i, "creator-a", i * 100) for i in range(1, 7)]
    events = [_migration_event(f"mint-{i}", i * 100 + 10, signature=f"mig-{i}") for i in range(1, 5)]

    report = build_creator_migration_reputation_report(
        strict_candidates_path=_write_jsonl(tmp_path / "strict.jsonl", candidates),
        all_candidates_path=_write_jsonl(tmp_path / "all.jsonl", candidates),
        events_path=_write_jsonl(tmp_path / "events.jsonl", events),
        strict_outcomes_path=_write_jsonl(tmp_path / "strict_outcomes.jsonl", []),
        all_outcomes_path=_write_jsonl(tmp_path / "all_outcomes.jsonl", []),
    )

    rows = {row["mint"]: row for row in report["sample_rows"]}
    assert rows["mint-5"]["creator_prior_migration_count"] == 4
    assert rows["mint-5"]["creator_has_4plus_prior_migrations"] is True
    assert report["derived_field_summary"]["launches_with_4plus_prior_migrations"] == 2


def test_readiness_partial_when_four_plus_filter_is_empty(tmp_path: Path) -> None:
    candidates = [_candidate(1, "creator-a", 100), _candidate(2, "creator-a", 200)]
    events = [_migration_event("mint-1", 150)]

    report = build_creator_migration_reputation_report(
        strict_candidates_path=_write_jsonl(tmp_path / "strict.jsonl", candidates),
        all_candidates_path=_write_jsonl(tmp_path / "all.jsonl", candidates),
        events_path=_write_jsonl(tmp_path / "events.jsonl", events),
        strict_outcomes_path=_write_jsonl(tmp_path / "strict_outcomes.jsonl", []),
        all_outcomes_path=_write_jsonl(tmp_path / "all_outcomes.jsonl", []),
    )

    assert report["readiness_classification"] == READINESS_PARTIAL
    assert report["t008_creator_migration_reputation_feasible_now"] is False
    assert "four_plus_prior_migration_filter_empty" in report["warning_flags"]


def test_outputs_reports_and_optional_sample_csv(tmp_path: Path) -> None:
    candidates = [_candidate(1, "creator-a", 100), _candidate(2, "creator-a", 200)]
    events = [_migration_event("mint-1", 150)]
    report = build_creator_migration_reputation_report(
        strict_candidates_path=_write_jsonl(tmp_path / "strict.jsonl", candidates),
        all_candidates_path=_write_jsonl(tmp_path / "all.jsonl", candidates),
        events_path=_write_jsonl(tmp_path / "events.jsonl", events),
        strict_outcomes_path=_write_jsonl(tmp_path / "strict_outcomes.jsonl", []),
        all_outcomes_path=_write_jsonl(tmp_path / "all_outcomes.jsonl", []),
    )

    paths = write_creator_migration_reputation_outputs(report, output_dir=tmp_path / "reports")

    assert paths["json_path"].name == "creator_migration_reputation_feasibility.json"
    assert paths["markdown_path"].name == "creator_migration_reputation_feasibility.md"
    assert paths["sample_csv_path"].name == "creator_migration_reputation_sample.csv"
    assert paths["json_path"].exists()
    assert paths["markdown_path"].exists()
    assert paths["sample_csv_path"].exists()
    with paths["sample_csv_path"].open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["launch_id"] == "launch-1"
    assert "No thesis cycle was run." in paths["markdown_path"].read_text(encoding="utf-8")
