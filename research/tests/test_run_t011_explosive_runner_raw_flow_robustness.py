import csv
import json
from pathlib import Path

from research.mtp_research.validation.run_t011_explosive_runner_raw_flow_robustness import main


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _write_csv(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_t011_robustness_cli_writes_outputs(tmp_path: Path, monkeypatch, capsys) -> None:
    summary_path = _write_json(tmp_path / "summary.json", {"final_classification": "descriptive_signal_present"})
    rows_path = _write_csv(
        tmp_path / "rows.csv",
        [
            {
                "token_mint": "mint-a",
                "launch_id": "launch-a",
                "creator": "creator-a",
                "launch_ts": 1_700_000_000,
                "trigger_age_seconds": 60,
                "trigger_fdv_proxy": 20_000,
                "peak_fdv_proxy": 100_000,
                "milestone_tier": "reached_1m_plus",
                "event_count_at_20k": 4,
                "buy_count_at_20k": 3,
                "sell_count_at_20k": 1,
                "active_wallets_at_20k": 3,
                "crossed_100k_after_20k": True,
                "crossed_500k_after_20k": True,
            }
        ],
    )
    snapshots_path = _write_json(tmp_path / "snapshots.jsonl", {})
    output_dir = tmp_path / "reports"
    status_path = tmp_path / "STATUS.md"
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_t011_explosive_runner_raw_flow_robustness",
            "--t011-summary-path",
            str(summary_path),
            "--trigger-20k-rows-path",
            str(rows_path),
            "--snapshots-path",
            str(snapshots_path),
            "--output-dir",
            str(output_dir),
            "--status-path",
            str(status_path),
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out

    assert "report_id=t011_explosive_runner_raw_flow_robustness_v0" in output
    assert (output_dir / "T011_explosive_runner_raw_flow_robustness_summary.json").exists()
    assert (output_dir / "T011_explosive_runner_raw_flow_robustness_summary.md").exists()
    assert (output_dir / "robustness_split_table.csv").exists()
    assert "No validation was run." in status_path.read_text(encoding="utf-8")
