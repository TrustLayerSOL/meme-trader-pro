import json
from pathlib import Path

from research.mtp_research.validation.p0_creator_funder_transfer_graph_collection import (
    READINESS_READY,
    load_creator_funder_checkpoint,
    run_creator_funder_transfer_graph_collection,
    write_creator_funder_checkpoint,
)


class FakeGraphClient:
    def __init__(self, transactions_by_address: dict[str, list[dict]]):
        self.transactions_by_address = transactions_by_address
        self.calls: list[dict] = []

    def fetch_transactions_for_address_window(self, address: str, **kwargs) -> dict:
        self.calls.append({"address": address, **kwargs})
        return {"transactions": list(self.transactions_by_address.get(address, [])), "pagination_token": None}


def _write_csv(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = list(rows[0])
    lines = [",".join(headers)]
    for row in rows:
        lines.append(",".join(str(row.get(key, "")) for key in headers))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True))
            handle.write("\n")
    return path


def _target_rows() -> list[dict]:
    return [
        {
            "candidate_funder": "funder-shared",
            "common_funder_candidate_id": "funder-funder-shared",
            "creator": "creator-a",
            "funding_signature": "sig-fund-a",
            "launch_id": "launch-a",
            "milestone_tier": "reached_100k_but_never_200k",
            "mint": "mint-a",
            "reason_selected": "test",
        },
        {
            "candidate_funder": "funder-shared",
            "common_funder_candidate_id": "funder-funder-shared",
            "creator": "creator-b",
            "funding_signature": "sig-fund-b",
            "launch_id": "launch-b",
            "milestone_tier": "never_reached_20k",
            "mint": "mint-b",
            "reason_selected": "test",
        },
    ]


def _candidate_rows() -> list[dict]:
    return [
        {"launch_id": "launch-a", "token_mint": "mint-a", "launch_ts": 1000, "launch_time_utc": "1970-01-01T00:16:40+00:00"},
        {"launch_id": "launch-b", "token_mint": "mint-b", "launch_ts": 1100, "launch_time_utc": "1970-01-01T00:18:20+00:00"},
    ]


def _native_tx(signature: str, block_time: int, source: str, destination: str, lamports: int) -> dict:
    return {
        "signature": signature,
        "blockTime": block_time,
        "nativeTransfers": [
            {"fromUserAccount": source, "toUserAccount": destination, "amount": lamports}
        ],
    }


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "raw_dir": tmp_path / "raw",
        "jsonl_path": tmp_path / "creator_funder.jsonl",
        "parquet_path": tmp_path / "creator_funder.parquet",
        "checkpoint_path": tmp_path / "checkpoint.json",
        "report_dir": tmp_path / "reports",
    }


def test_dry_run_checks_scope_and_does_not_call_network(tmp_path: Path) -> None:
    fake = FakeGraphClient({"creator-a": [_native_tx("sig", 900, "funder-shared", "creator-a", 1)]})

    report = run_creator_funder_transfer_graph_collection(
        target_path=_write_csv(tmp_path / "targets.csv", _target_rows()),
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", _candidate_rows()),
        execute=False,
        client=fake,
        output_paths=_paths(tmp_path),
    )

    assert fake.calls == []
    assert report["execution"]["mode"] == "dry_run"
    assert report["scope"]["creators_selected"] == 2
    assert report["scope"]["candidate_funders_selected"] == 1
    assert report["requests"]["requests_used"] == 0
    assert report["guardrails"]["trading_logic_added"] is False


