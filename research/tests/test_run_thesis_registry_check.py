from pathlib import Path

from research.mtp_research.validation.run_thesis_registry_check import main


def _write_thesis(path: Path, thesis_id: str) -> None:
    path.write_text(
        f"""---
thesis_id: {thesis_id}
name: Test Thesis
status: active
priority: high
strategy_family: test
current_stage: research
---

# Linked Rules
- rule-1
""",
        encoding="utf-8",
    )


def test_registry_check_cli_works_on_temp_theses_dir(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_thesis(tmp_path / "MTP-T999-a.md", "MTP-T999")
    monkeypatch.setattr("sys.argv", ["run_thesis_registry_check", "--theses-dir", str(tmp_path)])
    assert main() == 0
    output = capsys.readouterr().out
    assert "thesis_count=1" in output
    assert "MTP-T999: Test Thesis" in output


def test_registry_check_cli_detects_duplicate_ids(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_thesis(tmp_path / "MTP-T999-a.md", "MTP-T999")
    _write_thesis(tmp_path / "MTP-T998-b.md", "MTP-T999")
    monkeypatch.setattr("sys.argv", ["run_thesis_registry_check", "--theses-dir", str(tmp_path)])
    assert main() == 1
    assert "duplicate_thesis_id" in capsys.readouterr().out
