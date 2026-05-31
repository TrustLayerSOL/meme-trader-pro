"""Filesystem thesis registry loader."""

from __future__ import annotations

from pathlib import Path

from research.mtp_research.validation.thesis_models import (
    ThesisReference,
    normalize_thesis_id,
)


REQUIRED_FIELDS = {"thesis_id", "name", "status", "priority", "strategy_family"}


class ThesisRegistry:
    """Load flat Markdown thesis files with lightweight frontmatter parsing."""

    def __init__(self, theses_dir: Path | str = "theses"):
        self.theses_dir = Path(theses_dir)

    def load_theses(self) -> list[ThesisReference]:
        if not self.theses_dir.exists():
            return []
        theses: list[ThesisReference] = []
        for path in sorted(self.theses_dir.glob("MTP-T*.md")):
            thesis = self._load_thesis_file(path)
            if thesis is not None:
                theses.append(thesis)
        return theses

    def get_by_id(self, thesis_id: str) -> ThesisReference | None:
        normalized = normalize_thesis_id(thesis_id)
        for thesis in self.load_theses():
            if thesis.thesis_id == normalized:
                return thesis
        return None

    def list_active(self) -> list[ThesisReference]:
        return self.list_by_status("active")

    def list_by_status(self, status: str) -> list[ThesisReference]:
        return [thesis for thesis in self.load_theses() if thesis.status == status]

    def list_by_strategy_family(self, strategy_family: str) -> list[ThesisReference]:
        return [
            thesis for thesis in self.load_theses()
            if thesis.strategy_family == strategy_family
        ]

    def _load_thesis_file(self, path: Path) -> ThesisReference | None:
        text = path.read_text(encoding="utf-8")
        metadata = _parse_frontmatter(text)
        warnings = []
        missing = sorted(REQUIRED_FIELDS - set(metadata))
        if missing:
            warnings.append(f"missing_required_fields:{','.join(missing)}")
        thesis_id = normalize_thesis_id(metadata.get("thesis_id") or path.stem.split("-")[0])
        return ThesisReference(
            thesis_id=thesis_id,
            name=metadata.get("name", path.stem),
            status=metadata.get("status", "malformed"),
            priority=metadata.get("priority", "unknown"),
            strategy_family=metadata.get("strategy_family", "unknown"),
            current_stage=metadata.get("current_stage", "research"),
            linked_rule_ids=_parse_bullet_section(text, "Linked Rules"),
            required_features=_parse_bullet_section(text, "Required Features"),
            required_data_sources=_parse_bullet_section(text, "Required Data"),
            promotion_criteria=_parse_bullet_section(text, "Promotion Criteria"),
            rejection_criteria=_parse_bullet_section(text, "Rejection Criteria"),
            known_gaps=_parse_bullet_section(text, "Known Gaps"),
            metadata_json={
                "path": str(path),
                "frontmatter": metadata,
                "warning_flags": warnings,
            },
        )


def _parse_frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    output: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        output[key.strip()] = value.strip().strip('"').strip("'")
    return output


def _parse_bullet_section(text: str, section_name: str) -> list[str]:
    lines = text.splitlines()
    in_section = False
    output: list[str] = []
    header = f"# {section_name}"
    for line in lines:
        stripped = line.strip()
        if stripped == header:
            in_section = True
            continue
        if in_section and stripped.startswith("# "):
            break
        if in_section and stripped.startswith("- "):
            value = stripped[2:].strip()
            if value.lower() != "none yet." and value.lower() != "none":
                output.append(value)
    return output
