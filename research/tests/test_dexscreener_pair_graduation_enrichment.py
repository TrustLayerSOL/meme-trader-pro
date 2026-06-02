import json
from pathlib import Path

from research.mtp_research.validation.dexscreener_pair_graduation_enrichment import (
    READINESS_DRY_RUN,
    READINESS_READY,
    run_dexscreener_pair_graduation_enrichment,
)


WSOL = "So11111111111111111111111111111111111111112"


class FakeDexScreenerIngestor:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def fetch_tokens(self, mints):
        self.calls.append(list(mints))
        rows = []
        for mint in mints:
            rows.extend(self.responses.get(mint, []))
        return rows


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _candidate(index: int, *, launch_ts: int = 1_700_000_000) -> dict:
    return {
        "launch_id": f"launch-{index}",
        "token_mint": f"mint-{index}",
        "launch_ts": launch_ts,
        "metadata_json": {"creator_deployer": "creator-a"},
    }


def _pair(mint: str, *, pair_created_at: int = 1_700_000_100_000, dex_id: str = "pumpswap") -> dict:
    return {
        "chainId": "solana",
        "dexId": dex_id,
        "pairAddress": f"pair-{mint}",
        "pairCreatedAt": pair_created_at,
        "url": f"https://dexscreener.com/solana/pair-{mint}",
        "baseToken": {"address": mint, "symbol": "MEME"},
        "quoteToken": {"address": WSOL, "symbol": "SOL"},
        "liquidity": {"usd": 25_000},
        "fdv": 50_000,
    }


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "jsonl_path": tmp_path / "labels.jsonl",
        "parquet_path": tmp_path / "labels.parquet",
        "report_dir": tmp_path / "reports",
    }


def test_dry_run_makes_no_api_calls(tmp_path: Path) -> None:
    candidates_path = _write_jsonl(tmp_path / "candidates.jsonl", [_candidate(1)])
    fake = FakeDexScreenerIngestor({"mint-1": [_pair("mint-1")]})

    report = run_dexscreener_pair_graduation_enrichment(
        candidates_path=candidates_path,
        execute=False,
        output_paths=_paths(tmp_path),
        ingestor=fake,
    )

    assert fake.calls == []
    assert report["readiness_classification"] == READINESS_DRY_RUN
    assert report["requests"]["projected_requests"] == 1


def test_execute_writes_pair_graduation_labels(tmp_path: Path) -> None:
    candidates_path = _write_jsonl(tmp_path / "candidates.jsonl", [_candidate(1), _candidate(2)])
    paths = _paths(tmp_path)
    fake = FakeDexScreenerIngestor({"mint-1": [_pair("mint-1", dex_id="raydium")]})

    report = run_dexscreener_pair_graduation_enrichment(
        candidates_path=candidates_path,
        execute=True,
        batch_size=2,
        output_paths=paths,
        ingestor=fake,
    )

    rows = [json.loads(line) for line in paths["jsonl_path"].read_text(encoding="utf-8").splitlines()]
    assert fake.calls == [["mint-1", "mint-2"]]
    assert report["readiness_classification"] == READINESS_READY
    assert report["requests"]["requests_used"] == 1
    assert report["collection"]["dex_pair_detected_count"] == 1
    assert rows[0]["dex_pair_detected"] is True
    assert rows[0]["migrated_to_raydium"] is True
    assert rows[0]["migration_time"] is not None
    assert rows[1]["migration_missing_reason"] == "no_dexscreener_pair_detected"
    assert paths["parquet_path"].exists()
    assert (paths["report_dir"] / "dexscreener_pair_graduation_enrichment.json").exists()


def test_request_ceiling_blocks_before_api_calls(tmp_path: Path) -> None:
    candidates_path = _write_jsonl(tmp_path / "candidates.jsonl", [_candidate(1), _candidate(2), _candidate(3)])
    fake = FakeDexScreenerIngestor({})

    report = run_dexscreener_pair_graduation_enrichment(
        candidates_path=candidates_path,
        execute=True,
        batch_size=1,
        request_ceiling=2,
        output_paths=_paths(tmp_path),
        ingestor=fake,
    )

    assert fake.calls == []
    assert report["readiness_classification"] == "dexscreener_pair_labels_blocked"
    assert report["requests"]["stopped_due_ceiling"] is True
