from datetime import datetime, timezone
from pathlib import Path

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.models import LaunchCandidate
from research.mtp_research.pipeline.run_sample_adequacy_expansion_plan import main
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.walk_forward_models import (
    RuleWalkForwardSummary,
    WalkForwardConfig,
    WalkForwardValidationResult,
    utc_now_iso,
)
from research.mtp_research.validation.walk_forward_store import WalkForwardValidationStore


def test_sample_adequacy_expansion_plan_cli_runs_without_network(tmp_path: Path, monkeypatch, capsys) -> None:
    registry_path = tmp_path / "registry.jsonl"
    dataset_path = tmp_path / "dataset.jsonl"
    walk_path = tmp_path / "walk.jsonl"
    output_dir = tmp_path / "reports"
    CandidateRegistry(registry_path).upsert(
        LaunchCandidate(
            token_mint="token-1",
            source="dexscreener",
            first_seen_ts=datetime(2026, 5, 31, tzinfo=timezone.utc),
            pool_address="pool-1",
            liquidity_usd=20_000,
        )
    )
    ResearchDatasetStore(dataset_path).upsert(
        ResearchDatasetRow(
            row_id="row-1",
            snapshot_id="snapshot-1",
            outcome_id="outcome-1",
            token_mint="token-1",
            snapshot_ts=100,
            window_name="1m",
            window_seconds=60,
            horizon_name="1m",
            horizon_seconds=60,
        )
    )
    WalkForwardValidationStore(walk_path).upsert(
        WalkForwardValidationResult(
            validation_id="validation-1",
            created_at=utc_now_iso(),
            config=WalkForwardConfig("cfg", 900, 300, 300),
            dataset_path=str(dataset_path),
            row_count=1,
            filtered_row_count=1,
            fold_count=1,
            rules_tested=1,
            rule_summaries=[
                RuleWalkForwardSummary(
                    rule_id="rule-1",
                    rule_name="Rule 1",
                    valid_test_fold_count=1,
                    total_test_selected_count=5,
                )
            ],
        )
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_sample_adequacy_expansion_plan",
            "--registry-path",
            str(registry_path),
            "--dataset-path",
            str(dataset_path),
            "--walk-forward-store-path",
            str(walk_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "sample_adequate=False" in output
    assert "network_calls=0" in output
    assert list(output_dir.glob("sample_adequacy_expansion_plan_*.md"))
    assert list(output_dir.glob("sample_adequacy_expansion_plan_*.json"))
