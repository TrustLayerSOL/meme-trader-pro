import json
from pathlib import Path

from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.run_outlier_adjusted_rule_report import main


def test_run_outlier_adjusted_rule_report_cli_writes_reports(tmp_path: Path, monkeypatch, capsys) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    outlier_report_path = tmp_path / "outliers.json"
    output_dir = tmp_path / "reports"
    ResearchDatasetStore(dataset_path).upsert_many(
        [
            ResearchDatasetRow(
                row_id="row-1",
                snapshot_id="snapshot-1",
                outcome_id="outcome-1",
                token_mint="mint-1",
                snapshot_ts=100,
                window_name="1m",
                window_seconds=60,
                horizon_name="15m",
                horizon_seconds=900,
                possible_buy_count=2,
                buy_sell_imbalance=0.8,
                forward_return=-0.1,
                label_quality="sparse",
            ),
            ResearchDatasetRow(
                row_id="row-2",
                snapshot_id="snapshot-2",
                outcome_id="outcome-2",
                token_mint="mint-1",
                snapshot_ts=200,
                window_name="1m",
                window_seconds=60,
                horizon_name="15m",
                horizon_seconds=900,
                possible_buy_count=2,
                buy_sell_imbalance=0.8,
                forward_return=10.0,
                label_quality="sparse",
            ),
        ]
    )
    outlier_report_path.write_text(
        json.dumps({"reviews": [{"row_id": "row-2", "outlier_classification": "suspicious_price_jump"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_outlier_adjusted_rule_report",
            "--dataset-path",
            str(dataset_path),
            "--outlier-report-path",
            str(outlier_report_path),
            "--rule-id",
            "buy_imbalance_basic",
            "--output-dir",
            str(output_dir),
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "buy_imbalance_basic.excluded_outlier_count=1" in output
    assert "network_calls=0" in output
    assert list(output_dir.glob("outlier_adjusted_rule_*.json"))
    assert list(output_dir.glob("outlier_adjusted_rule_*.md"))
