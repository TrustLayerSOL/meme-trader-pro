import json
from pathlib import Path

from research.mtp_research.validation.run_confirmed_rule_discovery import main


def test_run_confirmed_rule_discovery_cli_execute(tmp_path: Path, monkeypatch) -> None:
    data_root = tmp_path / "lake"
    source_root = _write_sample(data_root / "data" / "forward_observation" / "official_lifecycle_watch_v2")
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_confirmed_rule_discovery",
            "--data-root",
            str(data_root),
            "--source-root",
            str(source_root),
            "--execute",
        ],
    )

    assert main() == 0

    report_root = (
        data_root
        / "data"
        / "backtests"
        / "diagnostics"
        / "reports"
        / "forward_observation"
        / "confirmed_rule_discovery"
    )
    assert (report_root / "confirmed_rule_discovery_summary.json").exists()
    summary = json.loads((report_root / "confirmed_rule_discovery_summary.json").read_text(encoding="utf-8"))
    assert summary["confirmed_actionable_crossed_20k_count"] == 1


def test_run_confirmed_rule_discovery_cli_dry_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["run_confirmed_rule_discovery", "--data-root", str(tmp_path)])

    assert main() == 0


def _write_sample(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    birth = {
        "mint": "confirmed-mint",
        "official_accepted_birth": True,
        "fdv_path_before_10k": True,
        "fdv_path_before_15k": True,
        "fdv_path_before_20k": True,
        "valid_fdv_path_provenance": True,
        "first_fdv_path_fdv": 8_000,
    }
    paths = [
        {"mint": "confirmed-mint", "timestamp": 100, "fdv_proxy": 22_000, "crossed_20k": True},
        {"mint": "confirmed-mint", "timestamp": 130, "fdv_proxy": 24_000, "crossed_20k": True},
    ]
    (root / "births.jsonl").write_text(json.dumps(birth) + "\n", encoding="utf-8")
    (root / "followup_paths.jsonl").write_text("".join(json.dumps(row) + "\n" for row in paths), encoding="utf-8")
    (root / "lifecycle_state.json").write_text(json.dumps({"mints": {"confirmed-mint": {"state": "trigger_qualified_active_watch"}}}), encoding="utf-8")
    return root
