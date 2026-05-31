import json
from pathlib import Path

from research.mtp_research.pipeline.run_seed_candidates import main


def test_seed_candidates_cli_works_against_temp_paths(tmp_path: Path, monkeypatch, capsys) -> None:
    seed_path = tmp_path / "seeds.jsonl"
    registry_path = tmp_path / "registry.jsonl"
    seed_path.write_text(
        json.dumps({"token_mint": "mint-1", "source": "manual", "first_seen_ts": "2026-05-31T00:00:00+00:00"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        ["run_seed_candidates", "--seed-path", str(seed_path), "--registry-path", str(registry_path)],
    )
    assert main() == 0
    output = capsys.readouterr().out
    assert "inserted=1" in output
    assert "network_calls=0" in output


def test_seed_candidates_cli_writes_example(tmp_path: Path, monkeypatch, capsys) -> None:
    seed_path = tmp_path / "example.jsonl"
    monkeypatch.setattr("sys.argv", ["run_seed_candidates", "--seed-path", str(seed_path), "--write-example"])
    assert main() == 0
    assert seed_path.exists()
    assert "example_seed_path=" in capsys.readouterr().out
