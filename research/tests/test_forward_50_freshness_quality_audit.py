import json
from pathlib import Path

from research.mtp_research.validation.forward_50_freshness_quality_audit import (
    GUARDRAILS,
    build_forward_50_freshness_quality_audit,
    classify_actionability,
    classify_freshness,
    classify_scale_readiness,
)


def test_classifies_first_seen_and_already_above_trigger() -> None:
    assert classify_freshness(source="helius_program_logs_pumpfun", first_seen_fdv_proxy=12_000, first_cross_times={"15k": 1}) == "pre_15k_observed_candidate"
    assert classify_freshness(source="helius_program_logs_pumpswap", first_seen_fdv_proxy=25_000, first_cross_times={}) == "already_above_20k_candidate"
    assert classify_freshness(source="helius_program_logs_pumpswap", first_seen_fdv_proxy=75_000, first_cross_times={}) == "already_above_50k_candidate"


def test_classifies_late_detected_above_100k() -> None:
    assert classify_freshness(source="helius_program_logs_pumpswap", first_seen_fdv_proxy=125_000, first_cross_times={}) == "already_above_100k_candidate"
    assert classify_actionability(125_000) == "observed_after_100k"
    assert classify_actionability(750_000) == "detected_too_late"


def test_build_audit_outputs_source_duplicates_fdv_and_reconciliation(tmp_path: Path) -> None:
    root = tmp_path / "lake"
    obs = root / "data" / "forward_observation" / "efficient_movers"
    raw = root / "data" / "raw" / "forward_observation" / "efficient_movers"
    obs.mkdir(parents=True)
    raw.mkdir(parents=True)
    _write_jsonl(
        obs / "candidates.jsonl",
        [
            {"observation_id": "o1", "mint": "mint-a", "source": "helius_program_logs_pumpfun", "first_seen_time": 100, "observed_at": 100},
            {"observation_id": "o2", "mint": "mint-b", "source": "helius_program_logs_pumpswap", "first_seen_time": 200, "observed_at": 200},
            {"observation_id": "o3", "mint": "mint-c", "source": "helius_program_logs_pumpswap", "first_seen_time": 300, "observed_at": 300},
        ],
    )
    _write_jsonl(
        obs / "candidate_paths.jsonl",
            [
                {"observation_id": "o1", "mint": "mint-a", "source": "helius_program_logs_pumpfun", "timestamp": 100, "fdv_proxy": 12_000, "event_count": 1, "buy_count": 1, "sell_count": 0, "active_wallets": 1},
                {"observation_id": "o1", "mint": "mint-a", "source": "helius_program_logs_pumpfun", "timestamp": 110, "fdv_proxy": 16_000, "event_count": 2, "buy_count": 2, "sell_count": 0, "active_wallets": 2},
                {"observation_id": "o2", "mint": "mint-b", "source": "helius_program_logs_pumpswap", "timestamp": 200, "fdv_proxy": 55_000, "event_count": 1, "buy_count": 1, "sell_count": 0, "active_wallets": 1},
                {"observation_id": "o3", "mint": "mint-c", "source": "helius_program_logs_pumpswap", "timestamp": 300, "fdv_proxy": 125_000, "event_count": 1, "buy_count": 1, "sell_count": 0, "active_wallets": 1},
            ],
    )
    for name in ["candidate_events.jsonl", "candidate_metadata.jsonl", "candidate_holders.jsonl", "candidate_drawdowns.jsonl"]:
        _write_jsonl(obs / name, [{"observation_id": "o1"}, {"observation_id": "o2"}, {"observation_id": "o3"}])
    _write_jsonl(
        raw / "source_candidates.jsonl",
        [
            {"observation_id": "o1", "mint": "mint-a", "source": "helius_program_logs_pumpfun"},
            {"observation_id": "o2", "mint": "mint-b", "source": "helius_program_logs_pumpswap"},
            {"observation_id": "o3", "mint": "mint-c", "source": "helius_program_logs_pumpswap"},
        ],
    )
    _write_jsonl(raw / "helius_rpc_raw.jsonl", [{"source_adapter": "helius_program_logs_pumpswap", "mint": None}])
    (obs / "status.json").write_text(json.dumps({"total_candidates_observed": 3}) + "\n", encoding="utf-8")

    summary, paths = build_forward_50_freshness_quality_audit(root, max_candidates=3)

    assert summary["candidates_audited"] == 3
    assert summary["source_mix"] == {"helius_program_logs_pumpfun": 1, "helius_program_logs_pumpswap": 2}
    assert summary["freshness_class_distribution"]["pre_15k_observed_candidate"] == 1
    assert summary["freshness_class_distribution"]["already_above_50k_candidate"] == 1
    assert summary["freshness_class_distribution"]["already_above_100k_candidate"] == 1
    assert summary["duplicate_class_distribution"]["unique_candidate"] == 3
    assert summary["fdv_sanity_distribution"]["valid_fdv_proxy"] == 3
    assert summary["status_reconciliation_mismatch_count"] > 0
    assert paths["summary_json"].exists()
    assert paths["freshness_csv"].exists()


def test_scale_readiness_blocks_late_or_non_fresh_sample() -> None:
    readiness = classify_scale_readiness(
        candidate_count=10,
        valid_fdv_count=10,
        duplicate_classes={"unique_candidate": 10},
        freshness_classes={"already_above_50k_candidate": 10},
        status_mismatches=0,
    )

    assert readiness == "forward_50_needs_source_freshness_repair"


def test_guardrails_prevent_live_or_paper_trading_language() -> None:
    joined = " ".join(GUARDRAILS)

    assert "no_network_calls" in GUARDRAILS
    assert "no_live_trading" in GUARDRAILS
    assert "no_paper_trading" in GUARDRAILS
    assert "wallet_execution" in joined


def test_audit_is_deterministic(tmp_path: Path) -> None:
    root = tmp_path / "lake"
    obs = root / "data" / "forward_observation" / "efficient_movers"
    raw = root / "data" / "raw" / "forward_observation" / "efficient_movers"
    obs.mkdir(parents=True)
    raw.mkdir(parents=True)
    _write_jsonl(obs / "candidates.jsonl", [{"observation_id": "o1", "mint": "mint-a", "source": "source-a", "observed_at": 1}])
    _write_jsonl(obs / "candidate_paths.jsonl", [{"observation_id": "o1", "mint": "mint-a", "timestamp": 1, "fdv_proxy": 25_000}])

    first, _ = build_forward_50_freshness_quality_audit(root, max_candidates=1, write_outputs=False)
    second, _ = build_forward_50_freshness_quality_audit(root, max_candidates=1, write_outputs=False)

    assert first == second


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
