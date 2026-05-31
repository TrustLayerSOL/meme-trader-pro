from pathlib import Path

from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.run_sample_adequacy_report import main
from research.mtp_research.validation.walk_forward_models import (
    RuleWalkForwardSummary,
    WalkForwardConfig,
    WalkForwardValidationResult,
    utc_now_iso,
)
from research.mtp_research.validation.walk_forward_store import WalkForwardValidationStore


def test_sample_adequacy_cli_runs_with_temp_dataset_and_walk_forward(tmp_path: Path, monkeypatch, capsys) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    walk_path = tmp_path / "walk.jsonl"
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
            "run_sample_adequacy_report",
            "--dataset-path",
            str(dataset_path),
            "--walk-forward-store-path",
            str(walk_path),
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "real_token_count=1" in output
    assert "adequate_for_rejection=False" in output
    assert "recommended_data_expansion=add_more_real_candidates_and_expand_time_span" in output
    assert "network_calls=0" in output
