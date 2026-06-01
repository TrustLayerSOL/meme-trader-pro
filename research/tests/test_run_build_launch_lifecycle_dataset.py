import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore
from research.mtp_research.ingestion.normalization_models import NormalizedEvent
from research.mtp_research.ingestion.pumpfun_creation_census import (
    PumpFunCreationCensusRow,
    write_creation_census,
)


PACIFIC = ZoneInfo("America/Los_Angeles")


def test_lifecycle_dataset_cli_can_build_from_pumpfun_census(tmp_path: Path) -> None:
    launch_ts = int(datetime(2026, 6, 1, 6, 30, tzinfo=PACIFIC).timestamp())
    census_path = tmp_path / "census.jsonl"
    events_path = tmp_path / "events.jsonl"
    output_dir = tmp_path / "launch_regime"
    write_creation_census(
        [
            PumpFunCreationCensusRow(
                mint="mint-1",
                creator_deployer="creator-1",
                creation_signature="sig-1",
                slot=123,
                block_time=launch_ts,
                parser_confidence="high",
                instruction_type="create_v2",
                source_method="pumpfun_gtfa_census",
                accepted=True,
                bonding_curve="curve-1",
            )
        ],
        census_path,
    )
    NormalizedEventStore(events_path).upsert(
        NormalizedEvent(
            event_id="event-1",
            signature="trade-1",
            slot=124,
            block_time=launch_ts + 60,
            event_type="possible_buy",
            token_mint="mint-1",
            venue="pumpfun",
            price_quote=1.0,
        )
    )

    result = subprocess.run(
        [
            "./trading_env/bin/python",
            "-m",
            "research.mtp_research.launch_regime.run_build_launch_lifecycle_dataset",
            "--census-path",
            str(census_path),
            "--events-path",
            str(events_path),
            "--output-dir",
            str(output_dir),
            "--target-launches",
            "1",
        ],
        cwd=Path(__file__).resolve().parents[2],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "launches_collected=1" in result.stdout
    assert "snapshot_rows_created=12" in result.stdout
    assert (output_dir / "launch_regime_candidates.jsonl").exists()
    assert (output_dir / "launch_lifecycle_snapshots.jsonl").exists()
    assert (output_dir / "launch_lifecycle_outcomes.jsonl").exists()
