import json

from research.mtp_research.ingestion.pumpfun_creation_census import (
    build_creation_census_from_scan_report,
    load_census_rows,
    write_creation_census,
)


def test_census_preserves_accepted_create_event_fields(tmp_path) -> None:
    report = {
        "verified_create_candidates": [
            {
                "signature": "sig-valid",
                "slot": 123,
                "block_time": 1_780_000_000,
                "token_mint": "mint-valid",
                "creator_wallet": "creator-valid",
                "bonding_curve": "bonding-valid",
                "associated_bonding_curve": "assoc-valid",
                "instruction_index": 2,
                "instruction_discriminator": "create-disc",
                "extraction_confidence": "high",
                "metadata_json": {"instruction_type": "create"},
                "warning_flags": [],
            }
        ]
    }

    rows = build_creation_census_from_scan_report(report)
    output = write_creation_census(rows, tmp_path / "census.jsonl")
    loaded = load_census_rows(output)

    assert len(loaded) == 1
    row = loaded[0]
    assert row.accepted is True
    assert row.mint == "mint-valid"
    assert row.creator_deployer == "creator-valid"
    assert row.creation_signature == "sig-valid"
    assert row.slot == 123
    assert row.block_time == 1_780_000_000
    assert row.parser_confidence == "high"
    assert row.instruction_type == "create"
    assert row.source_method == "pumpfun_create_scanner_verified"
    assert row.rejection_reason is None


def test_census_keeps_rejected_and_unknown_rows_with_reasons() -> None:
    report = {
        "rejected_create_like_candidates": [
            {
                "signature": "sig-rejected",
                "instruction_index": 1,
                "instruction_discriminator": "bad-disc",
                "instruction_classification": "rejected_create_like",
                "rejection_reasons": ["invalid_token_mint", "creator_wallet_not_signer_or_fee_payer"],
            }
        ],
        "unknown_pumpfun_instructions": [
            {
                "signature": "sig-unknown",
                "instruction_index": 0,
                "instruction_discriminator": "unknown-disc",
                "instruction_classification": "unknown_pumpfun_instruction",
                "rejection_reasons": ["unknown_discriminator"],
            }
        ],
    }

    rows = build_creation_census_from_scan_report(report)

    assert [row.accepted for row in rows] == [False, False]
    assert rows[0].source_method == "pumpfun_create_scanner_rejected"
    assert rows[0].rejection_reason == "invalid_token_mint;creator_wallet_not_signer_or_fee_payer"
    assert rows[1].source_method == "pumpfun_create_scanner_unknown"
    assert rows[1].rejection_reason == "unknown_discriminator"


def test_census_jsonl_uses_required_table_columns(tmp_path) -> None:
    rows = build_creation_census_from_scan_report(
        {
            "verified_create_candidates": [
                {
                    "signature": "sig-valid",
                    "slot": 123,
                    "block_time": 1_780_000_000,
                    "token_mint": "mint-valid",
                    "creator_wallet": "creator-valid",
                    "extraction_confidence": "medium",
                    "metadata_json": {"instruction_type": "create"},
                }
            ]
        }
    )

    output = write_creation_census(rows, tmp_path / "census.jsonl")
    payload = json.loads(output.read_text(encoding="utf-8").strip())

    for field in [
        "mint",
        "creator_deployer",
        "creation_signature",
        "slot",
        "block_time",
        "parser_confidence",
        "instruction_type",
        "source_method",
        "rejection_reason",
    ]:
        assert field in payload
