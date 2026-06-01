"""Manual precision-audit helpers for Pump.fun creation census rows."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from research.mtp_research.ingestion.pumpfun_creation_census import PumpFunCreationCensusRow, load_census_rows


VALID_REVIEW_LABELS = {"reviewed_valid", "reviewed_invalid", "uncertain"}


@dataclass
class PumpFunPrecisionReview:
    creation_signature: str
    review_label: str
    reviewer_notes: str = ""
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def deterministic_precision_sample(
    rows: list[PumpFunCreationCensusRow],
    sample_size: int,
) -> list[PumpFunCreationCensusRow]:
    ordered = sorted(rows, key=lambda row: (row.block_time or 0, row.creation_signature, row.instruction_index or -1))
    return ordered[:sample_size]


def write_precision_review_template(
    rows: list[PumpFunCreationCensusRow],
    output_path: Path | str,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for row in rows:
            review = PumpFunPrecisionReview(
                creation_signature=row.creation_signature,
                review_label="uncertain",
                metadata_json={
                    "mint": row.mint,
                    "creator_deployer": row.creator_deployer,
                    "parser_confidence": row.parser_confidence,
                    "rejection_reason": row.rejection_reason,
                },
            )
            f.write(json.dumps(review.to_dict(), sort_keys=True))
            f.write("\n")
    return output_path


def load_precision_reviews(path: Path | str) -> list[PumpFunPrecisionReview]:
    path = Path(path)
    if not path.exists():
        return []
    reviews = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            label = payload.get("review_label", "uncertain")
            if label not in VALID_REVIEW_LABELS:
                label = "uncertain"
            reviews.append(
                PumpFunPrecisionReview(
                    creation_signature=payload["creation_signature"],
                    review_label=label,
                    reviewer_notes=payload.get("reviewer_notes", ""),
                    metadata_json=dict(payload.get("metadata_json", {})),
                )
            )
    return reviews


def precision_summary(census_path: Path | str, review_path: Path | str) -> dict[str, Any]:
    rows = load_census_rows(census_path)
    reviews = load_precision_reviews(review_path)
    label_counts = Counter(review.review_label for review in reviews)
    reviewed = label_counts["reviewed_valid"] + label_counts["reviewed_invalid"]
    precision = None
    if reviewed:
        precision = label_counts["reviewed_valid"] / reviewed
    return {
        "census_rows": len(rows),
        "review_rows": len(reviews),
        "review_label_counts": dict(sorted(label_counts.items())),
        "reviewed_precision": precision,
        "acceptable_for_scaling": bool(precision is not None and precision >= 0.95 and reviewed >= 20),
        "warning_flags": _warning_flags(rows, reviews, precision, reviewed),
    }


def write_precision_summary(summary: dict[str, Any], output_path: Path | str) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def write_precision_summary_markdown(summary: dict[str, Any], output_path: Path | str) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Pump.fun Precision Audit Summary",
        "",
        "This is a parser-quality report only. It does not authorize broad scaling, backtests, thesis promotion, paper trading, or live trading.",
        "",
        f"- Census rows: `{summary['census_rows']}`",
        f"- Review rows: `{summary['review_rows']}`",
        f"- Review label counts: `{summary['review_label_counts']}`",
        f"- Reviewed precision: `{summary['reviewed_precision']}`",
        f"- Acceptable for scaling: `{summary['acceptable_for_scaling']}`",
        f"- Warning flags: `{summary['warning_flags']}`",
    ]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def _warning_flags(
    rows: list[PumpFunCreationCensusRow],
    reviews: list[PumpFunPrecisionReview],
    precision: float | None,
    reviewed: int,
) -> list[str]:
    warnings = []
    if not rows:
        warnings.append("empty_census")
    if not reviews:
        warnings.append("no_manual_reviews")
    if reviewed < 20:
        warnings.append("insufficient_reviewed_sample")
    if precision is None or precision < 0.95:
        warnings.append("parser_precision_not_acceptable_for_scaling")
    return warnings
