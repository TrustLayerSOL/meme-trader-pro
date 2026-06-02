from pathlib import Path

from research.mtp_research.validation.run_p0_creator_funder_transfer_graph_collection import main


def test_cli_dry_run_writes_creator_funder_report(tmp_path: Path, monkeypatch, capsys) -> None:
    target_path = tmp_path / "targets.csv"
    target_path.write_text(
        "candidate_funder,common_funder_candidate_id,creator,funding_signature,launch_id,milestone_tier,mint,reason_selected\n"
        "funder-a,funder-funder-a,creator-a,sig-a,launch-a,never_reached_20k,mint-a,test\n",
        encoding="utf-8",
    )
    candidates_path = tmp_path / "candidates.jsonl"
    candidates_path.write_text(
        '{"launch_id":"launch-a","token_mint":"mint-a","launch_ts":1000,"launch_time_utc":"1970-01-01T00:16:40+00:00"}\n',
        encoding="utf-8",
    )
    output_dir = tmp_path / "reports"
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_p0_creator_funder_transfer_graph_collection",
            "--target-path",
            str(target_path),
            "--candidates-path",
            str(candidates_path),
            "--raw-dir",
            str(tmp_path / "raw"),
            "--jsonl-path",
            str(tmp_path / "graph.jsonl"),
            "--parquet-path",
            str(tmp_path / "graph.parquet"),
            "--checkpoint-path",
            str(tmp_path / "checkpoint.json"),
            "--report-dir",
            str(output_dir),
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "report_id=creator_funder_transfer_graph_pilot_v0" in output
    assert "mode=dry_run" in output
    assert "creators_attempted=0" in output
    assert "requests_used=0" in output
    assert (output_dir / "creator_funder_transfer_graph_pilot_summary.json").exists()
    assert (output_dir / "creator_funder_transfer_graph_pilot_summary.md").exists()
