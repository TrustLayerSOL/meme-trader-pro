import csv
from pathlib import Path

from research.mtp_research.validation.run_p0_helius_early_buyer_collection import main


def _write_targets(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "wallet",
                "current_launch_id",
                "current_mint",
                "first_seen_in_launch_time",
                "reason_selected",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "wallet": "wallet-a",
                "current_launch_id": "launch-a",
                "current_mint": "mint-a",
                "first_seen_in_launch_time": 1_700_000_000,
                "reason_selected": "early_buyer_before_20k_trigger",
            }
        )
    return path


def test_cli_dry_run_writes_report_with_explicit_paths(tmp_path: Path, capsys) -> None:
    result = main(
        [
            "--target-csv-path",
            str(_write_targets(tmp_path / "targets.csv")),
            "--raw-path",
            str(tmp_path / "raw.jsonl"),
            "--jsonl-path",
            str(tmp_path / "history.jsonl"),
            "--parquet-path",
            str(tmp_path / "history.parquet"),
            "--checkpoint-path",
            str(tmp_path / "checkpoint.json"),
            "--report-dir",
            str(tmp_path / "reports"),
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "report_id=p0_early_buyer_wallet_history_pilot_v0" in output
    assert "mode=dry_run" in output
    assert "network_calls_made=0" in output
    assert (tmp_path / "reports" / "early_buyer_wallet_history_pilot_summary.json").exists()
