import json
from pathlib import Path

import pytest

from research.mtp_research.validation.creator_archetype_history_thesis import (
    build_t003_creator_archetype_report,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _candidate(mint: str, launch_ts: int, creator: str) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "launch_ts": launch_ts,
        "block_time": launch_ts,
        "metadata_json": {"creator_deployer": creator},
    }


def _snapshot(mint: str, terminal_value: float) -> list[dict]:
    return [
        {
            "launch_id": f"launch-{mint}",
            "token_mint": mint,
            "launch_age_seconds": 30,
            "valuation_proxy_available": True,
            "valuation_proxy_usd": 1000,
        },
        {
            "launch_id": f"launch-{mint}",
            "token_mint": mint,
            "launch_age_seconds": 7200,
            "valuation_proxy_available": True,
            "valuation_proxy_usd": terminal_value,
        },
    ]


def _outcome(mint: str) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "price_available_120m": True,
        "has_liquidity_proxy_at_120m": True,
    }


def test_future_creator_launches_do_not_affect_prior_history(tmp_path: Path) -> None:
    candidates = [
        _candidate("early", 1_000, "creator-x"),
        _candidate("middle", 2_000, "creator-x"),
        _candidate("future", 3_000, "creator-x"),
    ]
    snapshots = []
    snapshots.extend(_snapshot("early", 1100))
    snapshots.extend(_snapshot("middle", 1300))
    snapshots.extend(_snapshot("future", 10_000))
    paths = {
        "candidates_path": _write_jsonl(tmp_path / "launches.jsonl", candidates),
        "snapshots_path": _write_jsonl(tmp_path / "snapshots.jsonl", snapshots),
        "outcomes_path": _write_jsonl(
            tmp_path / "outcomes.jsonl",
            [_outcome("early"), _outcome("middle"), _outcome("future")],
        ),
    }

    report = build_t003_creator_archetype_report(**paths)
    rows = {row["token_mint"]: row for row in report["launch_rows"]}

    assert rows["early"]["features"]["creator_prior_launch_count"] == 0
    assert rows["early"]["features"]["creator_prior_median_fdv_proxy_runup"] is None
    assert rows["middle"]["features"]["creator_prior_launch_count"] == 1
    assert rows["middle"]["features"]["creator_prior_median_fdv_proxy_runup"] == pytest.approx(0.1)
    assert rows["middle"]["metadata_json"]["history_max_block_time"] == 1000
    assert rows["middle"]["metadata_json"]["history_max_block_time"] < rows["middle"]["block_time"]
    assert rows["future"]["features"]["creator_prior_launch_count"] == 2
