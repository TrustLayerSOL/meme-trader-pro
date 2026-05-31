import json
from pathlib import Path

from research.mtp_research.backtest.rule_library import default_rule_library
from research.mtp_research.validation.fold_sufficiency_analyzer import FoldSufficiencyAnalyzer
from research.mtp_research.validation.fold_sufficiency_models import FOLD_SUFFICIENCY_WARNING
from research.mtp_research.validation.fold_sufficiency_report import (
    format_seconds,
    report_to_dict,
    write_report_json,
    write_report_markdown,
)
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow


def _row(row_id: str, snapshot_ts: int) -> ResearchDatasetRow:
    return ResearchDatasetRow(
        row_id=row_id,
        snapshot_id=f"snapshot-{row_id}",
        outcome_id=f"outcome-{row_id}",
        token_mint="mint-1",
        snapshot_ts=snapshot_ts,
        window_name="1m",
        window_seconds=60,
        horizon_name="5m",
        horizon_seconds=300,
        entry_price=1.0,
        forward_return=0.1,
        possible_buy_count=1,
        confidence_weighted_net_flow=1.0,
        label_quality="sparse",
    )


def test_fold_sufficiency_report_writes_markdown_and_json(tmp_path: Path) -> None:
    rows = [_row(f"row-{idx}", idx * 60) for idx in range(31)]
    report = FoldSufficiencyAnalyzer().analyze(rows, default_rule_library(), dataset_path="dataset.jsonl")

    markdown_path = write_report_markdown(report, tmp_path / "report.md")
    json_path = write_report_json(report, tmp_path / "report.json")

    markdown = markdown_path.read_text(encoding="utf-8")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert FOLD_SUFFICIENCY_WARNING in markdown
    assert "Config Comparison" in markdown
    assert payload["diagnostic_warning"] == FOLD_SUFFICIENCY_WARNING
    assert report_to_dict(report)["report_id"] == report.report_id


def test_format_seconds() -> None:
    assert format_seconds(None) == "n/a"
    assert format_seconds(30) == "30s"
    assert format_seconds(300) == "5m"
    assert format_seconds(3600) == "1.00h"
    assert format_seconds(86400) == "1.00d"
