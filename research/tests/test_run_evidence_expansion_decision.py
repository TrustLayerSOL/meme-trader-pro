import json
from pathlib import Path

from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.run_evidence_expansion_decision import main


def test_evidence_expansion_decision_cli_loads_temp_reports(tmp_path: Path, monkeypatch, capsys) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    output_dir = tmp_path / "reports"
    robust_path = tmp_path / "robust.json"
    outlier_path = tmp_path / "outlier.json"
    selected_path = tmp_path / "selected.json"
    fold_path = tmp_path / "fold.json"
    wf_path = tmp_path / "wf.json"
    price_path = tmp_path / "price.json"
    sufficiency_path = tmp_path / "sufficiency.json"
    ResearchDatasetStore(dataset_path).upsert(
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
            forward_return=0.1,
            label_quality="sparse",
        )
    )
    robust_path.write_text(json.dumps({"rule_summaries": [{"rule_id": "rule-1", "rule_name": "Rule 1", "selected_count": 10, "robust_returns": {"mean": 1.0, "median": -0.01}, "capped_metrics": {"mean": 0.02}}]}), encoding="utf-8")
    outlier_path.write_text(json.dumps({"reviews": [{"rule_id": "rule-1", "outlier_classification": "plausible_price_path"}]}), encoding="utf-8")
    selected_path.write_text(json.dumps({"rule_audits": [{"rule_id": "rule-1", "outlier_return_share": 0.9}]}), encoding="utf-8")
    fold_path.write_text(json.dumps({"best_config": {"valid_folds": 2}}), encoding="utf-8")
    wf_path.write_text(json.dumps({"rule_findings": [{"rule_id": "rule-1", "positive_test_fold_rate": 0.25, "median_test_net_return": -0.01, "valid_test_fold_count": 2}]}), encoding="utf-8")
    price_path.write_text(json.dumps({"price_coverage_rate": 0.4, "no_price_label_count": 10}), encoding="utf-8")
    sufficiency_path.write_text(json.dumps({"sufficiency": {"rows_with_forward_return": 1}}), encoding="utf-8")

    monkeypatch.setattr(
        "sys.argv",
        [
            "run_evidence_expansion_decision",
            "--diagnostic-dataset-path",
            str(dataset_path),
            "--robust-rule-report-json",
            str(robust_path),
            "--outlier-price-path-json",
            str(outlier_path),
            "--selected-row-audit-json",
            str(selected_path),
            "--fold-sufficiency-json",
            str(fold_path),
            "--diagnostic-walk-forward-review-json",
            str(wf_path),
            "--price-coverage-json",
            str(price_path),
            "--dataset-sufficiency-json",
            str(sufficiency_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "recommended_next_action=" in output
    assert "recommended_command=" in output
    assert "network_calls=0" in output
    assert list(output_dir.glob("evidence_expansion_decision_*.json"))
