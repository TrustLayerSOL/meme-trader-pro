import json
import sys
from pathlib import Path

from research.mtp_research.validation.run_forward_paper_shadow import main as paper_shadow_main
from research.mtp_research.validation.run_partial_forward_strategy_preview import main as preview_main


def test_partial_forward_strategy_preview_cli_dry_run(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_partial_forward_strategy_preview",
            "--data-root",
            str(tmp_path),
        ],
    )

    assert preview_main() == 0

    output = capsys.readouterr().out
    assert "Partial Forward Strategy Preview" in output
    assert "execute=False" in output
    assert "partial_birth_coverage_long_lifecycle_sample" in output


def test_partial_forward_strategy_preview_cli_execute(tmp_path: Path, monkeypatch, capsys) -> None:
    source_root = tmp_path / "source"
    _write_minimal_source(source_root)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_partial_forward_strategy_preview",
            "--data-root",
            str(tmp_path),
            "--source-root",
            str(source_root),
            "--execute",
        ],
    )

    assert preview_main() == 0

    output = capsys.readouterr().out
    assert "execute=True" in output
    assert "rows_mints_analyzed=1" in output


def test_forward_paper_shadow_cli_execute_creates_disabled_config(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_forward_paper_shadow", "--data-root", str(tmp_path), "--execute"],
    )

    assert paper_shadow_main() == 0

    output = capsys.readouterr().out
    assert "enabled=False" in output
    config_path = tmp_path / "data" / "forward_observation" / "official_lifecycle_watch_v1" / "paper_shadow_rule_candidates.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["enabled"] is False


def _write_minimal_source(source_root: Path) -> None:
    source_root.mkdir(parents=True, exist_ok=True)
    birth = {
        "mint": "mint-a",
        "create_time": 100,
        "observed_time": 101,
        "first_followup_attempt_time": 102,
        "create_to_first_followup_seconds": 2,
        "first_followup_before_10k": True,
        "first_followup_before_20k": True,
        "observation_id": "obs-a",
    }
    path = {
        "mint": "mint-a",
        "timestamp": 110,
        "fdv_proxy": 12_000,
        "event_count": 3,
        "buy_count": 2,
        "sell_count": 1,
        "active_wallet_count": 2,
        "fdv_per_event": 4000,
        "fdv_per_buy": 6000,
        "fdv_per_active_wallet": 6000,
        "buy_sell_ratio": 2,
    }
    (source_root / "births.jsonl").write_text(json.dumps(birth) + "\n", encoding="utf-8")
    (source_root / "followup_paths.jsonl").write_text(json.dumps(path) + "\n", encoding="utf-8")
    for name in ["events.jsonl", "metadata.jsonl", "drawdowns.jsonl", "lifecycle_transitions.jsonl"]:
        (source_root / name).write_text("", encoding="utf-8")
    (source_root / "lifecycle_state.json").write_text(json.dumps({"mints": {"mint-a": {"state": "crossed_10k"}}}), encoding="utf-8")
    (source_root / "status.json").write_text("{}", encoding="utf-8")
