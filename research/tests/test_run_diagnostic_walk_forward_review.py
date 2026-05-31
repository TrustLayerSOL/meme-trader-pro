from pathlib import Path

from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.run_diagnostic_walk_forward_review import main
from research.mtp_research.validation.walk_forward_models import (
    RuleWalkForwardSummary,
    WalkForwardConfig,
    WalkForwardValidationResult,
    utc_now_iso,
)
from research.mtp_research.validation.walk_forward_store import WalkForwardValidationStore


def test_cli_loads_temp_dataset_and_walk_forward_store(tmp_path: Path, monkeypatch, capsys) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    store_path = tmp_path / "walk.jsonl"
    output_dir = tmp_path / "reports"
    ResearchDatasetStore(dataset_path).upsert(
        ResearchDatasetRow(
            row_id="row-1",
            snapshot_id="snapshot-1",
            outcome_id="outcome-1",
            token_mint="mint-1",
            snapshot_ts=100,
            window_name="1m",
            window_seconds=60,
            horizon_name="1m",
            horizon_seconds=60,
            entry_price_source="exact_snapshot",
            forward_return=0.1,
            label_quality="sparse",
        )
    )
    WalkForwardValidationStore(store_path).upsert(
        WalkForwardValidationResult(
            validation_id="validation-1",
            created_at=utc_now_iso(),
            config=WalkForwardConfig("best", 900, 300, 300),
            dataset_path=str(dataset_path),
            row_count=1,
            filtered_row_count=1,
            fold_count=1,
            rules_tested=1,
            rule_summaries=[
                RuleWalkForwardSummary(
                    rule_id="positive_flow_basic",
                    rule_name="Positive Flow Basic",
                    valid_test_fold_count=1,
                    total_test_selected_count=10,
                    avg_test_net_return=0.05,
                    positive_test_fold_rate=1.0,
                    consistency_score=0.05,
                )
            ],
        )
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_diagnostic_walk_forward_review",
            "--dataset-path",
            str(dataset_path),
            "--walk-forward-store-path",
            str(store_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "rules_with_valid_folds=1" in output
    assert "network_calls=0" in output
    assert list(output_dir.glob("*.md"))
    assert list(output_dir.glob("*.json"))
