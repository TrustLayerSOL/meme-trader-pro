import json
from pathlib import Path

from research.mtp_research.validation.entity_manipulation_feasibility import (
    build_entity_proxy_feasibility_report,
    write_entity_proxy_feasibility_outputs,
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
        "pool_address": f"pool-{mint}",
        "venue": "pumpfun",
        "metadata_json": {
            "creator_deployer": creator,
            "creation_signature": f"create-{mint}",
            "slot": launch_ts + 10,
            "bonding_curve": f"curve-{mint}",
            "associated_bonding_curve": f"assoc-{mint}",
        },
    }


def _event(mint: str, actor: str | None, age: int, side: str, signature: str | None = None) -> dict:
    launch_ts = 1_700_000_000
    return {
        "event_id": f"{mint}-{actor}-{age}-{side}",
        "token_mint": mint,
        "actor": actor,
        "side": side,
        "event_type": "token_accumulation" if side == "accumulate" else "token_distribution",
        "venue": "pumpfun_buy" if side == "accumulate" else "pumpfun_sell",
        "signature": signature or f"sig-{mint}-{actor}-{age}-{side}",
        "slot": launch_ts + age,
        "block_time": launch_ts + age,
        "base_qty": 10,
        "quote_qty": 1,
        "metadata_json": {"source_signature": signature or f"sig-{mint}-{actor}-{age}-{side}"},
    }


def _holder_state(mint: str, age: int, creator_share: float) -> dict:
    return {
        "launch_id": f"launch-{mint}",
        "mint": mint,
        "snapshot_age_seconds": age,
        "holder_count": 5,
        "top_holder_share": 0.4,
        "top_10_holder_share": 0.9,
        "creator_holder_share": creator_share,
        "holder_snapshot_confidence": "medium",
        "is_observed_delta_replay": True,
        "is_confirmed_full_chain_snapshot": False,
    }


def test_entity_proxy_pilot_builds_only_deterministic_neutral_proxies(tmp_path: Path) -> None:
    candidates = [
        _candidate("mint-a", "creator-1", 1_700_000_000),
        _candidate("mint-b", "creator-1", 1_700_000_100),
        _candidate("mint-c", "creator-2", 1_700_000_200),
    ]
    events = [
        _event("mint-a", "shared-wallet", 5, "accumulate"),
        _event("mint-a", "shared-wallet", 45, "distribute"),
        _event("mint-a", "actor-a", 10, "accumulate", signature="same-sig"),
        _event("mint-b", "shared-wallet", 8, "accumulate"),
        _event("mint-b", "actor-b", 11, "accumulate", signature="same-sig"),
        _event("mint-c", "actor-c", 90, "accumulate"),
    ]
    holder_rows = [
        _holder_state("mint-a", 1800, 0.25),
        _holder_state("mint-b", 1800, 0.5),
        _holder_state("mint-c", 1800, 0.0),
    ]

    report = build_entity_proxy_feasibility_report(
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", candidates),
        events_path=_write_jsonl(tmp_path / "events.jsonl", events),
        holder_state_snapshots_path=_write_jsonl(tmp_path / "holder.jsonl", holder_rows),
        max_launches=100,
        max_events=10_000,
    )

    assert report["scope"]["launches_attempted"] == 3
    assert report["scope"]["events_inspected"] == 6
    assert report["data_availability"]["event_fields"]["actor"]["coverage_pct"] == 100
    assert report["data_availability"]["event_fields"]["funding_source_wallet"]["available_count"] == 0
    assert report["proxy_family_feasibility"]["repeated_participant_overlap_proxy"]["status"] == "feasible"
    assert report["proxy_family_feasibility"]["common_transaction_source_proxy"]["status"] == "partial"
    assert report["proxy_family_feasibility"]["funding_link_proxy"]["status"] == "blocked"
    first = report["pilot_rows"][0]
    assert first["proxy_fields"]["shared_actor_count"] >= 1
    assert first["proxy_fields"]["quick_buy_sell_churn_actor_count"] == 1
    assert first["confidence_flags"]["uses_outcomes"] is False
    assert "insider" not in json.dumps(report).lower()
    assert "wash trading" not in json.dumps(report).lower()


def test_bounded_pilot_limits_launches_and_events(tmp_path: Path) -> None:
    candidates = [_candidate(f"mint-{i}", f"creator-{i}", 1_700_000_000 + i) for i in range(4)]
    events = [_event(f"mint-{i // 2}", f"actor-{i}", i, "accumulate") for i in range(8)]

    report = build_entity_proxy_feasibility_report(
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", candidates),
        events_path=_write_jsonl(tmp_path / "events.jsonl", events),
        holder_state_snapshots_path=_write_jsonl(tmp_path / "holder.jsonl", []),
        max_launches=2,
        max_events=3,
    )

    assert report["scope"]["launches_attempted"] == 2
    assert report["scope"]["events_inspected"] == 3
    assert report["readiness_classification"] == "entity_proxy_partial_needs_more_data"


def test_writes_availability_and_pilot_outputs(tmp_path: Path) -> None:
    report = build_entity_proxy_feasibility_report(
        candidates_path=_write_jsonl(tmp_path / "candidates.jsonl", [_candidate("mint-a", "creator-a", 1)]),
        events_path=_write_jsonl(tmp_path / "events.jsonl", [_event("mint-a", "actor-a", 5, "accumulate")]),
        holder_state_snapshots_path=_write_jsonl(tmp_path / "holder.jsonl", [_holder_state("mint-a", 1800, 0.1)]),
    )

    paths = write_entity_proxy_feasibility_outputs(report, output_dir=tmp_path / "reports")

    assert paths["data_availability_markdown_path"].exists()
    assert paths["pilot_json_path"].exists()
    assert paths["pilot_markdown_path"].exists()
    assert "No thesis cycle was run." in paths["pilot_markdown_path"].read_text(encoding="utf-8")
