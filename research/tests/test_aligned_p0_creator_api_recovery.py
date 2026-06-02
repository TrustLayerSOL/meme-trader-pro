import json
from pathlib import Path

from research.mtp_research.validation.aligned_p0_creator_api_recovery import (
    READINESS_BLOCKED,
    READINESS_GO,
    READINESS_PARTIAL,
    run_aligned_p0_creator_api_recovery,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True))
            handle.write("\n")
    return path


class FakeClient:
    def __init__(self, responses: dict[str, list[dict]]):
        self.responses = responses
        self.calls: list[dict] = []

    def fetch_transactions_for_address_window(self, address: str, **kwargs) -> dict:
        self.calls.append({"address": address, **kwargs})
        return {"transactions": list(self.responses.get(address, [])), "pagination_token": None}


def _create_tx(*, mint: str, creator: str, signature: str = "sig-create") -> dict:
    return {
        "signature": signature,
        "slot": 123,
        "blockTime": 1_700_000_001,
        "transaction": {
            "signatures": [signature],
            "message": {
                "accountKeys": [
                    {"pubkey": mint, "signer": False},
                    {"pubkey": "program-authority", "signer": False},
                    {"pubkey": "bonding-curve", "signer": False},
                    {"pubkey": "associated-bonding-curve", "signer": False},
                    {"pubkey": "global", "signer": False},
                    {"pubkey": creator, "signer": True},
                    {"pubkey": "payer", "signer": False},
                    {"pubkey": "system", "signer": False},
                    {"pubkey": "token-program", "signer": False},
                    {"pubkey": "metadata", "signer": False},
                    {"pubkey": "event-authority", "signer": False},
                    {"pubkey": "pumpfun-program", "signer": False},
                    {"pubkey": "extra-1", "signer": False},
                    {"pubkey": "extra-2", "signer": False},
                    {"pubkey": "extra-3", "signer": False},
                    {"pubkey": "extra-4", "signer": False},
                ],
                "instructions": [
                    {
                        "programId": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
                        "accounts": [
                            mint,
                            "program-authority",
                            "bonding-curve",
                            "associated-bonding-curve",
                            "global",
                            creator,
                            "payer",
                            "system",
                            "token-program",
                            "metadata",
                            "event-authority",
                            "pumpfun-program",
                            "extra-1",
                            "extra-2",
                            "extra-3",
                            "extra-4",
                        ],
                        "data": "d6904cec5f8b31b4",
                    }
                ],
            },
        },
    }


def test_dry_run_plans_unknown_creators_without_api_calls(tmp_path: Path) -> None:
    structural = _write_jsonl(
        tmp_path / "structural.jsonl",
        [
            {"launch_id": "launch-a", "mint": "mint-a", "creator": "", "launch_ts": 1000},
            {"launch_id": "launch-b", "mint": "mint-b", "creator": "creator-b", "launch_ts": 2000},
        ],
    )
    client = FakeClient({"mint-a": []})

    report = run_aligned_p0_creator_api_recovery(
        structural_features_path=structural,
        output_root=tmp_path / "lake",
        execute=False,
        client=client,
    )

    assert client.calls == []
    assert report["executed"] is False
    assert report["selected_unknown_mints"] == 1
    assert report["network_calls_made"] == 0
    assert report["readiness_classification"] == READINESS_PARTIAL
    assert "dry_run_only_no_api_calls_made" in report["warnings"]


def test_execute_recovers_creator_from_verified_pumpfun_create(tmp_path: Path) -> None:
    structural = _write_jsonl(
        tmp_path / "structural.jsonl",
        [{"launch_id": "launch-a", "mint": "mint-a", "creator": "", "launch_ts": 1_700_000_000}],
    )
    client = FakeClient({"mint-a": [_create_tx(mint="mint-a", creator="creator-a")]})

    report = run_aligned_p0_creator_api_recovery(
        structural_features_path=structural,
        output_root=tmp_path / "lake",
        execute=True,
        client=client,
        request_ceiling=10,
    )

    assert len(client.calls) == 1
    assert report["network_calls_made"] == 1
    assert report["recovered_creator_count"] == 1
    assert report["readiness_classification"] == READINESS_GO
    rows = [json.loads(line) for line in Path(report["outputs"]["jsonl_path"]).read_text(encoding="utf-8").splitlines()]
    assert rows[0]["mint"] == "mint-a"
    assert rows[0]["creator_deployer"] == "creator-a"
    assert rows[0]["creator_recovery_confidence"] == "high"
    assert Path(report["outputs"]["raw_jsonl_path"]).exists()


def test_unknown_layout_fails_closed(tmp_path: Path) -> None:
    structural = _write_jsonl(
        tmp_path / "structural.jsonl",
        [{"launch_id": "launch-a", "mint": "mint-a", "creator": "", "launch_ts": 1_700_000_000}],
    )
    tx = _create_tx(mint="mint-a", creator="creator-a")
    tx["transaction"]["message"]["instructions"][0]["data"] = "ffffffffffffffff"
    client = FakeClient({"mint-a": [tx]})

    report = run_aligned_p0_creator_api_recovery(
        structural_features_path=structural,
        output_root=tmp_path / "lake",
        execute=True,
        client=client,
        request_ceiling=10,
    )

    assert report["recovered_creator_count"] == 0
    assert report["unknown_or_missing_count"] == 1
    assert "no_verified_create_instruction_found" in report["missing_reason_counts"]
    assert report["readiness_classification"] == READINESS_PARTIAL


def test_request_ceiling_blocks_execute_before_fetch(tmp_path: Path) -> None:
    structural = _write_jsonl(
        tmp_path / "structural.jsonl",
        [
            {"launch_id": "launch-a", "mint": "mint-a", "creator": "", "launch_ts": 1000},
            {"launch_id": "launch-b", "mint": "mint-b", "creator": "", "launch_ts": 2000},
        ],
    )
    client = FakeClient({})

    report = run_aligned_p0_creator_api_recovery(
        structural_features_path=structural,
        output_root=tmp_path / "lake",
        execute=True,
        client=client,
        request_ceiling=0,
    )

    assert client.calls == []
    assert report["network_calls_made"] == 0
    assert report["readiness_classification"] == READINESS_BLOCKED
    assert "request_ceiling_too_low_for_selected_mints" in report["warnings"]
