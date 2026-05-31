from datetime import datetime, timezone
from pathlib import Path

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.models import LaunchCandidate
from research.mtp_research.pipeline.backfill_target_planner import BackfillTargetPlanner
from research.mtp_research.pipeline.run_evidence_backfill import main as evidence_main
from research.mtp_research.pipeline.run_plan_backfill_targets import main as plan_main


def _registry(path: Path, mock_only: bool = False) -> None:
    registry = CandidateRegistry(path)
    registry.upsert(
        LaunchCandidate(
            token_mint="mock-mint",
            source="manual_example",
            first_seen_ts=datetime(2026, 5, 31, tzinfo=timezone.utc),
            pool_address="mock-pool",
            metadata_json={"is_mock": True},
        )
    )
    if not mock_only:
        registry.upsert(
            LaunchCandidate(
                token_mint="real-mint",
                source="dexscreener_real",
                first_seen_ts=datetime(2026, 5, 31, tzinfo=timezone.utc),
                pool_address="real-pool",
                liquidity_usd=25_000,
                metadata_json={"is_mock": False},
            )
        )


def test_backfill_target_planner_excludes_mock_by_default(tmp_path: Path) -> None:
    _registry(tmp_path / "registry.jsonl")
    candidates = CandidateRegistry(tmp_path / "registry.jsonl").load_all()

    default_targets = BackfillTargetPlanner().candidates_to_targets(candidates, roles=["mint", "pool"])
    include_targets = BackfillTargetPlanner().candidates_to_targets(candidates, roles=["mint", "pool"], exclude_mock=False)

    assert {target.token_mint for target in default_targets} == {"real-mint"}
    assert {target.token_mint for target in include_targets} == {"mock-mint", "real-mint"}


def test_plan_backfill_targets_excludes_mock_by_default(tmp_path: Path, monkeypatch, capsys) -> None:
    registry_path = tmp_path / "registry.jsonl"
    output_path = tmp_path / "targets.jsonl"
    _registry(registry_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_plan_backfill_targets",
            "--registry-path",
            str(registry_path),
            "--output-path",
            str(output_path),
            "--candidate-limit",
            "10",
        ],
    )

    assert plan_main() == 0
    output = capsys.readouterr().out
    assert "skipped_mock=1" in output
    assert "targets_planned=2" in output
    assert "mock-mint" not in output_path.read_text(encoding="utf-8")


def test_evidence_backfill_does_not_call_helius_when_no_real_candidates_exist(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    registry_path = tmp_path / "registry.jsonl"
    raw_path = tmp_path / "raw.jsonl"
    _registry(registry_path, mock_only=True)
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_evidence_backfill",
            "--registry-path",
            str(registry_path),
            "--raw-path",
            str(raw_path),
            "--candidate-limit",
            "10",
            "--execute",
        ],
    )

    assert evidence_main() == 0
    output = capsys.readouterr().out
    assert "targets_planned=0" in output
    assert "No evidence-bearing real candidates found. Run real discovery first." in output
    assert "warning_flags=['no_evidence_bearing_real_candidates']" in output
    assert not raw_path.exists()
