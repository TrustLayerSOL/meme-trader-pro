import json
from pathlib import Path

from research.mtp_research.validation.pre_launch_funding_collection import (
    READINESS_PARTIAL,
    READINESS_READY,
    load_funding_collection_checkpoint,
    run_pre_launch_funding_collection,
    write_funding_collection_checkpoint,
)


class FakeFundingClient:
    def __init__(self, transactions_by_creator: dict[str, list[dict]]):
        self.transactions_by_creator = transactions_by_creator
        self.calls = []

    def fetch_transactions_for_address_window(self, address: str, **kwargs) -> dict:
        self.calls.append({"address": address, **kwargs})
        return {"transactions": list(self.transactions_by_creator.get(address, [])), "pagination_token": None}


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _candidate(index: int, creator: str, launch_ts: int) -> dict:
    return {
        "launch_id": f"launch-{index}",
        "token_mint": f"mint-{index}",
        "launch_ts": launch_ts,
        "launch_time_utc": f"1970-01-01T00:{index:02d}:00+00:00",
        "metadata_json": {"creator_deployer": creator, "creation_signature": f"create-{index}"},
    }


def _native_tx(signature: str, block_time: int, funder: str, creator: str, lamports: int) -> dict:
    return {
        "signature": signature,
        "blockTime": block_time,
        "nativeTransfers": [
            {"fromUserAccount": funder, "toUserAccount": creator, "amount": lamports}
        ],
    }


def _token_tx(signature: str, block_time: int, funder: str, creator: str, amount: str) -> dict:
    return {
        "signature": signature,
        "blockTime": block_time,
        "tokenTransfers": [
            {"fromUserAccount": funder, "toUserAccount": creator, "tokenAmount": amount, "mint": "token-mint"}
        ],
    }


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "raw_path": tmp_path / "raw" / "funding_link_raw_transactions.jsonl",
        "jsonl_path": tmp_path / "funding_link_pilot.jsonl",
        "parquet_path": tmp_path / "funding_link_pilot.parquet",
        "checkpoint_path": tmp_path / "funding_link_checkpoint.json",
        "report_dir": tmp_path / "reports",
    }


def test_dry_run_uses_planner_and_does_not_call_network(tmp_path: Path) -> None:
    candidates = [_candidate(1, "creator-a", 1000)]
    fake = FakeFundingClient({"creator-a": [_native_tx("sig-1", 900, "funder-a", "creator-a", 1_000_000_000)]})

    result = run_pre_launch_funding_collection(
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", candidates),
        execute=False,
        max_creators=1,
        output_paths=_paths(tmp_path),
        client=fake,
    )

    assert fake.calls == []
    assert result["execution"]["mode"] == "dry_run"
    assert result["requests"]["requests_used"] == 0
    assert result["guardrails"]["thesis_runs"] == 0


def test_execute_parses_latest_prelaunch_funding_and_repeated_funder(tmp_path: Path, monkeypatch) -> None:
    candidates = [
        _candidate(1, "creator-a", 1000),
        _candidate(2, "creator-a", 1200),
        _candidate(3, "creator-b", 1100),
    ]
    fake = FakeFundingClient(
        {
            "creator-a": [
                _native_tx("sig-old", 800, "shared-funder", "creator-a", 1_000_000_000),
                _native_tx("sig-new", 950, "shared-funder", "creator-a", 2_000_000_000),
            ],
            "creator-b": [_token_tx("sig-token", 1000, "shared-funder", "creator-b", "42")],
        }
    )

    monkeypatch.setattr(
        "research.mtp_research.validation.pre_launch_funding_collection._write_parquet",
        lambda rows, path: Path(path).write_text("stub", encoding="utf-8"),
    )
    result = run_pre_launch_funding_collection(
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", candidates),
        execute=True,
        max_creators=2,
        lookback_hours=24,
        request_ceiling=200,
        hard_stop_projected_requests=200,
        max_total_transactions=10,
        output_paths=_paths(tmp_path),
        client=fake,
    )

    rows = [json.loads(line) for line in _paths(tmp_path)["jsonl_path"].read_text(encoding="utf-8").splitlines()]
    by_launch = {row["launch_id"]: row for row in rows}
    assert result["readiness_classification"] in {READINESS_READY, READINESS_PARTIAL}
    assert by_launch["launch-1"]["candidate_funding_wallet"] == "shared-funder"
    assert by_launch["launch-1"]["candidate_funding_signature"] == "sig-new"
    assert by_launch["launch-1"]["funding_amount_sol"] == 2.0
    assert by_launch["launch-3"]["funding_amount_token"] == "42"
    assert by_launch["launch-1"]["launches_sharing_funder"] == 3
    assert by_launch["launch-1"]["creator_has_prior_funding_trace"] is True
    assert result["funding"]["funding_source_coverage"]["covered_launches"] == 3
    assert result["funding"]["repeated_funder_coverage"]["launches_with_repeated_funder"] == 3
    assert result["raw"]["raw_transactions_preserved"] == 3


def test_checkpoint_roundtrip_and_resume_skips_completed_creator(tmp_path: Path, monkeypatch) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    write_funding_collection_checkpoint(checkpoint, {"completed_creators": ["creator-a"], "requests_used": 1})
    assert load_funding_collection_checkpoint(checkpoint)["completed_creators"] == ["creator-a"]

    candidates = [_candidate(1, "creator-a", 1000), _candidate(2, "creator-b", 1100)]
    fake = FakeFundingClient({"creator-b": [_native_tx("sig-b", 1000, "funder-b", "creator-b", 1)]})
    paths = _paths(tmp_path)
    paths["checkpoint_path"] = checkpoint
    monkeypatch.setattr(
        "research.mtp_research.validation.pre_launch_funding_collection._write_parquet",
        lambda rows, path: Path(path).write_text("stub", encoding="utf-8"),
    )

    result = run_pre_launch_funding_collection(
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", candidates),
        execute=True,
        max_creators=2,
        output_paths=paths,
        client=fake,
    )

    assert [call["address"] for call in fake.calls] == ["creator-b"]
    assert result["collection"]["creators_attempted"] == 2
    assert result["collection"]["creators_completed"] == 2
