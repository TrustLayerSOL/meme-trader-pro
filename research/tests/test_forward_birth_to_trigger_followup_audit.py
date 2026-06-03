import json
from pathlib import Path

from research.mtp_research.validation.forward_birth_to_trigger_followup_audit import (
    GUARDRAILS,
    build_birth_to_trigger_followup_audit,
)


def test_birth_to_trigger_audit_detects_later_fdv_by_mint(tmp_path: Path) -> None:
    root = tmp_path / "lake"
    obs = root / "data" / "forward_observation" / "efficient_movers"
    obs.mkdir(parents=True)
    _write_jsonl(
        obs / "candidates.jsonl",
        [
            {
                "observation_id": "birth-a",
                "mint": "mint-a",
                "token_mint": "mint-a",
                "freshness_lane": "birth_watch",
                "candidate_classification": "pumpfun_birth_candidate_observed",
                "event_type": "pumpfun_create",
                "observed_at": 100,
                "launch_time": 90,
            },
            {
                "observation_id": "birth-b",
                "mint": "mint-b",
                "token_mint": "mint-b",
                "freshness_lane": "birth_watch",
                "candidate_classification": "pumpfun_birth_candidate_observed",
                "event_type": "pumpfun_create",
                "observed_at": 200,
                "launch_time": 190,
            },
        ],
    )
    _write_jsonl(
        obs / "candidate_paths.jsonl",
        [
            {
                "observation_id": "birth-a",
                "mint": "mint-a",
                "token_mint": "mint-a",
                "freshness_lane": "birth_watch",
                "event_type": "pumpfun_create",
                "timestamp": 100,
                "fdv_proxy": None,
            },
            {
                "observation_id": "follow-a",
                "mint": "mint-a",
                "token_mint": "mint-a",
                "event_type": "pumpfun_buy",
                "timestamp": 125,
                "fdv_proxy": 12_500,
            },
            {
                "observation_id": "birth-b",
                "mint": "mint-b",
                "token_mint": "mint-b",
                "freshness_lane": "birth_watch",
                "event_type": "pumpfun_create",
                "timestamp": 200,
                "fdv_proxy": None,
            },
        ],
    )

    summary, paths = build_birth_to_trigger_followup_audit(root)

    assert summary["total_birth_watch_candidates"] == 2
    assert summary["birth_mints_with_followup_fdv"] == 1
    assert summary["birth_mints_with_any_trigger_cross"] == 1
    assert summary["trigger_cross_counts"]["10k"] == 1
    assert summary["trigger_cross_counts"]["15k"] == 0
    assert summary["per_mint"][0]["mint"] == "mint-a"
    assert summary["per_mint"][0]["first_fdv_proxy"] == 12_500
    assert summary["per_mint"][0]["first_trigger_level"] == "10k"
    assert summary["per_mint"][1]["mint"] == "mint-b"
    assert summary["per_mint"][1]["followup_status"] == "needs_followup_collection"
    assert paths["summary_json"].exists()
    assert paths["summary_markdown"].exists()
    assert paths["per_mint_csv"].exists()


def test_birth_to_trigger_audit_does_not_count_create_rows_as_followup(tmp_path: Path) -> None:
    root = tmp_path / "lake"
    obs = root / "data" / "forward_observation" / "efficient_movers"
    obs.mkdir(parents=True)
    _write_jsonl(
        obs / "candidates.jsonl",
        [
            {
                "observation_id": "birth-a",
                "mint": "mint-a",
                "freshness_lane": "birth_watch",
                "candidate_classification": "pumpfun_birth_candidate_observed",
                "event_type": "pumpfun_create",
                "observed_at": 100,
            }
        ],
    )
    _write_jsonl(
        obs / "candidate_paths.jsonl",
        [
            {
                "observation_id": "birth-a",
                "mint": "mint-a",
                "freshness_lane": "birth_watch",
                "event_type": "pumpfun_create",
                "timestamp": 100,
                "fdv_proxy": 1_000_000,
            }
        ],
    )

    summary, _ = build_birth_to_trigger_followup_audit(root, write_outputs=False)

    assert summary["birth_mints_with_followup_fdv"] == 0
    assert summary["birth_mints_with_any_trigger_cross"] == 0
    assert summary["per_mint"][0]["max_fdv_proxy"] is None
    assert summary["per_mint"][0]["followup_status"] == "needs_followup_collection"


def test_birth_to_trigger_audit_counts_same_observation_followup_if_not_create(tmp_path: Path) -> None:
    root = tmp_path / "lake"
    obs = root / "data" / "forward_observation" / "efficient_movers"
    obs.mkdir(parents=True)
    _write_jsonl(
        obs / "candidates.jsonl",
        [
            {
                "observation_id": "birth-a",
                "mint": "mint-a",
                "freshness_lane": "birth_watch",
                "candidate_classification": "pumpfun_birth_candidate_observed",
                "event_type": "pumpfun_create",
                "observed_at": 100,
            }
        ],
    )
    _write_jsonl(
        obs / "candidate_paths.jsonl",
        [
            {
                "observation_id": "birth-a",
                "mint": "mint-a",
                "freshness_lane": "birth_watch",
                "event_type": "pumpfun_create",
                "timestamp": 100,
                "fdv_proxy": None,
            },
            {
                "observation_id": "birth-a",
                "mint": "mint-a",
                "freshness_lane": "birth_watch",
                "event_type": "pumpfun_trade",
                "timestamp": 130,
                "fdv_proxy": 9_000,
            },
        ],
    )

    summary, _ = build_birth_to_trigger_followup_audit(root, write_outputs=False)

    assert summary["birth_mints_with_followup_fdv"] == 1
    assert summary["birth_mints_with_any_trigger_cross"] == 0
    assert summary["per_mint"][0]["first_fdv_proxy"] == 9_000
    assert summary["per_mint"][0]["followup_status"] == "fdv_followup_below_trigger"


def test_birth_to_trigger_audit_guardrails_are_read_only() -> None:
    joined = " ".join(GUARDRAILS)

    assert "no_network_calls" in GUARDRAILS
    assert "no_helius_calls" in GUARDRAILS
    assert "no_live_trading" in GUARDRAILS
    assert "no_paper_trading" in GUARDRAILS
    assert "wallet_execution" in joined


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