def test_execute_parses_candidate_funders_and_relation_proxies(tmp_path: Path, monkeypatch) -> None:
    early_buyers = [{"current_launch_id": "launch-a", "wallet": "buyer-a"}]
    top_holders = [{"launch_id": "launch-a", "top_holder_owner": "top-a"}]
    fake = FakeGraphClient(
        {
            "creator-a": [
                _native_tx("sig-fund-a", 900, "funder-shared", "creator-a", 2_000_000_000),
                _native_tx("sig-buyer", 920, "creator-a", "buyer-a", 100),
                _native_tx("sig-top", 930, "creator-a", "top-a", 100),
            ],
            "creator-b": [_native_tx("sig-fund-b", 1000, "funder-shared", "creator-b", 1_000_000_000)],
            "funder-shared": [_native_tx("sig-funder-out", 890, "funder-shared", "creator-a", 2_000_000_000)],
        }
    )
    monkeypatch.setattr(
        "research.mtp_research.validation.p0_creator_funder_transfer_graph_collection._write_parquet",
        lambda rows, path: Path(path).write_text("stub", encoding="utf-8"),
    )

    report = run_creator_funder_transfer_graph_collection(
        target_path=_write_csv(tmp_path / "targets.csv", _target_rows()),
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", _candidate_rows()),
        early_buyer_path=_write_jsonl(tmp_path / "early_buyers.jsonl", early_buyers),
        top_holder_path=_write_jsonl(tmp_path / "top_holders.jsonl", top_holders),
        execute=True,
        request_ceiling=20,
        credit_cap=25_000,
        output_paths=_paths(tmp_path),
        client=fake,
    )

    rows = [json.loads(line) for line in _paths(tmp_path)["jsonl_path"].read_text(encoding="utf-8").splitlines()]
    by_launch = {row["launch_id"]: row for row in rows}
    assert report["readiness_classification"] == READINESS_READY
    assert by_launch["launch-a"]["candidate_funder"] == "funder-shared"
    assert by_launch["launch-a"]["funding_amount_sol"] == 2.0
    assert by_launch["launch-a"]["shared_funding_proxy"] is True
    assert by_launch["launch-a"]["time_linked_funding_proxy"] is True
    assert by_launch["launch-a"]["creator_to_early_buyer_transfer_link_proxy"] is True
    assert by_launch["launch-a"]["creator_to_top_holder_transfer_link_proxy"] is True
    assert by_launch["launch-a"]["creator_wallet_relation_proxy_count"] >= 2
    assert report["raw"]["raw_responses_preserved"] == 5
    assert report["quality"]["candidate_funder_coverage"]["covered_launches"] == 2


def test_budget_cap_checkpoint_and_missing_reason_handling(tmp_path: Path, monkeypatch) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    write_creator_funder_checkpoint(checkpoint, {"completed_addresses": ["creator-a"], "requests_used": 1})
    assert load_creator_funder_checkpoint(checkpoint)["completed_addresses"] == ["creator-a"]

    paths = _paths(tmp_path)
    paths["checkpoint_path"] = checkpoint
    fake = FakeGraphClient({"creator-b": []})
    monkeypatch.setattr(
        "research.mtp_research.validation.p0_creator_funder_transfer_graph_collection._write_parquet",
        lambda rows, path: Path(path).write_text("stub", encoding="utf-8"),
    )

    blocked = run_creator_funder_transfer_graph_collection(
        target_path=_write_csv(tmp_path / "targets.csv", _target_rows()),
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", _candidate_rows()),
        execute=True,
        credit_cap=1,
        output_paths=paths,
        client=fake,
    )
    assert blocked["readiness_classification"] == "creator_funder_graph_blocked"
    assert "projected_credit_cap_exceeded" in blocked["warnings"]

    report = run_creator_funder_transfer_graph_collection(
        target_path=_write_csv(tmp_path / "targets.csv", _target_rows()),
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", _candidate_rows()),
        execute=True,
        request_ceiling=20,
        credit_cap=25_000,
        output_paths=paths,
        client=fake,
    )
    assert [call["address"] for call in fake.calls] == ["creator-b", "funder-shared"]
    assert report["quality"]["missing_reason_counts"]["no_prelaunch_transfer_found"] >= 1


def test_report_uses_neutral_labels_only(tmp_path: Path) -> None:
    report = run_creator_funder_transfer_graph_collection(
        target_path=_write_csv(tmp_path / "targets.csv", _target_rows()),
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", _candidate_rows()),
        execute=False,
        output_paths=_paths(tmp_path),
    )

    text = json.dumps(report).lower()
    assert "creator_link_proxy" in text
    assert "insider" not in text
    assert "scammer" not in text
    assert "wash trader" not in text
    assert "manipulator" not in text
