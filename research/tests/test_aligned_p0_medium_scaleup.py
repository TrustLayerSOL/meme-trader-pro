import csv
import json
from pathlib import Path

import pytest

from research.mtp_research.validation.aligned_p0_medium_scaleup import (
    BudgetExceededError,
    build_aligned_p0_medium_scaleup,
)


TIERS = [
    "reached_20k_but_never_50k",
    "reached_50k_but_never_100k",
    "reached_100k_but_never_200k",
    "reached_200k_but_never_500k",
    "reached_500k_but_never_1m",
    "reached_1m_plus",
]


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True))
            handle.write("\n")
    return path


def _fixtures(tmp_path: Path) -> dict[str, Path]:
    launch_rows = []
    census_rows = []
    event_rows = []
    base_ts = 1_760_000_000
    for tier_idx, tier in enumerate(TIERS):
        for i in range(3):
            mint = f"mint-{tier_idx}-{i}"
            launch_ts = base_ts + (tier_idx * 20 + i) * 86_400
            launch_rows.append(
                {
                    "launch_id": f"launch-{tier_idx}-{i}",
                    "mint": mint,
                    "creator": None,
                    "launch_ts": launch_ts,
                    "launch_date": f"2026-01-{(tier_idx * 3 + i) % 28 + 1:02d}",
                    "milestone_tier": tier,
                    "crossing_20k_age": 60,
                    "crossing_50k_age": 120 if tier != "reached_20k_but_never_50k" else None,
                    "crossing_100k_age": 180 if tier not in {"reached_20k_but_never_50k", "reached_50k_but_never_100k"} else None,
                    "crossing_200k_age": 240
                    if tier in {"reached_200k_but_never_500k", "reached_500k_but_never_1m", "reached_1m_plus"}
                    else None,
                    "crossing_500k_age": 300 if tier in {"reached_500k_but_never_1m", "reached_1m_plus"} else None,
                    "crossing_1m_age": 360 if tier == "reached_1m_plus" else None,
                }
            )
            census_rows.append(
                {
                    "accepted": True,
                    "mint": mint,
                    "creator_deployer": f"creator-{tier_idx}-{i}",
                    "block_time": launch_ts,
                    "creation_signature": f"sig-{tier_idx}-{i}",
                }
            )
            event_rows.append(
                {
                    "token_mint": mint,
                    "actor": f"wallet-{tier_idx}-{i}",
                    "block_time": launch_ts + 30,
                    "side": "buy",
                }
            )
    return {
        "universe_path": _write_json(tmp_path / "universe.json", {"launch_feature_rows": launch_rows, "dataset": {"event_paths": []}}),
        "census_path": _write_jsonl(tmp_path / "census.jsonl", census_rows),
        "events_path": _write_jsonl(tmp_path / "events.jsonl", event_rows),
        "output_root": tmp_path / "lake",
        "status_path": tmp_path / "STATUS.md",
    }


def test_dry_run_builds_aligned_target_set_and_reports(tmp_path: Path) -> None:
    paths = _fixtures(tmp_path)
    report, outputs = build_aligned_p0_medium_scaleup(
        universe_path=paths["universe_path"],
        event_paths=[paths["events_path"]],
        creator_lookup_paths=[paths["census_path"]],
        output_root=paths["output_root"],
        status_path=paths["status_path"],
        preferred_per_tier=2,
        minimum_total_targets=12,
        max_early_buyer_wallets=100,
        execute=False,
    )

    assert report["execution"]["mode"] == "dry_run"
    assert report["network_calls_made"] == 0
    assert report["target_cohort"]["launches_selected"] == 12
    assert report["target_cohort"]["never_reached_20k_included"] == 0
    assert all(row["selected_launches"] == 2 for row in report["coverage_by_tier"])
    assert report["dry_run_budget"]["projected_credits"] <= 100_000
    assert report["readiness_classification"] == "aligned_p0_medium_dry_run_ready"
    assert outputs["target_set_path"].exists()
    assert outputs["dry_run_json_path"].exists()
    assert outputs["dry_run_markdown_path"].exists()
    assert outputs["status_path"].exists()

    with outputs["target_set_path"].open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert {"launch_id", "mint", "creator", "milestone_tier", "reason_selected"} <= set(rows[0])
    assert len(rows) == 12


def test_budget_gate_blocks_execute_when_projection_is_too_high(tmp_path: Path) -> None:
    paths = _fixtures(tmp_path)
    with pytest.raises(BudgetExceededError):
        build_aligned_p0_medium_scaleup(
            universe_path=paths["universe_path"],
            event_paths=[paths["events_path"]],
            creator_lookup_paths=[paths["census_path"]],
            output_root=paths["output_root"],
            status_path=paths["status_path"],
            preferred_per_tier=2,
            minimum_total_targets=12,
            credit_cap=1,
            execute=True,
        )


