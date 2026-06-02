import json
from pathlib import Path

from research.mtp_research.validation.migration_positive_control_probe import (
    CLASSIFICATION_READY,
    CLASSIFICATION_STRATEGY_FOUND,
    build_migration_positive_control_probe,
    write_migration_positive_control_probe_outputs,
)


class FakeProbeClient:
    def __init__(self, signatures_by_address: dict[str, list[dict]], transactions: dict[str, dict]):
        self.signatures_by_address = signatures_by_address
        self.transactions = transactions
        self.signature_calls = 0
        self.transaction_calls = 0

    def fetch_signatures_for_address(self, request):
        self.signature_calls += 1
        rows = self.signatures_by_address.get(request.address, [])
        return _SignatureResult(
            records=[
                _SignatureRecord(signature=row["signature"], block_time=row.get("blockTime"), slot=row.get("slot"))
                for row in rows
            ],
            next_before=None,
        )

    def fetch_transaction(self, signature: str) -> dict:
        self.transaction_calls += 1
        return self.transactions.get(signature, {})


class _SignatureRecord:
    def __init__(self, *, signature: str, block_time: int | None, slot: int | None):
        self.signature = signature
        self.block_time = block_time
        self.slot = slot


class _SignatureResult:
    def __init__(self, *, records: list[_SignatureRecord], next_before: str | None):
        self.records = records
        self.next_before = next_before


def _write_candidates(path: Path) -> Path:
    row = {
        "launch_id": "launch-a",
        "token_mint": "mint-a",
        "launch_ts": 1_700_000_000,
        "launch_time_utc": "2026-05-25T10:00:00+00:00",
        "pool_address": "curve-a",
        "metadata_json": {
            "bonding_curve": "curve-a",
            "associated_bonding_curve": "assoc-a",
            "creator_deployer": "creator-a",
        },
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    return path


def _migrate_tx() -> dict:
    return {
        "blockTime": 1_700_000_120,
        "meta": {"logMessages": ["Program log: Instruction: MigrateV2"]},
        "transaction": {
            "message": {
                "accountKeys": [{"pubkey": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"}],
                "instructions": [{"programId": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"}],
            }
        },
    }


def test_dry_run_does_not_call_network(tmp_path: Path) -> None:
    client = FakeProbeClient(signatures_by_address={"curve-a": [{"signature": "known", "blockTime": 1_700_000_120}]}, transactions={})

    report = build_migration_positive_control_probe(
        candidates_path=_write_candidates(tmp_path / "candidates.jsonl"),
        known_mint="mint-a",
        known_signature="known",
        execute=False,
        client=client,
    )

    assert report["classification"] == CLASSIFICATION_READY
    assert report["network_calls_used"] == 0
    assert client.signature_calls == 0
    assert client.transaction_calls == 0


def test_execute_finds_positive_control_address_strategy(tmp_path: Path) -> None:
    client = FakeProbeClient(
        signatures_by_address={
            "mint-a": [{"signature": "other", "blockTime": 1_700_000_100}],
            "curve-a": [{"signature": "known", "blockTime": 1_700_000_120}],
        },
        transactions={"known": _migrate_tx()},
    )

    report = build_migration_positive_control_probe(
        candidates_path=_write_candidates(tmp_path / "candidates.jsonl"),
        known_mint="mint-a",
        known_signature="known",
        execute=True,
        request_ceiling=10,
        client=client,
    )

    assert report["classification"] == CLASSIFICATION_STRATEGY_FOUND
    assert report["positive_control"]["known_signature_found"] is True
    assert report["positive_control"]["best_strategy"] == "bonding_curve"
    assert report["positive_control"]["hydrated_exact_migration"] is True
    assert client.transaction_calls == 1


def test_outputs_are_written(tmp_path: Path) -> None:
    report = build_migration_positive_control_probe(
        candidates_path=_write_candidates(tmp_path / "candidates.jsonl"),
        known_mint="mint-a",
        known_signature="known",
        execute=False,
    )

    paths = write_migration_positive_control_probe_outputs(report, output_dir=tmp_path / "reports")

    assert paths["json_path"].exists()
    assert paths["markdown_path"].exists()
    assert "No thesis" in paths["markdown_path"].read_text(encoding="utf-8")
