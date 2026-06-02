import json
from pathlib import Path

import pytest

from research.mtp_research.validation.funding_link_feasibility import (
    READINESS_PARTIAL,
    build_funding_link_feasibility_report,
    write_funding_link_feasibility_outputs,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _candidate(mint: str, creator: str, signature: str) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "launch_ts": 1_700_000_000,
        "metadata_json": {
            "creator_deployer": creator,
            "creation_signature": signature,
            "bonding_curve": f"curve-{mint}",
            "associated_bonding_curve": f"assoc-{mint}",
        },
    }


def _raw_creation(signature: str, creator: str, mint: str, fee_payer: str | None = None) -> dict:
    payer = fee_payer or creator
    return {
        "signature": signature,
        "token_mint": mint,
        "block_time": 1_700_000_000,
        "raw_json": {
            "transaction": {
                "signatures": [signature, f"mint-signer-{mint}"],
                "message": {
                    "accountKeys": [
                        {"pubkey": payer, "signer": True, "writable": True},
                        {"pubkey": f"mint-signer-{mint}", "signer": True, "writable": True},
                        {"pubkey": creator, "signer": False, "writable": True},
                    ],
                    "instructions": [
                        {
                            "parsed": {
                                "type": "transfer",
                                "info": {
                                    "source": payer,
                                    "destination": f"curve-{mint}",
                                    "lamports": 2_000_000,
                                },
                            },
                            "program": "system",
                            "programId": "11111111111111111111111111111111",
                        }
                    ],
                },
            },
            "meta": {"err": None, "fee": 5000},
        },
    }


def test_funding_link_audit_extracts_fee_payer_signers_and_source_wallets(tmp_path: Path) -> None:
    candidates = [
        _candidate("mint-a", "creator-a", "sig-a"),
        _candidate("mint-b", "creator-b", "sig-b"),
    ]
    raw_rows = [
        _raw_creation("sig-a", "creator-a", "mint-a", fee_payer="shared-payer"),
        _raw_creation("sig-b", "creator-b", "mint-b", fee_payer="shared-payer"),
    ]

    report = build_funding_link_feasibility_report(
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", candidates),
        raw_transaction_paths=[_write_jsonl(tmp_path / "raw.jsonl", raw_rows)],
        max_launches=100,
    )

    assert report["scope"]["launches_inspected"] == 2
    assert report["field_coverage"]["fee_payer"]["coverage_pct"] == 100
    assert report["field_coverage"]["signer"]["coverage_pct"] == 100
    assert report["field_coverage"]["source_wallet"]["coverage_pct"] == 100
    assert report["field_coverage"]["creator_funding_source"]["classification"] == "unavailable"
    assert report["linkage_summary"]["shared_fee_payer_launches"] == 2
    assert report["offline_reconstruction"]["deterministic_reconstruction_possible"] is False
    assert report["offline_reconstruction"]["offline_only_possible"] is False
    assert report["offline_reconstruction"]["new_data_source_required"] is True
    assert report["readiness_classification"] == READINESS_PARTIAL


def test_funding_link_audit_fails_closed_when_creation_raw_is_missing(tmp_path: Path) -> None:
    report = build_funding_link_feasibility_report(
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", [_candidate("mint-a", "creator-a", "sig-a")]),
        raw_transaction_paths=[_write_jsonl(tmp_path / "raw.jsonl", [])],
        max_launches=100,
    )

    row = report["launch_rows"][0]
    assert row["field_status"]["transaction_metadata"] == "unavailable"
    assert row["field_status"]["fee_payer"] == "unavailable"
    assert row["field_status"]["signer"] == "unavailable"
    assert row["field_status"]["source_wallet"] == "unavailable"
    assert row["rejection_reason"] == "creation_transaction_raw_missing"
    assert report["readiness_classification"] == "funding_link_blocked"


def test_funding_link_audit_is_bounded_to_100_launches(tmp_path: Path) -> None:
    candidates = [_candidate(f"mint-{i}", f"creator-{i}", f"sig-{i}") for i in range(101)]

    with pytest.raises(ValueError, match="max_launches must be <= 100"):
        build_funding_link_feasibility_report(
            candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", candidates),
            raw_transaction_paths=[_write_jsonl(tmp_path / "raw.jsonl", [])],
            max_launches=101,
        )


def test_funding_link_outputs_use_requested_names(tmp_path: Path) -> None:
    report = build_funding_link_feasibility_report(
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", [_candidate("mint-a", "creator-a", "sig-a")]),
        raw_transaction_paths=[_write_jsonl(tmp_path / "raw.jsonl", [_raw_creation("sig-a", "creator-a", "mint-a")])],
    )

    paths = write_funding_link_feasibility_outputs(report, output_dir=tmp_path / "reports")

    assert paths["data_availability_markdown_path"].name == "funding_link_data_availability.md"
    assert paths["feasibility_json_path"].name == "funding_link_feasibility.json"
    assert paths["feasibility_markdown_path"].name == "funding_link_feasibility.md"
    assert paths["feasibility_json_path"].exists()
    assert "No thesis cycle was run." in paths["feasibility_markdown_path"].read_text(encoding="utf-8")
