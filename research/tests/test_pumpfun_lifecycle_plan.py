import json
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from research.mtp_research.ingestion.pumpfun_creation_census import (
    PumpFunCreationCensusRow,
    write_creation_census,
)
from research.mtp_research.launch_regime.pumpfun_lifecycle_plan import build_pumpfun_lifecycle_plan


PACIFIC = ZoneInfo("America/Los_Angeles")


def _ts(year: int, month: int, day: int, hour: int, minute: int = 0) -> int:
    return int(datetime(year, month, day, hour, minute, tzinfo=PACIFIC).timestamp())


def _census_row(mint: str, block_time: int, *, accepted: bool = True, bonding_curve: str = "curve") -> PumpFunCreationCensusRow:
    return PumpFunCreationCensusRow(
        mint=mint,
        creator_deployer=f"creator-{mint}",
        creation_signature=f"sig-{mint}",
        slot=100,
        block_time=block_time,
        parser_confidence="high",
        instruction_type="create_v2",
        source_method="test",
        accepted=accepted,
        bonding_curve=bonding_curve,
        associated_bonding_curve=f"assoc-{mint}",
        instruction_index=3,
        instruction_discriminator="d6904cec5f8b31b4",
    )


def _precision_summary(path: Path, acceptable: bool = True) -> Path:
    path.write_text(
        json.dumps(
            {
                "acceptable_for_scaling": acceptable,
                "review_rows": 50 if acceptable else 0,
                "reviewed_precision": 1.0 if acceptable else None,
                "warning_flags": [] if acceptable else ["parser_precision_not_acceptable_for_scaling"],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_plan_filters_verified_census_rows_to_configured_launch_regime(tmp_path: Path) -> None:
    census_path = tmp_path / "census.jsonl"
    precision_path = _precision_summary(tmp_path / "precision.json")
    write_creation_census(
        [
            _census_row("morning", _ts(2026, 6, 1, 6, 30)),
            _census_row("evening", _ts(2026, 6, 2, 18, 15)),
            _census_row("weekend", _ts(2026, 6, 6, 8, 0)),
            _census_row("outside-window", _ts(2026, 6, 3, 14, 0)),
            _census_row("rejected", _ts(2026, 6, 1, 7, 0), accepted=False),
        ],
        census_path,
    )

    plan = build_pumpfun_lifecycle_plan(
        census_path=census_path,
        precision_summary_path=precision_path,
        target_launches=10,
        max_transactions_per_launch=100,
    )

    assert plan["census_rows"] == 5
    assert plan["accepted_census_rows"] == 4
    assert plan["eligible_launches"] == 2
    assert plan["selected_launches"] == 2
    assert plan["launch_regime_counts"] == {
        "mon_tue_wed_0600_1200_pt": 1,
        "mon_tue_wed_1700_2200_pt": 1,
    }
    assert plan["accepted_weekday_counts"] == {
        "Monday": 1,
        "Saturday": 1,
        "Tuesday": 1,
        "Wednesday": 1,
    }
    assert plan["accepted_hour_local_counts"][6] == 1
    assert plan["accepted_configured_window_counts"] == {
        "configured_weekday_outside_time_window": 1,
        "configured_weekday_window": 2,
        "outside_configured_weekday": 1,
    }
    assert plan["expected_snapshot_rows"] == 24
    assert plan["expected_outcome_rows"] == 2
    assert plan["network_calls"] == 0
    assert plan["plan_reasonable"] is True


def test_plan_blocks_when_precision_summary_is_not_acceptable(tmp_path: Path) -> None:
    census_path = tmp_path / "census.jsonl"
    precision_path = _precision_summary(tmp_path / "precision.json", acceptable=False)
    write_creation_census([_census_row("mint", _ts(2026, 6, 1, 6, 30))], census_path)

    plan = build_pumpfun_lifecycle_plan(
        census_path=census_path,
        precision_summary_path=precision_path,
        target_launches=1,
    )

    assert plan["plan_reasonable"] is False
    assert "precision_gate_not_acceptable_for_scaling" in plan["warning_flags"]


def test_plan_estimates_lifecycle_requests_and_rows(tmp_path: Path) -> None:
    census_path = tmp_path / "census.jsonl"
    precision_path = _precision_summary(tmp_path / "precision.json")
    write_creation_census(
        [
            _census_row("one", _ts(2026, 6, 1, 6, 0)),
            _census_row("two", _ts(2026, 6, 1, 7, 0)),
            _census_row("three", _ts(2026, 6, 1, 8, 0)),
        ],
        census_path,
    )

    plan = build_pumpfun_lifecycle_plan(
        census_path=census_path,
        precision_summary_path=precision_path,
        target_launches=2,
        signature_pages_per_launch=2,
        max_transactions_per_launch=75,
        targets_per_launch=1,
    )

    assert plan["selected_launches"] == 2
    assert plan["estimated_signature_requests"] == 4
    assert plan["estimated_transaction_requests"] == 150
    assert plan["estimated_total_rpc_requests"] == 154
    assert plan["expected_raw_transactions_up_to"] == 150
    assert plan["expected_research_rows"] == 26
    assert plan["collection_scope"] == "first_two_hours_only"


def test_lifecycle_plan_cli_is_dry_run_and_writes_reports(tmp_path: Path) -> None:
    census_path = tmp_path / "census.jsonl"
    precision_path = _precision_summary(tmp_path / "precision.json")
    json_output = tmp_path / "plan.json"
    md_output = tmp_path / "plan.md"
    write_creation_census([_census_row("mint", _ts(2026, 6, 1, 6, 30))], census_path)

    result = subprocess.run(
        [
            "./trading_env/bin/python",
            "-m",
            "research.mtp_research.launch_regime.run_pumpfun_lifecycle_plan",
            "--census-path",
            str(census_path),
            "--precision-summary-path",
            str(precision_path),
            "--target-launches",
            "1",
            "--output-path",
            str(json_output),
            "--markdown-output-path",
            str(md_output),
        ],
        cwd=Path(__file__).resolve().parents[2],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "network_calls=0" in result.stdout
    assert "selected_launches=1" in result.stdout
    assert json_output.exists()
    assert md_output.exists()
