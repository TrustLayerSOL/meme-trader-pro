from pathlib import Path
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

from research.mtp_research.ingestion.pumpfun_creation_census import PumpFunCreationCensusRow, write_creation_census
from research.mtp_research.ingestion.run_pumpfun_create_census_collection import _load_checkpoint, _write_checkpoint
from research.mtp_research.ingestion.run_pumpfun_create_census_collection import _regime_launch_count


PACIFIC = ZoneInfo("America/Los_Angeles")


def test_checkpoint_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.json"

    _write_checkpoint(path, {"cursor_before": "sig-1", "accepted_launches": 3})

    assert _load_checkpoint(path) == {"cursor_before": "sig-1", "accepted_launches": 3}


def test_missing_checkpoint_loads_empty_dict(tmp_path: Path) -> None:
    assert _load_checkpoint(tmp_path / "missing.json") == {}


def _row(mint: str, year: int, month: int, day: int, hour: int, accepted: bool = True) -> PumpFunCreationCensusRow:
    block_time = int(datetime(year, month, day, hour, 0, tzinfo=PACIFIC).timestamp())
    return PumpFunCreationCensusRow(
        mint=mint,
        creator_deployer=f"creator-{mint}",
        creation_signature=f"sig-{mint}",
        slot=1,
        block_time=block_time,
        parser_confidence="high",
        instruction_type="create_v2",
        source_method="test",
        accepted=accepted,
        bonding_curve=f"curve-{mint}",
    )


def test_regime_launch_count_counts_only_requested_windows() -> None:
    rows = [
        _row("mon-morning", 2026, 6, 1, 6),
        _row("tue-evening", 2026, 6, 2, 18),
        _row("wed-outside", 2026, 6, 3, 13),
        _row("sun-evening", 2026, 6, 7, 18),
        _row("rejected", 2026, 6, 1, 7, accepted=False),
    ]

    assert _regime_launch_count(rows) == 2


def test_census_collection_dry_run_reports_existing_regime_count(tmp_path: Path) -> None:
    census_path = tmp_path / "census.jsonl"
    checkpoint_path = tmp_path / "checkpoint.json"
    write_creation_census(
        [
            _row("mon-morning", 2026, 6, 1, 6),
            _row("sun-evening", 2026, 6, 7, 18),
        ],
        census_path,
    )

    result = subprocess.run(
        [
            "./trading_env/bin/python",
            "-m",
            "research.mtp_research.ingestion.run_pumpfun_create_census_collection",
            "--output-path",
            str(census_path),
            "--checkpoint-path",
            str(checkpoint_path),
            "--target-regime-launches",
            "2500",
        ],
        cwd=Path(__file__).resolve().parents[2],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "execute=False" in result.stdout
    assert "accepted_launches_existing=2" in result.stdout
    assert "accepted_regime_launches_existing=1" in result.stdout
    assert "network_calls=0" in result.stdout
