from datetime import datetime, timezone
from pathlib import Path

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.models import LaunchCandidate
from research.mtp_research.pipeline.run_plan_backfill_targets import main


def test_plan_backfill_targets_cli_writes_target_plan(tmp_path: Path, monkeypatch, capsys) -> None:
    registry_path = tmp_path / "registry.jsonl"
    output_path = tmp_path / "targets.jsonl"
    CandidateRegistry(registry_path).upsert(
        LaunchCandidate(
            token_mint="mint-1",
            source="test",
            first_seen_ts=datetime(2026, 5, 31, tzinfo=timezone.utc),
            pool_address="pool-1",
        )
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_plan_backfill_targets",
            "--registry-path",
            str(registry_path),
            "--output-path",
            str(output_path),
            "--role",
            "mint",
            "--role",
            "pool",
        ],
    )
    assert main() == 0
    output = capsys.readouterr().out
    assert "candidates_selected=1" in output
    assert "targets_planned=2" in output
    assert output_path.exists()
