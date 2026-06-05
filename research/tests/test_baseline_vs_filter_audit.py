import json
from pathlib import Path

from research.mtp_research.validation.baseline_vs_filter_audit import (
    build_baseline_exit_comparison,
    build_baseline_path_summary,
    build_disabled_baseline_config,
    build_filter_vs_baseline_comparison,
    build_rule_labels,
    classify_recommendation,
    load_audit_inputs,
    run_baseline_vs_filter_audit,
)


def test_load_audit_inputs_uses_actionable_crossed_20k_main_population(tmp_path: Path) -> None:
    report_root = _write_inputs(tmp_path)

    inputs = load_audit_inputs(report_root)

    assert len(inputs.actionable_rows) == 4
    assert inputs.summary["all_crossed_20k_count"] == 8
    assert inputs.duplicate_mint_count == 0
    assert inputs.missing_path_count == 0


def test_rule_labels_include_baseline_and_failure_reasons(tmp_path: Path) -> None:
    inputs = load_audit_inputs(_write_inputs(tmp_path))

    labels = build_rule_labels(inputs.actionable_rows)

    assert all(row["baseline_all_actionable_20k"] is True for row in labels)
    assert {key for key in labels[0] if key.endswith("_pass")} == {"B1_pass", "B2_pass", "B3_pass", "B4_pass"}
    mint_a = next(row for row in labels if row["mint"] == "mint-a")
    mint_b = next(row for row in labels if row["mint"] == "mint-b")
    assert mint_a["B3_pass"] is True
    assert mint_b["B3_pass"] is False
    assert "chase_guard" in mint_b["B3_failure_reason"]


def test_filter_comparison_marks_small_support_as_artifact(tmp_path: Path) -> None:
    inputs = load_audit_inputs(_write_inputs(tmp_path))
    labels = build_rule_labels(inputs.actionable_rows)
    baseline = build_baseline_path_summary(inputs.actionable_rows)

    comparison = build_filter_vs_baseline_comparison(inputs.actionable_rows, labels, baseline)

    b3_pass = next(row for row in comparison if row["group_id"] == "B3_pass")
    b3_fail = next(row for row in comparison if row["group_id"] == "B3_fail")
    assert b3_pass["pass_count"] == 1
    assert b3_pass["support_warning"] == "support_lt_30"
    assert b3_pass["improvement_interpretation"] == "small_sample_artifact"
    assert b3_fail["pass_count"] == 3


def test_baseline_exit_comparison_and_recommendation(tmp_path: Path) -> None:
    inputs = load_audit_inputs(_write_inputs(tmp_path))
    labels = build_rule_labels(inputs.actionable_rows)
    baseline = build_baseline_path_summary(inputs.actionable_rows)
    filter_comparison = build_filter_vs_baseline_comparison(inputs.actionable_rows, labels, baseline)

    exit_rows = build_baseline_exit_comparison(inputs.actionable_rows)
    recommendation = classify_recommendation(inputs.actionable_rows, filter_comparison, exit_rows)
    config = build_disabled_baseline_config(recommendation)

    assert {row["exit_rule_id"] for row in exit_rows} == {"E1", "E2", "E3", "E4"}
    assert recommendation["recommendation"] == "A_baseline_all_actionable_20k_with_filter_labels"
    assert recommendation["selected_exit_rule_id"] == "E2"
    assert config["enabled"] is False
    assert config["selected_entry_universe"] == "confirmed_actionable_crossed_20k"
    assert config["attached_filter_labels"] == ["B1", "B2", "B3", "B4"]


def test_run_writes_reports_and_keeps_config_disabled(tmp_path: Path) -> None:
    data_root = tmp_path / "lake"
    report_root = _write_inputs(data_root)

    result = run_baseline_vs_filter_audit(data_root=data_root, source_report_root=report_root, execute=True)

    audit_root = data_root / "data" / "backtests" / "diagnostics" / "reports" / "forward_observation" / "baseline_vs_filter_audit"
    config_path = data_root / "data" / "forward_observation" / "official_lifecycle_watch_v1" / "paper_shadow_starting_config.json"
    status_path = Path("theses/BASELINE_VS_FILTER_AUDIT_STATUS.md")
    assert result["execute"] is True
    assert result["baseline_actionable_crossed_20k_count"] == 4
    assert result["recommendation"] == "A_baseline_all_actionable_20k_with_filter_labels"
    assert (audit_root / "actionable_20k_rule_labels.csv").exists()
    assert (audit_root / "filter_vs_baseline_comparison.csv").exists()
    assert (audit_root / "baseline_exit_comparison.csv").exists()
    assert config_path.exists()
    assert json.loads(config_path.read_text(encoding="utf-8"))["enabled"] is False
    assert status_path.exists()


