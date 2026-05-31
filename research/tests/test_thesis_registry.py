from pathlib import Path

from research.mtp_research.validation.thesis_registry import ThesisRegistry


def _write_thesis(path: Path, thesis_id: str = "MTP-T999", status: str = "active") -> Path:
    path.write_text(
        f"""---
thesis_id: {thesis_id}
name: Test Thesis
status: {status}
priority: high
strategy_family: test_family
current_stage: research
---

# Thesis
Test thesis.

# Linked Rules
- positive_flow_basic

# Required Features
- flow

# Required Data
- rows

# Promotion Criteria
- evidence

# Rejection Criteria
- no evidence

# Known Gaps
- sample size
""",
        encoding="utf-8",
    )
    return path


def test_loads_thesis_files_and_parses_frontmatter(tmp_path: Path) -> None:
    _write_thesis(tmp_path / "MTP-T999-test.md")
    thesis = ThesisRegistry(tmp_path).load_theses()[0]
    assert thesis.thesis_id == "MTP-T999"
    assert thesis.name == "Test Thesis"
    assert thesis.status == "active"
    assert thesis.linked_rule_ids == ["positive_flow_basic"]
    assert thesis.required_features == ["flow"]


def test_get_by_id_and_filters_work(tmp_path: Path) -> None:
    _write_thesis(tmp_path / "MTP-T999-test.md", "MTP-T999", "active")
    _write_thesis(tmp_path / "MTP-T998-test.md", "MTP-T998", "planned")
    registry = ThesisRegistry(tmp_path)
    assert registry.get_by_id("mtp-t999").thesis_id == "MTP-T999"
    assert [thesis.thesis_id for thesis in registry.list_active()] == ["MTP-T999"]
    assert [thesis.thesis_id for thesis in registry.list_by_status("planned")] == ["MTP-T998"]
    assert len(registry.list_by_strategy_family("test_family")) == 2


def test_malformed_thesis_file_does_not_crash_registry(tmp_path: Path) -> None:
    (tmp_path / "MTP-T997-bad.md").write_text("# Bad\nNo frontmatter", encoding="utf-8")
    theses = ThesisRegistry(tmp_path).load_theses()
    assert len(theses) == 1
    assert "missing_required_fields" in theses[0].metadata_json["warning_flags"][0]
