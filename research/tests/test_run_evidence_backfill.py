from datetime import datetime, timezone
from pathlib import Path

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.models import LaunchCandidate
from research.mtp_research.pipeline.run_evidence_backfill import main


def test_evidence_backfill_dry_run_makes_no_network_calls(tmp_path: Path, monkeypatch, capsys) -> None:
    registry_path = tmp_path / "registry.jsonl"
    raw_path = tmp_path / "raw.jsonl"
    CandidateRegistry(registry_path).upsert(
        LaunchCandidate(
            token_mint="mint-1",
            source="test",
            first_seen_ts=datetime(2026, 5, 31, tzinfo=timezone.utc),
        )
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_evidence_backfill",
            "--registry-path",
            str(registry_path),
            "--raw-path",
            str(raw_path),
            "--candidate-limit",
            "1",
            "--max-signatures-per-target",
            "10",
            "--max-transactions-per-target",
            "10",
        ],
    )
    assert main() == 0
    output = capsys.readouterr().out
    assert "dry_run=True" in output
    assert "no_network_calls_made=True" in output
    assert "targets_planned=1" in output
