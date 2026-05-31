"""Report writers for rule failure anatomy reviews."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from research.mtp_research.validation.rule_failure_models import RuleFailureReview


WARNING_TEXT = "This is diagnostic failure analysis only. It is not a trading signal."


def review_to_dict(review: RuleFailureReview) -> dict[str, Any]:
    return asdict(review)


def write_review_json(review: RuleFailureReview, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(review_to_dict(review), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_review_markdown(review: RuleFailureReview, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Rule Failure Anatomy Review",
        "",
        f"> Warning: {WARNING_TEXT}",
        "",
        "## Dataset Summary",
        "",
        f"- Row count: `{review.row_count}`",
        f"- Token count: `{review.token_count}`",
        f"- Time span seconds: `{review.time_span_seconds}`",
        f"- Nearest fallback row count: `{review.nearest_fallback_row_count}`",
        "",
        "## Decision",
        "",
        f"- Recommended next action: `{review.recommended_next_action}`",
        f"- Evidence scale recommendation: `{review.evidence_scale_recommendation}`",
        f"- Rule review recommendation: `{review.rule_review_recommendation}`",
        "",
        "## Rule Anatomy",
        "",
        "| Rule | Valid Folds | Positive Fold Rate | Selected | Avg Net | Token Concentration | Fallback Rate | Likely Causes |",
        "| --- | ---: | ---: | ---: | ---: | --- | ---: | --- |",
    ]
    for anatomy in review.rule_anatomies:
        lines.append(
            "| "
            f"`{anatomy.rule_id}` | "
            f"{anatomy.valid_test_fold_count} | "
            f"{_fmt(anatomy.positive_test_fold_rate)} | "
            f"{anatomy.total_test_selected_count} | "
            f"{_fmt(anatomy.avg_test_net_return)} | "
            f"`{anatomy.token_concentration}` | "
            f"{_fmt(anatomy.fallback_entry_rate)} | "
            f"`{anatomy.likely_failure_causes}` |"
        )
    lines.extend(["", "## Fold Detail", ""])
    for anatomy in review.rule_anatomies:
        lines.extend([f"### `{anatomy.rule_id}`", ""])
        if not anatomy.fold_anatomies:
            lines.append("- No fold details available.")
        for fold in anatomy.fold_anatomies:
            lines.append(
                "- "
                f"fold `{fold.fold_index}` selected `{fold.test_selected_count}`, "
                f"avg net `{_fmt(fold.test_avg_net_return)}`, "
                f"fallback rate `{_fmt(fold.fallback_entry_rate)}`, "
                f"tokens `{fold.token_counts}`, "
                f"warnings `{fold.warning_flags}`"
            )
        lines.append("")

    buy = next((item for item in review.rule_anatomies if item.rule_id == "buy_imbalance_basic"), None)
    lines.extend(["## buy_imbalance_basic", ""])
    if buy is None:
        lines.append("`buy_imbalance_basic` was not present in this review.")
    else:
        durable = (
            "not yet durable because positive fold rate remains below diagnostic review thresholds"
            if (buy.positive_test_fold_rate or 0.0) < 0.5
            else "requires clean-label retest and larger samples before any trust claim"
        )
        lines.extend(
            [
                f"- Selected count: `{buy.total_test_selected_count}`",
                f"- Valid fold count: `{buy.valid_test_fold_count}`",
                f"- Positive fold rate: `{_fmt(buy.positive_test_fold_rate)}`",
                f"- Why it is not yet durable: {durable}.",
                "- Evidence needed next: more real candidates, longer per-pool time span, and clean-label retest before changing thresholds.",
            ]
        )
    lines.extend(
        [
            "",
            "## Metadata",
            "",
            f"- Review ID: `{review.review_id}`",
            f"- Dataset path: `{review.dataset_path}`",
            f"- Walk-forward path: `{review.walk_forward_path}`",
            f"- Warning flags: `{review.warning_flags}`",
            f"- JSON path: `{path.with_suffix('.json')}`",
            f"- Markdown path: `{path}`",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _fmt(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}"
