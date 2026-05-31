"""Compare clean labels against diagnostic nearest-entry fallback labels."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from research.mtp_research.validation.entry_price_coverage_models import (
    EntryPriceCoverageComparison,
    EntryPriceCoverageSummary,
    make_entry_price_coverage_report_id,
)
from research.mtp_research.validation.outcome_label_store import OutcomeLabelStore
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore


SPARSE_OR_BETTER = {"sparse", "good"}


def summarize_outcomes(
    path: Path | str,
    dataset_path: Path | str | None = None,
    name: str = "clean",
) -> EntryPriceCoverageSummary:
    labels = OutcomeLabelStore(path).load_all()
    source_counts = Counter(label.entry_price_source or "missing" for label in labels)
    quality_counts = Counter(label.label_quality for label in labels)
    return EntryPriceCoverageSummary(
        name=name,
        outcome_path=str(path),
        dataset_path=str(dataset_path) if dataset_path else None,
        total_labels=len(labels),
        labels_with_entry_price=sum(1 for label in labels if label.entry_price is not None),
        labels_missing_entry_price=sum(1 for label in labels if label.entry_price is None),
        labels_with_forward_return=sum(1 for label in labels if label.forward_return is not None),
        sparse_or_better_labels=sum(1 for label in labels if label.label_quality in SPARSE_OR_BETTER),
        good_labels=sum(1 for label in labels if label.label_quality == "good"),
        no_price_labels=sum(1 for label in labels if label.label_quality == "no_price"),
        nearest_fallback_labels=sum(1 for label in labels if label.entry_price_source == "nearest_research_fallback"),
        entry_price_source_counts=dict(sorted(source_counts.items())),
        label_quality_counts=dict(sorted(quality_counts.items())),
        metadata_json=_dataset_counts(dataset_path),
    )


def compare_entry_price_coverage(
    clean_outcomes_path: Path | str,
    fallback_outcomes_path: Path | str,
    clean_dataset_path: Path | str | None = None,
    fallback_dataset_path: Path | str | None = None,
) -> EntryPriceCoverageComparison:
    clean = summarize_outcomes(clean_outcomes_path, clean_dataset_path, name="clean")
    fallback = summarize_outcomes(fallback_outcomes_path, fallback_dataset_path, name="fallback")
    report = EntryPriceCoverageComparison(
        report_id=make_entry_price_coverage_report_id(),
        created_at=datetime.now(timezone.utc).isoformat(),
        clean_summary=clean,
        fallback_summary=fallback,
        entry_price_gain=fallback.labels_with_entry_price - clean.labels_with_entry_price,
        forward_return_gain=fallback.labels_with_forward_return - clean.labels_with_forward_return,
        sparse_or_better_gain=fallback.sparse_or_better_labels - clean.sparse_or_better_labels,
        no_price_reduction=clean.no_price_labels - fallback.no_price_labels,
        warnings=["nearest_research_fallback_diagnostic_only"],
    )
    report.recommended_next_actions = _recommend(report)
    return report


def write_entry_price_comparison_markdown(
    report: EntryPriceCoverageComparison,
    output_path: Path | str,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = report.clean_summary
    fallback = report.fallback_summary
    lines = [
        "# Entry Price Coverage Comparison",
        "",
        f"- created_at: `{report.created_at}`",
        f"- report_id: `{report.report_id}`",
        "",
        "## Summary",
        "",
        f"- clean labels with entry price: `{clean.labels_with_entry_price}`",
        f"- fallback labels with entry price: `{fallback.labels_with_entry_price}`",
        f"- entry price gain: `{report.entry_price_gain}`",
        f"- forward return gain: `{report.forward_return_gain}`",
        f"- sparse-or-better gain: `{report.sparse_or_better_gain}`",
        f"- no_price reduction: `{report.no_price_reduction}`",
        f"- nearest fallback labels: `{fallback.nearest_fallback_labels}`",
        "",
        "## Entry Price Sources",
        "",
        f"- clean: `{clean.entry_price_source_counts}`",
        f"- fallback: `{fallback.entry_price_source_counts}`",
        "",
        "## Label Quality",
        "",
        f"- clean: `{clean.label_quality_counts}`",
        f"- fallback: `{fallback.label_quality_counts}`",
        "",
        "## Recommended Next Actions",
        "",
        *[f"- {action}" for action in report.recommended_next_actions],
        "",
        "Nearest research fallback is diagnostic-only and is not a trading signal.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_entry_price_comparison_json(
    report: EntryPriceCoverageComparison,
    output_path: Path | str,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(report), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _dataset_counts(dataset_path: Path | str | None) -> dict:
    if not dataset_path:
        return {}
    rows = ResearchDatasetStore(dataset_path).load_all()
    return {
        "dataset_row_count": len(rows),
        "dataset_rows_with_forward_return": sum(1 for row in rows if row.forward_return is not None),
        "dataset_nearest_fallback_rows": sum(1 for row in rows if row.entry_price_source == "nearest_research_fallback"),
    }


def _recommend(report: EntryPriceCoverageComparison) -> list[str]:
    if report.entry_price_gain > 0 or report.forward_return_gain > 0:
        return ["rerun baseline/rule/walk-forward on diagnostic dataset before more Helius"]
    return ["fallback did not materially improve coverage; consider larger bounded backfill"]
