import json
from pathlib import Path

from research.mtp_research.validation.run_baseline_vs_filter_audit import main


def test_run_baseline_vs_filter_audit_cli_execute(tmp_path: Path, monkeypatch) -> None:
    data_root = tmp_path / "lake"
    source_root = _write_inputs(data_root)
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_baseline_vs_filter_audit",
            "--data-root",
            str(data_root),
            "--source-report-root",
            str(source_root),
            "--execute",
        ],
    )

    assert main() == 0

    assert (
        data_root
        / "data"
        / "backtests"
        / "diagnostics"
        / "reports"
        / "forward_observation"
        / "baseline_vs_filter_audit"
        / "baseline_vs_filter_audit_summary.json"
    ).exists()


def test_run_baseline_vs_filter_audit_cli_dry_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["run_baseline_vs_filter_audit", "--data-root", str(tmp_path)])

    assert main() == 0


def _write_inputs(base: Path) -> Path:
    report_root = base / "data" / "backtests" / "diagnostics" / "reports" / "forward_observation" / "buy_exit_design"
    report_root.mkdir(parents=True, exist_ok=True)
    row = {
        "mint": "mint-a",
        "actionable_sample_flag": True,
        "crossed_20k": True,
        "crossed_50k": True,
        "crossed_100k": False,
        "crossed_500k": False,
        "crossed_1m": False,
        "fdv_at_20k": 22_000,
        "fdv_per_event_at_20k": 22_000,
        "fdv_per_active_wallet_at_20k": 22_000,
        "first_path_before_20k": True,
        "10k_to_20k_seconds": 20,
        "path_row_count": 2,
        "max_fdv_after_20k": 60_000,
        "max_drawdown_after_20k": 0,
        "maturity_state": "trigger_qualified_active_watch",
    }
    (report_root / "buy_exit_design_dataset.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    (report_root / "buy_exit_start_rule_design_summary.json").write_text(
        json.dumps({"all_crossed_20k_count": 1, "actionable_crossed_20k_count": 1}),
        encoding="utf-8",
    )
    return report_root
