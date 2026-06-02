import csv
import json
from pathlib import Path

from research.mtp_research.validation.run_t011_explosive_runner_validation import main


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


def test_t011_validation_cli_writes_outputs(tmp_path: Path, monkeypatch, capsys) -> None:
    design = _write_json(
        tmp_path / "design.json",
        {"validation_design": {"primary_split": {"train_pct": 60}, "primary_outcome": "crossed_100k_after_20k"}},
    )
    rows = []
    for idx in range(10):
        rows.append(
            {
                "token_mint": f"mint-{idx}",
                "launch_id": f"launch-{idx}",
                "creator": f"creator-{idx % 3}",
                "launch_ts": 1_700_000_000 + idx,
                "trigger_age_seconds": 60,
                "trigger_fdv_proxy": 20_000,
                "peak_fdv_proxy": 100_000,
                "milestone_tier": "reached_1m_plus" if idx >= 6 else "reached_20k_but_never_50k",
                "event_count_at_20k": 1 if idx >= 6 else 10,
                "buy_count_at_20k": 1 if idx >= 6 else 8,
                "sell_count_at_20k": 0 if idx >= 6 else 2,
                "active_wallets_at_20k": 1 if idx >= 6 else 5,
                "crossed_100k_after_20k": idx >= 6,
            }
        )
    rows_path = _write_csv(tmp_path / "rows.csv", rows)
    output_dir = tmp_path / "reports"
    status_path = tmp_path / "STATUS.md"
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_t011_explosive_runner_validation",
            "--design-path",
            str(design),
            "--trigger-20k-rows-path",
            str(rows_path),
            "--output-dir",
            str(output_dir),
            "--status-path",
            str(status_path),
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out

    assert "report_id=t011_explosive_runner_validation_v0" in output
    assert (output_dir / "T011_validation_summary.json").exists()
    assert (output_dir / "T011_validation_summary.md").exists()
    assert (output_dir / "T011_holdout_rows.csv").exists()
    assert "No trading rules were generated." in status_path.read_text(encoding="utf-8")
