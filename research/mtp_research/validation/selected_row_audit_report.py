"""Report writers for selected-row diagnostic audits."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from research.mtp_research.validation.selected_row_audit_models import (
    RuleSelectedRowAudit,
    SelectedRowAuditReport,
)


WARNING_TEXT = "Selected row audit is diagnostic only. It is not a trading signal."


def report_to_dict(report: SelectedRowAuditReport) -> dict[str, Any]:
    return asdict(report)


def write_report_json(report: SelectedRowAuditReport, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report_to_dict(report), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_report_markdown(report: SelectedRowAuditReport, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Selected Row + Price Trust Audit",
        "",
        f"> Warning: {WARNING_TEXT}",
        "",
        "## Summary",
        "",
        f"- Report ID: `{report.report_id}`",
        f"- Dataset path: `{report.dataset_path}`",
        f"- Row count: `{report.row_count}`",
        f"- Audited rules: `{report.audited_rule_ids}`",
        f"- Recommended next action: `{report.recommended_next_action}`",
        f"- Warning flags: `{report.warning_flags}`",
        "",
        "## Summary By Rule",
        "",
        "| Rule | Selected | Tokens | Win Rate | Median Return | Outlier Share | Fallback Rate | Stale Rate | Warnings |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for audit in report.rule_audits:
        lines.append(
            "| "
            f"`{audit.rule_id}` | "
            f"{audit.selected_count} | "
            f"{audit.token_count} | "
            f"{_fmt(audit.win_rate)} | "
            f"{_fmt(audit.median_forward_return)} | "
            f"{_fmt(audit.outlier_return_share)} | "
            f"{_fmt(audit.fallback_entry_rate)} | "
            f"{_fmt(audit.stale_entry_rate)} | "
            f"`{audit.warning_flags}` |"
        )
    lines.extend(["", "## Rule Details", ""])
    for audit in report.rule_audits:
        _append_rule_detail(lines, audit)
    lines.extend(
        [
            "## Cross-Rule Findings",
            "",
            *[f"- `{finding}`" for finding in report.cross_rule_findings],
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _append_rule_detail(lines: list[str], audit: RuleSelectedRowAudit) -> None:
    lines.extend(
        [
            f"### `{audit.rule_id}`",
            "",
            f"- Rule name: `{audit.rule_name}`",
            f"- Rule warning flags: `{audit.warning_flags}`",
            f"- Outlier concentration: `{_fmt(audit.outlier_return_share)}`",
            f"- Token concentration: `{audit.token_concentration}`",
            f"- Entry price source mix: `{_entry_source_mix(audit)}`",
            "",
            "#### Top Selected Rows By Forward Return",
            "",
            "| Row | Token | Snapshot | Source | Staleness | Forward | Net | Runup | Warnings |",
            "| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for record in _top_records(audit, reverse=True):
        lines.append(_record_table_row(record_to_dict(record)))
    lines.extend(
        [
            "",
            "#### Worst Selected Rows By Forward Return",
            "",
            "| Row | Token | Snapshot | Source | Staleness | Forward | Net | Runup | Warnings |",
            "| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for record in _top_records(audit, reverse=False):
        lines.append(_record_table_row(record_to_dict(record)))
    lines.append("")


def record_to_dict(record) -> dict[str, Any]:
    return asdict(record)


def _top_records(audit: RuleSelectedRowAudit, reverse: bool) -> list:
    return sorted(
        [record for record in audit.records if record.forward_return is not None],
        key=lambda record: record.forward_return or 0.0,
        reverse=reverse,
    )[:25]


def _record_table_row(record: dict[str, Any]) -> str:
    return (
        "| "
        f"`{record['row_id']}` | "
        f"`{record['token_mint']}` | "
        f"{record['snapshot_ts']} | "
        f"`{record.get('entry_price_source')}` | "
        f"{record.get('entry_price_staleness_sec') or ''} | "
        f"{_fmt(record.get('forward_return'))} | "
        f"{_fmt(record.get('net_return_estimate'))} | "
        f"{_fmt(record.get('max_runup'))} | "
        f"`{record.get('warning_flags', [])}` |"
    )


def _entry_source_mix(audit: RuleSelectedRowAudit) -> dict[str, int]:
    output: dict[str, int] = {}
    for record in audit.records:
        key = record.entry_price_source or "unknown"
        output[key] = output.get(key, 0) + 1
    return dict(sorted(output.items()))


def _fmt(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}"