def test_audit_files_do_not_contain_runtime_execution_logic() -> None:
    guarded = [
        Path("research/mtp_research/validation/baseline_vs_filter_audit.py"),
        Path("research/mtp_research/validation/run_baseline_vs_filter_audit.py"),
    ]
    forbidden = ["send_transaction(", "sign_transaction(", "secret_key", "place_order(", "submit_order("]
    for path in guarded:
        text = path.read_text(encoding="utf-8").lower()
        for pattern in forbidden:
            assert pattern not in text


def _write_inputs(base: Path) -> Path:
    report_root = base / "data" / "backtests" / "diagnostics" / "reports" / "forward_observation" / "buy_exit_design"
    report_root.mkdir(parents=True, exist_ok=True)
    rows = [
        _row("mint-a", fdv20=28_000, max_fdv=190_000, reached_50k=True, reached_100k=False),
        _row("mint-b", fdv20=80_000, max_fdv=500_000, reached_50k=True, reached_100k=True, reached_500k=True),
        _row("mint-c", fdv20=25_000, max_fdv=30_000, reached_50k=False, drawdown=80),
        _row("mint-d", fdv20=1_000_000_000, max_fdv=1_000_000_000, reached_50k=True, reached_100k=True, anomaly=True),
    ]
    (report_root / "buy_exit_design_dataset.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    (report_root / "buy_exit_start_rule_design_summary.json").write_text(
        json.dumps({"all_crossed_20k_count": 8, "actionable_crossed_20k_count": 4, "quality_gate_result": "paper_start_candidate_data_limited"}),
        encoding="utf-8",
    )
    return report_root


def _row(
    mint: str,
    *,
    fdv20: float,
    max_fdv: float,
    reached_50k: bool,
    reached_100k: bool = False,
    reached_500k: bool = False,
    drawdown: float = 0,
    anomaly: bool = False,
) -> dict:
    return {
        "mint": mint,
        "actionable_sample_flag": True,
        "crossed_10k": True,
        "crossed_15k": True,
        "crossed_20k": True,
        "crossed_30k": reached_50k,
        "crossed_50k": reached_50k,
        "crossed_100k": reached_100k,
        "crossed_200k": reached_500k,
        "crossed_500k": reached_500k,
        "crossed_1m": False,
        "fdv_anomaly": anomaly,
        "fdv_at_10k": min(fdv20, 14_000),
        "fdv_at_15k": min(fdv20, 19_000),
        "fdv_at_20k": fdv20,
        "fdv_per_event_at_10k": min(fdv20, 14_000),
        "fdv_per_active_wallet_at_10k": min(fdv20, 14_000),
        "fdv_per_event_at_15k": min(fdv20, 19_000),
        "fdv_per_active_wallet_at_15k": min(fdv20, 19_000),
        "fdv_per_event_at_20k": fdv20,
        "fdv_per_active_wallet_at_20k": fdv20,
        "first_path_before_10k": True,
        "first_path_before_15k": True,
        "first_path_before_20k": True,
        "first_crossed_20k_time": 100,
        "first_crossed_30k_time": 140 if reached_50k else None,
        "10k_to_15k_seconds": 10,
        "10k_to_20k_seconds": 20,
        "15k_to_20k_seconds": 10,
        "create_to_15k_seconds": 30,
        "sell_count_at_15k": 0,
        "path_row_count": 3,
        "max_fdv_after_20k": max_fdv,
        "max_drawdown_after_20k": drawdown,
        "first_30pct_drawdown_time_after_entry": 120 if drawdown >= 30 else None,
        "first_40pct_drawdown_time_after_entry": 120 if drawdown >= 40 else None,
        "first_50pct_drawdown_time_after_entry": 120 if drawdown >= 50 else None,
        "reclaimed_after_30pct_drawdown": False if drawdown >= 30 else None,
        "reclaimed_after_40pct_drawdown": False if drawdown >= 40 else None,
        "reclaimed_after_50pct_drawdown": False if drawdown >= 50 else None,
        "time_to_peak_after_20k": 60,
        "maturity_state": "matured_reached_1m" if reached_500k else "trigger_qualified_active_watch",
    }
