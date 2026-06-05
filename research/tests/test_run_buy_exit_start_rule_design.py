import json
from pathlib import Path

from research.mtp_research.validation.run_buy_exit_start_rule_design import main


def test_run_buy_exit_start_rule_design_cli_execute(tmp_path: Path, monkeypatch) -> None:
    data_root = tmp_path / "lake"
    source_root = _write_sample(data_root / "data" / "forward_observation" / "combined_samples" / "fixed")
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_buy_exit_start_rule_design",
            "--data-root",
            str(data_root),
            "--source-root",
            str(source_root),
            "--execute",
        ],
    )

    exit_code = main()

    assert exit_code == 0
    assert (
        data_root
        / "data"
        / "backtests"
        / "diagnostics"
        / "reports"
        / "forward_observation"
        / "buy_exit_design"
        / "buy_exit_start_rule_design_summary.json"
    ).exists()


def test_run_buy_exit_start_rule_design_cli_dry_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["run_buy_exit_start_rule_design", "--data-root", str(tmp_path)])

    exit_code = main()

    assert exit_code == 0


def _write_sample(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    births = [
        {
            "mint": "mint-a",
            "sample_label": "fixed_sample",
            "source_provenance": "helius_birth_watch_followup",
            "create_time": 100,
            "observed_time": 101,
            "first_followup_attempt_time": 102,
            "freshness_class": "fresh",
            "fdv_path_before_10k": True,
            "fdv_path_before_20k": True,
            "first_followup_before_10k": True,
            "first_followup_before_20k": True,
        }
    ]
    paths = [
        {
            "mint": "mint-a",
            "timestamp": 130,
            "fdv_proxy": 22_000,
            "sample_label": "fixed_sample",
            "source_provenance": "helius_birth_watch_followup",
            "crossed_10k": True,
            "crossed_15k": True,
            "crossed_20k": True,
            "event_count": 5,
            "buy_count": 4,
            "sell_count": 1,
            "active_wallet_count": 4,
            "fdv_per_event": 4400,
            "fdv_per_active_wallet": 5500,
            "drawdown_pct": 0,
            "local_high_fdv": 22_000,
        }
    ]
    for name, rows in {
        "births.jsonl": births,
        "followup_paths.jsonl": paths,
        "events.jsonl": paths,
        "metadata.jsonl": [],
        "drawdowns.jsonl": [],
        "lifecycle_transitions.jsonl": [],
    }.items():
        (root / name).write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    (root / "lifecycle_state.json").write_text(json.dumps({"mints": {"mint-a": {"state": "trigger_qualified_active_watch"}}}), encoding="utf-8")
    (root / "official_lifecycle_manifest.json").write_text(json.dumps({"sample_label": "fixed_sample"}), encoding="utf-8")
    return root
