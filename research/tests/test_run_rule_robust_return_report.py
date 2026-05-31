from pathlib import Path

from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.run_rule_robust_return_report import main


def test_run_rule_robust_return_report_cli_writes_reports(tmp_path: Path, monkeypatch, capsys) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    output_dir = tmp_path / "reports"
    rows = []
    for idx, value in enumerate([-0.1, 0.0, 0.1, 10.0]):
        rows.append(
            ResearchDatasetRow(
                row_id=f"row-{idx}",
                snapshot_id=f"snapshot-{idx}",
                outcome_id=f"outcome-{idx}",
                token_mint="mint-1",
                snapshot_ts=idx,
                window_name="1m",
                window_seconds=60,
                horizon_name="15m",
                horizon_seconds=900,
                possible_buy_count=2,
                buy_sell_imbalance=0.8,
                forward_return=value,
                label_quality="sparse",
            )
        )
    ResearchDatasetStore(dataset_path).upsert_many(rows)
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_rule_robust_return_report",
            "--dataset-path",
            str(dataset_path),
            "--rule-id",
            "buy_imbalance_basic",
            "--output-dir",
            str(output_dir),
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "buy_imbalance_basic.selected_count=4" in output
    assert "network_calls=0" in output
    assert list(output_dir.glob("rule_robust_return_*.md"))
    assert list(output_dir.glob("rule_robust_return_*.json"))
