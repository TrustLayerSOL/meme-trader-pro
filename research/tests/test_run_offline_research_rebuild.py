from pathlib import Path

from research.mtp_research.pipeline.run_offline_research_rebuild import main


def test_offline_rebuild_cli_works_with_temp_stores(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_offline_research_rebuild",
            "--raw-path",
            str(tmp_path / "raw.jsonl"),
            "--events-path",
            str(tmp_path / "events.jsonl"),
            "--features-path",
            str(tmp_path / "features.jsonl"),
            "--outcomes-path",
            str(tmp_path / "outcomes.jsonl"),
            "--dataset-path",
            str(tmp_path / "dataset.jsonl"),
        ],
    )
    assert main() == 0
    output = capsys.readouterr().out
    assert "network_calls=0" in output
    assert "offline_rebuild_no_network_calls" in output
