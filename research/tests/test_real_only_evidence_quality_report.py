from datetime import datetime, timezone
from pathlib import Path

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.models import LaunchCandidate
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.run_real_only_evidence_quality_report import main


def _candidate(token_mint: str, is_mock: bool) -> LaunchCandidate:
    return LaunchCandidate(
        token_mint=token_mint,
        source="manual_example" if is_mock else "dexscreener_real",
        first_seen_ts=datetime(2026, 5, 31, tzinfo=timezone.utc),
        pool_address="MockPool" if is_mock else "real-pool",
        metadata_json={"is_mock": is_mock},
    )


def _row(row_id: str, token_mint: str, source="last_before_snapshot"):
    return ResearchDatasetRow(
        row_id=row_id,
        snapshot_id=f"s-{row_id}",
        outcome_id=f"o-{row_id}",
        token_mint=token_mint,
        snapshot_ts=100,
        window_name="1m",
        window_seconds=60,
        horizon_name="5m",
        horizon_seconds=300,
        entry_price=1.0,
        forward_return=0.1,
        label_quality="sparse",
        entry_price_source=source,
    )


def test_real_only_evidence_quality_report_filters_mock_tokens(tmp_path: Path, monkeypatch, capsys) -> None:
    registry_path = tmp_path / "registry.jsonl"
    clean_dataset_path = tmp_path / "clean.jsonl"
    fallback_dataset_path = tmp_path / "fallback.jsonl"
    registry = CandidateRegistry(registry_path)
    registry.upsert(_candidate("mock-token", True))
    registry.upsert(_candidate("real-token", False))
    ResearchDatasetStore(clean_dataset_path).upsert_many([_row("1", "mock-token"), _row("2", "real-token")])
    ResearchDatasetStore(fallback_dataset_path).upsert_many(
        [_row("3", "real-token", "nearest_research_fallback"), _row("4", "mock-token")]
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_real_only_evidence_quality_report",
            "--registry-path",
            str(registry_path),
            "--clean-dataset-path",
            str(clean_dataset_path),
            "--fallback-dataset-path",
            str(fallback_dataset_path),
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out
    assert "real_only_clean_rows=1" in output
    assert "real_only_fallback_rows=1" in output
    assert "nearest_fallback_row_count=1" in output
    assert "recommendation=accept fallback for research-only diagnostics" in output
