import json
from pathlib import Path

from research.mtp_research.validation.entity_proxy_rollout import (
    build_entity_proxy_rollout,
    write_entity_proxy_rollout_outputs,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    return path


def _candidate(mint: str, creator: str, launch_ts: int) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "token_mint": mint,
        "launch_ts": launch_ts,
        "metadata_json": {
            "creator_deployer": creator,
            "creation_signature": f"create-{mint}",
            "bonding_curve": f"curve-{mint}",
            "associated_bonding_curve": f"assoc-{mint}",
        },
    }


def _event(mint: str, actor: str | None, age: int, side: str) -> dict:
    return {
        "event_id": f"{mint}-{actor}-{age}-{side}",
        "token_mint": mint,
        "actor": actor,
        "side": side,
        "event_type": "token_accumulation" if side == "accumulate" else "token_distribution",
        "venue": "pumpfun_buy" if side == "accumulate" else "pumpfun_sell",
        "signature": f"sig-{mint}-{actor}-{age}-{side}",
        "block_time": 1_700_000_000 + age,
        "slot": 1_700_000_000 + age,
        "base_qty": 10,
        "quote_qty": 1,
        "metadata_json": {},
    }


def _holder(mint: str, age: int, creator_share: float | None) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "mint": mint,
        "snapshot_age_seconds": age,
        "holder_count": 4,
        "top_holder_share": 0.5,
        "top_10_holder_share": 1.0,
        "creator_holder_share": creator_share,
        "holder_snapshot_confidence": "medium",
        "is_observed_delta_replay": True,
        "is_confirmed_full_chain_snapshot": False,
    }


def test_rollout_builds_required_proxy_rows_without_outcomes(tmp_path: Path) -> None:
    candidates = [
        _candidate("mint-a", "creator-1", 1_700_000_000),
        _candidate("mint-b", "creator-1", 1_700_000_050),
        _candidate("mint-c", "creator-2", 1_700_000_100),
    ]
    events = [
        _event("mint-a", "shared", 5, "accumulate"),
        _event("mint-a", "shared", 40, "distribute"),
        _event("mint-a", "actor-a", 10, "accumulate"),
        _event("mint-b", "shared", 8, "accumulate"),
        _event("mint-b", "actor-b", 20, "accumulate"),
    ]
    holders = [_holder("mint-a", 1800, 0.3), _holder("mint-b", 1800, 0.4), _holder("mint-c", 1800, None)]

    rollout = build_entity_proxy_rollout(
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", candidates),
        events_path=_write_jsonl(tmp_path / "events.jsonl", events),
        holder_state_snapshots_path=_write_jsonl(tmp_path / "holder.jsonl", holders),
    )

    assert rollout["launches_processed"] == 3
    assert rollout["readiness_classification"] == "entity_proxy_partial_needs_review"
    assert rollout["audit"]["proxy_coverage"]["creator_linked_share_proxy"]["available_count"] == 2
    first = rollout["proxy_rows"][0]
    assert set(first) >= {
        "creator_linked_share_proxy",
        "repeated_actor_overlap_proxy",
        "repeated_buyer_overlap_proxy",
        "synchronized_participation_proxy",
        "circularity_proxy",
        "churn_proxy",
        "proxy_confidence",
        "proxy_missing_reason",
    }
    assert first["repeated_actor_overlap_proxy"] == 1
    assert first["repeated_buyer_overlap_proxy"] == 1
    assert first["circularity_proxy"] == 1
    assert first["proxy_confidence"] in {"high", "medium", "low"}
    assert "outcome" not in json.dumps(rollout["proxy_rows"]).lower()


def test_rollout_writes_jsonl_parquet_and_audit_reports(tmp_path: Path) -> None:
    rollout = build_entity_proxy_rollout(
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", [_candidate("mint-a", "creator-a", 1)]),
        events_path=_write_jsonl(tmp_path / "events.jsonl", [_event("mint-a", "actor-a", 2, "accumulate")]),
        holder_state_snapshots_path=_write_jsonl(tmp_path / "holder.jsonl", [_holder("mint-a", 1800, 0.1)]),
    )

    paths = write_entity_proxy_rollout_outputs(
        rollout,
        dataset_dir=tmp_path / "entity_proxy",
        report_dir=tmp_path / "reports",
    )

    assert paths["jsonl_path"].exists()
    assert paths["parquet_path"].exists()
    assert paths["audit_json_path"].exists()
    assert paths["audit_markdown_path"].exists()
    assert "No thesis cycle was run." in paths["audit_markdown_path"].read_text(encoding="utf-8")
