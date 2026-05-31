import json
from pathlib import Path

from research.mtp_research.validation.entry_price_coverage_report import (
    compare_entry_price_coverage,
    summarize_outcomes,
    write_entry_price_comparison_json,
    write_entry_price_comparison_markdown,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _label(outcome_id: str, entry_price=None, forward_return=None, quality="no_price", source="missing", metadata=None):
    return {
        "outcome_id": outcome_id,
        "snapshot_id": f"snapshot-{outcome_id}",
        "token_mint": "token-a",
        "snapshot_ts": 100,
        "horizon_name": "5m",
        "horizon_seconds": 300,
        "entry_price": entry_price,
        "entry_price_source": source,
        "forward_return": forward_return,
        "label_quality": quality,
        "metadata_json": metadata or {},
    }


def test_summarize_outcomes_counts_nearest_fallback_labels(tmp_path: Path) -> None:
    outcomes = tmp_path / "outcomes.jsonl"
    _write_jsonl(
        outcomes,
        [
            _label("1", entry_price=1.0, forward_return=0.1, quality="sparse", source="nearest_research_fallback"),
            _label("2"),
        ],
    )

    summary = summarize_outcomes(outcomes)

    assert summary.total_labels == 2
    assert summary.labels_with_entry_price == 1
    assert summary.labels_with_forward_return == 1
    assert summary.nearest_fallback_labels == 1
    assert summary.entry_price_source_counts["nearest_research_fallback"] == 1


def test_compare_entry_price_coverage_calculates_gains_and_no_price_reduction(tmp_path: Path) -> None:
    clean = tmp_path / "clean.jsonl"
    fallback = tmp_path / "fallback.jsonl"
    _write_jsonl(clean, [_label("1"), _label("2", entry_price=1.0, forward_return=0.1, quality="sparse", source="last_before_snapshot")])
    _write_jsonl(
        fallback,
        [
            _label("1", entry_price=1.0, forward_return=0.2, quality="sparse", source="nearest_research_fallback"),
            _label("2", entry_price=1.0, forward_return=0.1, quality="sparse", source="last_before_snapshot"),
        ],
    )

    report = compare_entry_price_coverage(clean, fallback)

    assert report.entry_price_gain == 1
    assert report.forward_return_gain == 1
    assert report.sparse_or_better_gain == 1
    assert report.no_price_reduction == 1
    assert "nearest_research_fallback_diagnostic_only" in report.warnings


def test_entry_price_comparison_writers_create_markdown_and_json(tmp_path: Path) -> None:
    clean = tmp_path / "clean.jsonl"
    fallback = tmp_path / "fallback.jsonl"
    _write_jsonl(clean, [_label("1")])
    _write_jsonl(fallback, [_label("1", entry_price=1.0, source="nearest_research_fallback")])
    report = compare_entry_price_coverage(clean, fallback)

    md = write_entry_price_comparison_markdown(report, tmp_path / "report.md")
    js = write_entry_price_comparison_json(report, tmp_path / "report.json")

    assert "Entry Price Coverage Comparison" in md.read_text(encoding="utf-8")
    assert "diagnostic-only" in md.read_text(encoding="utf-8")
    assert json.loads(js.read_text(encoding="utf-8"))["entry_price_gain"] == 1
