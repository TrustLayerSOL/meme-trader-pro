import json

from research.mtp_research.ingestion.pumpfun_creation_census import PumpFunCreationCensusRow, write_creation_census
from research.mtp_research.validation.pumpfun_precision_audit import (
    deterministic_precision_sample,
    load_precision_reviews,
    precision_summary,
    write_precision_review_template,
)


def _row(signature: str, block_time: int | None = None) -> PumpFunCreationCensusRow:
    return PumpFunCreationCensusRow(
        mint=f"mint-{signature}",
        creator_deployer=f"creator-{signature}",
        creation_signature=signature,
        slot=1,
        block_time=block_time,
        parser_confidence="medium",
        instruction_type="create",
        source_method="pumpfun_create_scanner_verified",
        accepted=True,
    )


def test_precision_sample_is_deterministic() -> None:
    rows = [_row("sig-c", 30), _row("sig-a", 10), _row("sig-b", 20)]

    sample = deterministic_precision_sample(rows, 2)

    assert [row.creation_signature for row in sample] == ["sig-a", "sig-b"]


def test_precision_review_template_defaults_to_uncertain(tmp_path) -> None:
    output = write_precision_review_template([_row("sig-a", 10)], tmp_path / "review.jsonl")

    reviews = load_precision_reviews(output)

    assert len(reviews) == 1
    assert reviews[0].creation_signature == "sig-a"
    assert reviews[0].review_label == "uncertain"


def test_precision_summary_blocks_scaling_without_reviewed_valid_sample(tmp_path) -> None:
    census_path = write_creation_census([_row("sig-a", 10), _row("sig-b", 20)], tmp_path / "census.jsonl")
    review_path = tmp_path / "reviews.jsonl"
    review_path.write_text(
        "\n".join(
            [
                json.dumps({"creation_signature": "sig-a", "review_label": "reviewed_valid"}),
                json.dumps({"creation_signature": "sig-b", "review_label": "reviewed_invalid"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    summary = precision_summary(census_path, review_path)

    assert summary["review_label_counts"] == {"reviewed_invalid": 1, "reviewed_valid": 1}
    assert summary["reviewed_precision"] == 0.5
    assert summary["acceptable_for_scaling"] is False
    assert "parser_precision_not_acceptable_for_scaling" in summary["warning_flags"]
