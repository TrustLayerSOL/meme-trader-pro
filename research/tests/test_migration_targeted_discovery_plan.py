import json
from pathlib import Path

from research.mtp_research.validation.migration_targeted_discovery_plan import (
    CLASSIFICATION_READY,
    build_migration_targeted_discovery_plan,
    write_migration_targeted_discovery_plan_outputs,
)


def _write_raw(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _raw_row(signature: str, mint: str, logs: list[str]) -> dict:
    return {
        "signature": signature,
        "mint": mint,
        "creator": "creator-a",
        "launch_id": f"launch-{mint}",
        "block_time": 1_700_000_123,
        "raw_json": {
            "blockTime": 1_700_000_123,
            "meta": {"logMessages": logs},
            "transaction": {
                "message": {
                    "accountKeys": [
                        {"pubkey": "mint-account"},
                        {"pubkey": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"},
                    ],
                    "instructions": [
                        {
                            "programId": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
                            "accounts": ["mint-account", "curve-account", "creator-a"],
                            "data": "abcdef",
                        }
                    ],
                }
            },
        },
    }


def test_plan_counts_exact_migrate_and_excludes_fee_sharing_false_positive(tmp_path: Path) -> None:
    raw_path = _write_raw(
        tmp_path / "raw.jsonl",
        [
            _raw_row("sig-real", "mint-real", ["Program log: Instruction: MigrateV2"]),
            _raw_row("sig-fee", "mint-fee", ["Program log: Instruction: MigrateBondingCurveCreator"]),
        ],
    )

    plan = build_migration_targeted_discovery_plan(raw_transactions_path=raw_path)

    assert plan["classification"] == CLASSIFICATION_READY
    assert plan["evidence_summary"]["exact_migration_event_count"] == 1
    assert plan["evidence_summary"]["migration_like_false_positive_count"] == 1
    assert plan["known_migration_examples"][0]["signature"] == "sig-real"
    assert plan["known_false_positive_examples"][0]["signature"] == "sig-fee"
    assert plan["network_calls_used"] == 0


def test_plan_outputs_are_written(tmp_path: Path) -> None:
    raw_path = _write_raw(tmp_path / "raw.jsonl", [_raw_row("sig-real", "mint-real", ["Program log: Instruction: Migrate"])])
    plan = build_migration_targeted_discovery_plan(raw_transactions_path=raw_path)

    paths = write_migration_targeted_discovery_plan_outputs(plan, output_dir=tmp_path / "reports")

    assert paths["json_path"].exists()
    assert paths["markdown_path"].exists()
    loaded = json.loads(paths["json_path"].read_text(encoding="utf-8"))
    assert loaded["report_id"] == "migration_targeted_discovery_plan_v0"
    assert "No network calls were made." in paths["markdown_path"].read_text(encoding="utf-8")
