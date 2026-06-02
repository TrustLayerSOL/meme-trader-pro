import json
from pathlib import Path

import pytest

from research.mtp_research.validation.migration_graduation_enrichment_planner import (
    CLASSIFICATION_BLOCKED,
    CLASSIFICATION_GO,
    CLASSIFICATION_NEEDS_ADJUSTMENT,
    build_migration_graduation_enrichment_dry_run_plan,
    write_migration_graduation_enrichment_plan_outputs,
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
        "launch_time_utc": f"2026-05-25T{index % 24:02d}:00:00+00:00",
        "metadata_json": {
            "creator_deployer": creator,
            "creation_signature": f"sig-{index}",
            "bonding_curve": f"curve-{index}",
            "associated_bonding_curve": f"assoc-{index}",
        },
    }


def test_selects_mints_deterministically_with_repeat_creator_priority_and_time_distribution(tmp_path: Path) -> None:
    candidates = [
        _candidate(1, "creator-repeat-a", 100),
        _candidate(2, "creator-repeat-a", 200),
        _candidate(3, "creator-repeat-b", 300),
        _candidate(4, "creator-repeat-b", 400),
        _candidate(5, "creator-single-a", 500),
        _candidate(6, "creator-single-b", 600),
    ]

    first = build_migration_graduation_enrichment_dry_run_plan(
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", candidates),
        mint_limit=4,
        windows=["24h", "72h", "7d"],
        dry_run=True,
    )
    second = build_migration_graduation_enrichment_dry_run_plan(
        candidates_path=tmp_path / "candidates.jsonl",
        mint_limit=4,
        windows=["24h", "72h", "7d"],
        dry_run=True,
    )

    assert [row["mint"] for row in first["selected_mints"]] == [row["mint"] for row in second["selected_mints"]]
    assert first["selected_mints"][0]["reason_selected"] == "repeat_creator_priority"
    assert any(row["reason_selected"] == "singleton_time_distribution" for row in first["selected_mints"])
    assert first["scope"]["selected_mint_count"] == 4
    assert first["scope"]["selected_creator_count"] >= 2


def test_request_estimates_cover_all_requested_windows_and_primary_gate(tmp_path: Path) -> None:
    candidates = [_candidate(i, f"creator-{i}", 1_700_000_000 + i) for i in range(5)]

    plan = build_migration_graduation_enrichment_dry_run_plan(
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", candidates),
        mint_limit=5,
        windows=["24h", "72h", "7d"],
        request_ceiling=300,
        hard_stop_projected_requests=500,
        dry_run=True,
    )

    assert plan["request_estimate"]["primary_window"] == "24h"
    assert plan["request_estimate"]["primary_base_projected_requests"] == 30
    assert plan["request_estimate"]["primary_high_projected_requests"] == 140
    assert plan["request_estimate"]["request_ceiling_status"] == "within_ceiling"
    assert plan["dry_run_classification"] == CLASSIFICATION_GO
    assert set(plan["request_estimate"]["windows"].keys()) == {"24h", "72h", "7d"}
    assert plan["request_estimate"]["windows"]["72h"]["high_projected_requests"] == 280
    assert plan["request_estimate"]["windows"]["7d"]["high_projected_requests"] == 575


def test_stop_go_needs_adjustment_when_primary_window_exceeds_ceiling(tmp_path: Path) -> None:
    candidates = [_candidate(i, f"creator-{i}", 1_700_000_000 + i) for i in range(5)]

    plan = build_migration_graduation_enrichment_dry_run_plan(
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", candidates),
        mint_limit=5,
        windows=["24h"],
        request_ceiling=100,
        hard_stop_projected_requests=500,
        dry_run=True,
    )

    assert plan["request_estimate"]["primary_high_projected_requests"] == 140
    assert plan["dry_run_classification"] == CLASSIFICATION_NEEDS_ADJUSTMENT
    assert "primary_high_requests_above_request_ceiling" in plan["stop_go"]["failed_gates"]


def test_hard_stop_blocks_plan(tmp_path: Path) -> None:
    candidates = [_candidate(i, f"creator-{i}", 1_700_000_000 + i) for i in range(5)]

    plan = build_migration_graduation_enrichment_dry_run_plan(
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", candidates),
        mint_limit=5,
        windows=["7d"],
        request_ceiling=10_000,
        hard_stop_projected_requests=100,
        dry_run=True,
    )

    assert plan["dry_run_classification"] == CLASSIFICATION_BLOCKED
    assert "primary_high_requests_above_hard_stop" in plan["stop_go"]["failed_gates"]


def test_dry_run_required_and_no_network_calls_recorded(tmp_path: Path) -> None:
    candidates = [_candidate(1, "creator-a", 100)]

    with pytest.raises(ValueError, match="dry_run=True is required"):
        build_migration_graduation_enrichment_dry_run_plan(
            candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", candidates),
            mint_limit=1,
            dry_run=False,
        )

    plan = build_migration_graduation_enrichment_dry_run_plan(
        candidates_path=tmp_path / "candidates.jsonl",
        mint_limit=1,
        dry_run=True,
    )
    assert plan["scope"]["network_calls_used"] == 0
    assert plan["scope"]["helius_calls_used"] == 0
    assert plan["scope"]["dry_run"] is True


def test_output_schema_and_report_files(tmp_path: Path) -> None:
    candidates = [_candidate(i, f"creator-{i}", 1_700_000_000 + i) for i in range(3)]
    plan = build_migration_graduation_enrichment_dry_run_plan(
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", candidates),
        mint_limit=3,
        dry_run=True,
    )

    paths = write_migration_graduation_enrichment_plan_outputs(plan, output_dir=tmp_path / "reports")

    assert paths["json_path"].name == "migration_graduation_enrichment_dry_run_plan.json"
    assert paths["markdown_path"].name == "migration_graduation_enrichment_dry_run_plan.md"
    assert paths["json_path"].exists()
    assert paths["markdown_path"].exists()
    loaded = json.loads(paths["json_path"].read_text(encoding="utf-8"))
    assert loaded["report_id"] == "migration_graduation_enrichment_dry_run_plan_v0"
    assert loaded["exact_later_execute_command"].endswith("--execute")
    assert "No network calls were made." in paths["markdown_path"].read_text(encoding="utf-8")
