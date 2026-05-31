import json
from pathlib import Path

from research.mtp_research.pipeline.evidence_audit_models import (
    EvidenceAuditReport,
    EvidenceStoreCount,
    TargetQualitySummary,
)
from research.mtp_research.pipeline.evidence_audit_report import (
    format_number,
    format_percent,
    report_to_dict,
    write_report_json,
    write_report_markdown,
)


def _report() -> EvidenceAuditReport:
    return EvidenceAuditReport(
        report_id="audit-1",
        created_at="2026-05-31T00:00:00+00:00",
        store_counts=[EvidenceStoreCount("candidate_registry", "candidates.jsonl", True, 2, 10)],
        target_quality=TargetQualitySummary(target_count=1, role_counts={"mint": 1}),
        bottleneck_stage="low_value_backfill_targets",
        top_warnings=["mint_only_targets"],
        recommended_next_actions=["seed candidates with pool_address and creator_wallet"],
    )


def test_report_to_dict_serializes() -> None:
    payload = report_to_dict(_report())

    assert payload["report_id"] == "audit-1"
    assert payload["target_quality"]["role_counts"] == {"mint": 1}


def test_write_report_json_writes_valid_json(tmp_path: Path) -> None:
    path = write_report_json(_report(), tmp_path / "audit.json")

    assert json.loads(path.read_text(encoding="utf-8"))["bottleneck_stage"] == "low_value_backfill_targets"


def test_write_report_markdown_writes_readable_markdown(tmp_path: Path) -> None:
    path = write_report_markdown(_report(), tmp_path / "audit.md")
    text = path.read_text(encoding="utf-8")

    assert "# Evidence Run Audit" in text
    assert "low_value_backfill_targets" in text
    assert "Target Quality" in text
    assert "seed candidates" in text
    assert "diagnostic only and is not a trading signal" in text


def test_format_helpers_handle_none() -> None:
    assert format_percent(None) == "n/a"
    assert format_number(None) == "n/a"
    assert format_percent(0.5) == "50.00%"
    assert format_number(12.345) == "12.35"
