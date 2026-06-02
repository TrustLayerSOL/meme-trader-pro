import json
from pathlib import Path

import pytest

from research.mtp_research.validation.pre_launch_funding_planner import (
    CLASSIFICATION_BLOCKED,
    CLASSIFICATION_GO,
    CLASSIFICATION_NEEDS_ADJUSTMENT,
    build_pre_launch_funding_dry_run_plan,
    write_pre_launch_funding_plan_outputs,
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
        },
    }


def test_selects_repeat_creators_first_and_includes_singletons_deterministically(tmp_path: Path) -> None:
    candidates = [
        _candidate(1, "creator-repeat-a", 100),
        _candidate(2, "creator-repeat-a", 200),
        _candidate(3, "creator-repeat-b", 300),
        _candidate(4, "creator-repeat-b", 400),
        _candidate(5, "creator-single-a", 500),
        _candidate(6, "creator-single-b", 600),
    ]

    first = build_pre_launch_funding_dry_run_plan(
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", candidates),
        max_creators=3,
        lookback_hours=24,
        dry_run=True,
    )
    second = build_pre_launch_funding_dry_run_plan(
        candidates_path=tmp_path / "candidates.jsonl",
        max_creators=3,
        lookback_hours=24,
        dry_run=True,
    )

    selected = [row["creator"] for row in first["selected_creators"]]
    assert selected[:2] == ["creator-repeat-a", "creator-repeat-b"]
    assert selected[2].startswith("creator-single")
    assert first["selected_creators"] == second["selected_creators"]
    assert first["scope"]["launches_covered_by_selected_creators"] == 5
    assert "repeat_creator_priority" in first["selected_creators"][0]["reason_selected"]
    assert "singleton_time_distribution" in first["selected_creators"][2]["reason_selected"]


def test_request_estimates_match_lookback_window_and_caps(tmp_path: Path) -> None:
    candidates = [_candidate(i, f"creator-{i}", 1_700_000_000 + i) for i in range(5)]

    plan = build_pre_launch_funding_dry_run_plan(
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", candidates),
        max_creators=5,
        lookback_hours=24,
        request_ceiling=300,
        hard_stop_projected_requests=500,
        dry_run=True,
    )

    assert plan["request_estimate"]["lookback_window"] == "24h"
    assert plan["request_estimate"]["base_projected_requests"] == 105
    assert plan["request_estimate"]["high_projected_requests"] == 260
    assert plan["request_estimate"]["request_ceiling_status"] == "within_ceiling"
    assert plan["dry_run_classification"] == CLASSIFICATION_GO
    assert all(row["base_request_estimate"] == 21 for row in plan["request_estimate"]["per_creator"])
    assert all(row["high_request_estimate"] == 52 for row in plan["request_estimate"]["per_creator"])


def test_stop_go_gate_needs_adjustment_when_high_estimate_exceeds_ceiling(tmp_path: Path) -> None:
    candidates = [_candidate(i, f"creator-{i}", 1_700_000_000 + i) for i in range(5)]

    plan = build_pre_launch_funding_dry_run_plan(
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", candidates),
        max_creators=5,
        lookback_hours=24,
        request_ceiling=200,
        hard_stop_projected_requests=500,
        dry_run=True,
    )

    assert plan["request_estimate"]["high_projected_requests"] == 260
    assert plan["dry_run_classification"] == CLASSIFICATION_NEEDS_ADJUSTMENT
    assert "projected_high_requests_above_request_ceiling" in plan["stop_go"]["failed_gates"]


def test_hard_stop_blocks_plan(tmp_path: Path) -> None:
    candidates = [_candidate(i, f"creator-{i}", 1_700_000_000 + i) for i in range(5)]

    plan = build_pre_launch_funding_dry_run_plan(
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", candidates),
        max_creators=5,
        lookback_hours=7 * 24,
        request_ceiling=10_000,
        hard_stop_projected_requests=100,
        dry_run=True,
    )

    assert plan["dry_run_classification"] == CLASSIFICATION_BLOCKED
    assert "projected_high_requests_above_hard_stop" in plan["stop_go"]["failed_gates"]


def test_dry_run_is_required_and_no_network_calls_are_recorded(tmp_path: Path) -> None:
    candidates = [_candidate(1, "creator-a", 100)]

    with pytest.raises(ValueError, match="dry_run=True is required"):
        build_pre_launch_funding_dry_run_plan(
            candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", candidates),
            max_creators=1,
            dry_run=False,
        )

    plan = build_pre_launch_funding_dry_run_plan(
        candidates_path=tmp_path / "candidates.jsonl",
        max_creators=1,
        dry_run=True,
    )
    assert plan["scope"]["network_calls_used"] == 0
    assert plan["scope"]["helius_calls_used"] == 0
    assert plan["scope"]["dry_run"] is True


def test_output_schema_and_report_files(tmp_path: Path) -> None:
    candidates = [_candidate(i, f"creator-{i}", 1_700_000_000 + i) for i in range(3)]
    plan = build_pre_launch_funding_dry_run_plan(
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", candidates),
        max_creators=3,
        dry_run=True,
    )

    paths = write_pre_launch_funding_plan_outputs(plan, output_dir=tmp_path / "reports")

    assert paths["json_path"].name == "pre_launch_funding_dry_run_plan.json"
    assert paths["markdown_path"].name == "pre_launch_funding_dry_run_plan.md"
    assert paths["json_path"].exists()
    assert paths["markdown_path"].exists()
    loaded = json.loads(paths["json_path"].read_text(encoding="utf-8"))
    assert loaded["report_id"] == "pre_launch_funding_dry_run_plan_v0"
    assert loaded["exact_later_execute_command"].endswith("--execute")
    assert "No network calls were made." in paths["markdown_path"].read_text(encoding="utf-8")
