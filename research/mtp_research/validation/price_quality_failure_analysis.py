"""Token-level analysis for strict price-quality gate failures."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from research.mtp_research.validation.price_quality_models import PriceQualityDecision, PriceQualityGateReport
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow


@dataclass
class PriceQualityTokenFailureSummary:
    token_mint: str
    input_row_count: int = 0
    failed_row_count: int = 0
    passed_row_count: int = 0
    failure_rate: float | None = None
    failure_reason_counts: dict[str, int] = field(default_factory=dict)
    entry_source_counts: dict[str, int] = field(default_factory=dict)
    label_quality_counts: dict[str, int] = field(default_factory=dict)
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class PriceQualityFailureAnalysisReport:
    report_id: str
    created_at: str
    dataset_path: str = ""
    input_row_count: int = 0
    failed_row_count: int = 0
    passed_row_count: int = 0
    token_count: int = 0
    failed_token_count: int = 0
    failure_reason_counts: dict[str, int] = field(default_factory=dict)
    failure_combo_counts: dict[str, int] = field(default_factory=dict)
    top_tokens: list[PriceQualityTokenFailureSummary] = field(default_factory=list)
    recommended_next_action: str = "manual_price_quality_review"
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)


class PriceQualityFailureAnalyzer:
    """Summarize where strict price-quality filtering is losing rows."""

    def build_report(
        self,
        rows: list[ResearchDatasetRow],
        decisions: list[PriceQualityDecision],
        gate_report: PriceQualityGateReport,
        top_n: int = 10,
    ) -> PriceQualityFailureAnalysisReport:
        row_by_id = {row.row_id: row for row in rows}
        decisions_by_token: dict[str, list[PriceQualityDecision]] = defaultdict(list)
        rows_by_token: dict[str, list[ResearchDatasetRow]] = defaultdict(list)
        failure_reasons: Counter[str] = Counter()
        failure_combos: Counter[str] = Counter()

        for row in rows:
            rows_by_token[row.token_mint].append(row)
        for decision in decisions:
            decisions_by_token[decision.token_mint].append(decision)
            if decision.reasons_failed:
                failure_reasons.update(decision.reasons_failed)
                failure_combos[_combo_key(decision.reasons_failed)] += 1

        token_summaries = [
            _summarize_token(token, token_rows, decisions_by_token.get(token, []))
            for token, token_rows in rows_by_token.items()
        ]
        token_summaries.sort(
            key=lambda item: (
                -item.failed_row_count,
                -(item.failure_rate or 0.0),
                item.token_mint,
            )
        )
        failed_token_count = sum(1 for item in token_summaries if item.failed_row_count)
        warning_flags = _warning_flags(gate_report, failure_reasons)
        return PriceQualityFailureAnalysisReport(
            report_id=make_price_quality_failure_analysis_report_id(),
            created_at=utc_now_iso(),
            dataset_path=gate_report.dataset_path,
            input_row_count=len(rows),
            failed_row_count=sum(1 for decision in decisions if not decision.passed),
            passed_row_count=sum(1 for decision in decisions if decision.passed),
            token_count=len(rows_by_token),
            failed_token_count=failed_token_count,
            failure_reason_counts=dict(sorted(failure_reasons.items())),
            failure_combo_counts=dict(sorted(failure_combos.items())),
            top_tokens=token_summaries[:top_n],
            recommended_next_action=_recommended_next_action(failure_reasons, gate_report),
            warning_flags=warning_flags,
            metadata_json={
                "gate_report_id": gate_report.report_id,
                "top_n": top_n,
                "row_ids_reviewed": len(row_by_id),
            },
        )


def report_to_dict(report: PriceQualityFailureAnalysisReport) -> dict[str, Any]:
    return asdict(report)


def write_report_json(report: PriceQualityFailureAnalysisReport, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report_to_dict(report), indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_report_markdown(report: PriceQualityFailureAnalysisReport, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Price Quality Failure Analysis",
        "",
        "## What This Report Does",
        "",
        "Identifies which tokens and price-quality failure combinations are driving row loss in the strict diagnostic gate.",
        "",
        f"- Report ID: `{report.report_id}`",
        f"- Input rows: `{report.input_row_count}`",
        f"- Failed rows: `{report.failed_row_count}`",
        f"- Passed rows: `{report.passed_row_count}`",
        f"- Token count: `{report.token_count}`",
        f"- Failed token count: `{report.failed_token_count}`",
        f"- Recommended next action: `{report.recommended_next_action}`",
        f"- Warning flags: `{', '.join(report.warning_flags) if report.warning_flags else 'none'}`",
        "",
        "## Failure Reasons",
        "",
    ]
    for reason, count in report.failure_reason_counts.items():
        lines.append(f"- `{reason}`: `{count}`")
    lines.extend(["", "## Failure Combinations", ""])
    for combo, count in report.failure_combo_counts.items():
        lines.append(f"- `{combo}`: `{count}`")
    lines.extend(["", "## Top Failing Tokens", ""])
    lines.append("| token | failed rows | input rows | failure rate | top reasons |")
    lines.append("|---|---:|---:|---:|---|")
    for item in report.top_tokens:
        top_reasons = ", ".join(f"{reason}:{count}" for reason, count in item.failure_reason_counts.items())
        failure_rate = "" if item.failure_rate is None else f"{item.failure_rate:.4f}"
        lines.append(
            f"| `{item.token_mint}` | {item.failed_row_count} | {item.input_row_count} | "
            f"{failure_rate} | {top_reasons or 'none'} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def make_price_quality_failure_analysis_report_id(prefix: str = "price_quality_failure_analysis") -> str:
    created = utc_now_iso()
    digest = sha256(f"{prefix}|{created}".encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _summarize_token(
    token_mint: str,
    rows: list[ResearchDatasetRow],
    decisions: list[PriceQualityDecision],
) -> PriceQualityTokenFailureSummary:
    failed = [decision for decision in decisions if not decision.passed]
    reasons: Counter[str] = Counter()
    for decision in failed:
        reasons.update(decision.reasons_failed)
    return PriceQualityTokenFailureSummary(
        token_mint=token_mint,
        input_row_count=len(rows),
        failed_row_count=len(failed),
        passed_row_count=len(rows) - len(failed),
        failure_rate=(len(failed) / len(rows)) if rows else None,
        failure_reason_counts=dict(sorted(reasons.items())),
        entry_source_counts=dict(sorted(Counter(row.entry_price_source or "missing" for row in rows).items())),
        label_quality_counts=dict(sorted(Counter(row.label_quality for row in rows).items())),
    )


def _combo_key(reasons: list[str]) -> str:
    return "+".join(sorted(reasons)) if reasons else "passed"


def _warning_flags(gate_report: PriceQualityGateReport, failure_reasons: Counter[str]) -> list[str]:
    warnings = ["diagnostic_only_not_trading_signal"]
    failed = gate_report.failed_row_count or 0
    if failed and failure_reasons.get("nearest_fallback_disallowed", 0) / failed >= 0.5:
        warnings.append("fallback_rows_dominate_failures")
    if failed and failure_reasons.get("insufficient_future_price_points", 0) / failed >= 0.4:
        warnings.append("future_price_points_dominate_failures")
    if failed and failure_reasons.get("stale_entry_price", 0) / failed >= 0.25:
        warnings.append("stale_entries_material")
    return warnings


def _recommended_next_action(failure_reasons: Counter[str], gate_report: PriceQualityGateReport) -> str:
    failed = gate_report.failed_row_count or 0
    if not failed:
        return "continue_gated_validation_review"
    fallback_share = failure_reasons.get("nearest_fallback_disallowed", 0) / failed
    future_share = failure_reasons.get("insufficient_future_price_points", 0) / failed
    stale_share = failure_reasons.get("stale_entry_price", 0) / failed
    if fallback_share >= 0.5:
        return "improve_price_inference_before_scaling"
    if future_share >= 0.4:
        return "expand_future_price_coverage_before_rule_review"
    if stale_share >= 0.25:
        return "tighten_entry_price_timestamp_alignment"
    return "manual_price_quality_review"