def test_execute_uses_existing_collectors_and_writes_combined_outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = _fixtures(tmp_path)

    def fake_early(**kwargs):
        rows = [
            {
                "current_launch_id": "launch-0-0",
                "current_mint": "mint-0-0",
                "wallet": "wallet-a",
                "prior_transaction_count": 1,
                "history_missing_reason": None,
                "wallet_history_source_confidence": "medium",
            }
        ]
        _write_jsonl(Path(kwargs["output_paths"]["jsonl_path"]), rows)
        return {"requests": {"requests_used": 1}, "collection": {"transactions_fetched": 2}, "network_calls_made": 1, "warnings": []}

    def fake_top(**kwargs):
        rows = [
            {
                "launch_id": "launch-0-0",
                "mint": "mint-0-0",
                "milestone": "20k",
                "top_holder_owner": "holder-a",
                "top_holder_share_proxy": 0.25,
                "top_10_holder_share_proxy": 0.75,
                "holder_snapshot_confidence": "medium",
                "is_confirmed_full_chain_snapshot": False,
            }
        ]
        _write_jsonl(Path(kwargs["output_paths"]["jsonl_path"]), rows)
        return {"requests": {"requests_used": 1}, "collection": {"transactions_fetched": 3}, "network_calls_made": 1, "warnings": []}

    def fake_funder(**kwargs):
        rows = [
            {
                "launch_id": "launch-0-0",
                "mint": "mint-0-0",
                "creator": "creator-0-0",
                "candidate_funder": "funder-a",
                "candidate_funder_confidence": "medium",
                "shared_funding_proxy": False,
                "time_linked_funding_proxy": True,
            }
        ]
        _write_jsonl(Path(kwargs["output_paths"]["jsonl_path"]), rows)
        return {"requests": {"requests_used": 1}, "collection": {"transactions_fetched": 4}, "network_calls_made": 1, "warnings": []}

    monkeypatch.setattr("research.mtp_research.validation.aligned_p0_medium_scaleup.run_p0_early_buyer_wallet_history_collection", fake_early)
    monkeypatch.setattr("research.mtp_research.validation.aligned_p0_medium_scaleup.run_p0_top_holder_replay_pilot", fake_top)
    monkeypatch.setattr("research.mtp_research.validation.aligned_p0_medium_scaleup.run_creator_funder_transfer_graph_collection", fake_funder)

    report, outputs = build_aligned_p0_medium_scaleup(
        universe_path=paths["universe_path"],
        event_paths=[paths["events_path"]],
        creator_lookup_paths=[paths["census_path"]],
        output_root=paths["output_root"],
        status_path=paths["status_path"],
        preferred_per_tier=1,
        minimum_total_targets=6,
        execute=True,
    )

    assert report["execution"]["mode"] == "execute"
    assert report["execution"]["execute_completed"] is True
    assert report["readiness_classification"] == "aligned_p0_medium_partial_needs_review"
    assert report["collection_summary"]["total_requests_used"] == 3
    assert report["collection_summary"]["total_transactions_fetched"] == 9
    assert report["overlap_audit"]["launches_with_all_three_p0_layers"] == 1
    assert outputs["combined_jsonl_path"].exists()
    assert outputs["summary_json_path"].exists()


def test_guardrails_and_deterministic_selection(tmp_path: Path) -> None:
    paths = _fixtures(tmp_path)
    first, _ = build_aligned_p0_medium_scaleup(
        universe_path=paths["universe_path"],
        event_paths=[paths["events_path"]],
        creator_lookup_paths=[paths["census_path"]],
        output_root=paths["output_root"] / "a",
        status_path=tmp_path / "A.md",
        preferred_per_tier=2,
        minimum_total_targets=12,
    )
    second, _ = build_aligned_p0_medium_scaleup(
        universe_path=paths["universe_path"],
        event_paths=[paths["events_path"]],
        creator_lookup_paths=[paths["census_path"]],
        output_root=paths["output_root"] / "b",
        status_path=tmp_path / "B.md",
        preferred_per_tier=2,
        minimum_total_targets=12,
    )

    assert first["target_cohort"]["target_launch_ids"] == second["target_cohort"]["target_launch_ids"]
    assert "no_trading_logic" in first["methodology_flags"]
    assert "no_thesis_promotion" in first["methodology_flags"]
    text = json.dumps(first).lower()
    assert "insider" not in text
    assert "manipulator" not in text
    assert "buy_rule" not in text


def test_real_lifecycle_schema_selects_pumpfun_buys_but_not_create_events(tmp_path: Path) -> None:
    paths = _fixtures(tmp_path)
    rows = [
        {
            "token_mint": "mint-0-0",
            "actor": "creator-wallet",
            "block_time": 1_760_000_030,
            "event_type": "token_accumulation",
            "side": "accumulate",
            "venue": "pumpfun_create",
        },
        {
            "token_mint": "mint-0-0",
            "actor": "buyer-wallet",
            "block_time": 1_760_000_031,
            "event_type": "token_accumulation",
            "side": "accumulate",
            "venue": "pumpfun_buy",
        },
    ]
    events = _write_jsonl(tmp_path / "real_schema_events.jsonl", rows)

    report, _outputs = build_aligned_p0_medium_scaleup(
        universe_path=paths["universe_path"],
        event_paths=[events],
        creator_lookup_paths=[paths["census_path"]],
        output_root=paths["output_root"],
        status_path=paths["status_path"],
        preferred_per_tier=1,
        minimum_total_targets=6,
        execute=False,
    )

    assert report["layer_targets"]["early_buyer_wallet_targets"] == 1
