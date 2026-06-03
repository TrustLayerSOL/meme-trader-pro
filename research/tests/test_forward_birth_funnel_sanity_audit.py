import csv
import json
from pathlib import Path

from research.mtp_research.validation.forward_birth_funnel_sanity_audit import (
    GUARDRAILS,
    build_forward_birth_funnel_sanity_audit,
    classify_birth_freshness,
    classify_followup_bias,
    classify_milestone_provenance,
    validate_milestone_ordering,
)


def test_sanity_audit_dedupes_and_revises_funnel_counts(tmp_path: Path) -> None:
    root = tmp_path / "lake"
    obs = root / "data" / "forward_observation" / "efficient_movers"
    raw = root / "data" / "raw" / "forward_observation" / "efficient_movers"
    obs.mkdir(parents=True)
    raw.mkdir(parents=True)
    _write_jsonl(
        obs / "candidates.jsonl",
        [
            _birth_candidate("birth-a", "mint-a", 100, 100),
            _birth_candidate("birth-a-dupe", "mint-a", 101, 100),
            _birth_candidate("birth-b", "mint-b", 200, 200),
        ],
    )
    _write_jsonl(
        raw / "source_candidates.jsonl",
        [
            {**_birth_candidate("birth-a", "mint-a", 100, 100), "transaction_signature": "sig-a"},
            {**_birth_candidate("birth-b", "mint-b", 200, 200), "transaction_signature": "sig-b"},
        ],
    )
    _write_jsonl(
        obs / "candidate_paths.jsonl",
        [
            _create_path("birth-a", "mint-a", 100),
            _followup_path("follow-a-0", "mint-a", 105, 9_000),
            _followup_path("follow-a-1", "mint-a", 110, 12_000),
            _followup_path("follow-a-1-duplicate", "mint-a", 110, 12_000),
            _followup_path("follow-a-2", "mint-a", 130, 55_000),
            _create_path("birth-b", "mint-b", 200),
        ],
    )
    _write_jsonl(
        obs / "candidate_events.jsonl",
        [
            _create_event("birth-a", "mint-a", 100, "sig-a"),
            _event("follow-a-1", "mint-a", 110, "trade-a"),
            _create_event("birth-b", "mint-b", 200, "sig-b"),
        ],
    )

    summary, paths = build_forward_birth_funnel_sanity_audit(root)

    assert summary["raw_funnel_counts"]["birth_watch_count"] == 3
    assert summary["strict_deduped_funnel_counts"]["birth_watch_count"] == 2
    assert summary["raw_funnel_counts"]["crossed_10k"] == 2
    assert summary["strict_deduped_funnel_counts"]["crossed_10k"] == 1
    assert summary["observed_followup_only_funnel_counts"]["crossed_10k"] == 1
    assert summary["true_near_birth_funnel_counts"]["crossed_10k"] == 1
    assert summary["duplicate_counts"]["duplicate_mint_rows"] == 1
    assert summary["duplicate_counts"]["duplicate_followup_rows"] == 1
    assert summary["duplicate_counts"]["duplicate_milestone_rows"] == 1
    assert summary["milestone_provenance_summary"]["observed_followup_path"] == 5
    assert summary["freshness_summary"]["true_birth_observed"] == 1
    assert summary["freshness_summary"]["unknown_birth_freshness"] == 1
    assert summary["ten_k_mover_completeness_summary"]["total_10k_crossers"] == 1
    assert summary["ten_k_mover_completeness_summary"]["freshness_groups"]["true/near-birth observed 10k crossers"] == 1
    assert summary["ten_k_mover_completeness_summary"]["field_coverage"]["mint"]["available"] == 1
    assert paths["summary_json"].exists()
    assert paths["summary_markdown"].exists()
    assert paths["dedupe_csv"].exists()
    assert paths["ten_k_mover_completeness_csv"].exists()
    assert paths["manual_review_sample_csv"].exists()
    assert paths["status_markdown"].exists()

    with paths["dedupe_csv"].open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert any(row["duplicate_cause"] == "duplicate_candidate_should_collapse" for row in rows)
    assert any(row["duplicate_cause"] == "duplicate_milestone_row" for row in rows)


def test_milestone_provenance_requires_observed_followup_path() -> None:
    assert classify_milestone_provenance({"source": "helius_birth_watch_followup", "event_type": "pumpfun_trade"}) == (
        "observed_followup_path",
        True,
    )
    assert classify_milestone_provenance({"source": "summary_peak_label", "event_type": "summary"}) == (
        "summary_peak_label",
        False,
    )
    assert classify_milestone_provenance({"source": "outcome_label", "event_type": "later_outcome"}) == (
        "later_outcome_label",
        False,
    )
    assert classify_milestone_provenance({"source": "unknown"}) == ("unknown", False)


def test_milestone_ordering_flags_same_timestamp_and_impossible_order() -> None:
    ok = validate_milestone_ordering(
        create_time=100,
        first_followup_time=105,
        milestone_times={"10k": 110, "15k": 110, "20k": 120},
    )
    assert ok == ["same_timestamp_multiple_milestones"]

    bad = validate_milestone_ordering(
        create_time=100,
        first_followup_time=90,
        milestone_times={"10k": 120, "20k": 110, "50k": 105},
    )
    assert "impossible_time_order" in bad
    assert "20k_before_10k" in bad
    assert "50k_before_20k" in bad


def test_birth_freshness_classification_uses_first_followup_fdv_and_time() -> None:
    assert classify_birth_freshness(True, "pumpfun_create", 100, 105, 9_000) == "true_birth_observed"
    assert classify_birth_freshness(True, "pumpfun_create", 100, 130, 9_000) == "near_birth_observed"
    assert classify_birth_freshness(True, "pumpfun_create", 100, 180, 9_000) == "first_followup_after_activity"
    assert classify_birth_freshness(True, "pumpfun_create", 100, 105, 25_000) == "first_followup_already_above_20k"
    assert classify_birth_freshness(False, "pumpfun_trade", 100, 105, 9_000) == "unknown_birth_freshness"


def test_followup_bias_classification_is_deterministic() -> None:
    assert classify_followup_bias(total_births=100, fdv_followup=95, no_fdv_evidence=5, crossed_10k=10) == "low_bias_risk"
    assert classify_followup_bias(total_births=100, fdv_followup=70, no_fdv_evidence=30, crossed_10k=10) == "medium_bias_risk"
    assert classify_followup_bias(total_births=100, fdv_followup=30, no_fdv_evidence=70, crossed_10k=10) == "high_bias_risk"
    assert classify_followup_bias(total_births=0, fdv_followup=0, no_fdv_evidence=0, crossed_10k=0) == "unknown_bias_risk"


def test_sanity_audit_guardrails_do_not_allow_collection_or_trading() -> None:
    joined = " ".join(GUARDRAILS)

    assert "no_network_calls" in GUARDRAILS
    assert "no_helius_calls" in GUARDRAILS
    assert "no_additional_collection" in GUARDRAILS
    assert "no_live_trading" in GUARDRAILS
    assert "no_paper_trading" in GUARDRAILS
    assert "wallet_execution" in joined


def _birth_candidate(observation_id: str, mint: str, observed_at: int, launch_time: int) -> dict:
    return {
        "observation_id": observation_id,
        "mint": mint,
        "token_mint": mint,
        "freshness_lane": "birth_watch",
        "candidate_classification": "pumpfun_birth_candidate_observed",
        "event_type": "pumpfun_create",
        "observed_at": observed_at,
        "launch_time": launch_time,
        "source": "helius_program_logs_pumpfun_create_scanner",
    }


def _create_path(observation_id: str, mint: str, timestamp: int) -> dict:
    return {
        "observation_id": observation_id,
        "mint": mint,
        "token_mint": mint,
        "event_type": "pumpfun_create",
        "timestamp": timestamp,
        "source": "helius_program_logs_pumpfun_create_scanner",
        "fdv_proxy": None,
    }


def _followup_path(observation_id: str, mint: str, timestamp: int, fdv_proxy: float) -> dict:
    return {
        "observation_id": observation_id,
        "mint": mint,
        "token_mint": mint,
        "event_type": "pumpfun_trade",
        "timestamp": timestamp,
        "source": "helius_birth_watch_followup",
        "fdv_proxy": fdv_proxy,
        "buy_count": 1,
        "sell_count": 0,
        "event_count": 1,
    }


def _create_event(observation_id: str, mint: str, timestamp: int, signature: str) -> dict:
    return {
        "observation_id": observation_id,
        "mint": mint,
        "token_mint": mint,
        "event_type": "pumpfun_create",
        "timestamp": timestamp,
        "transaction_time": timestamp,
        "transaction_signature": signature,
        "source": "helius_program_logs_pumpfun_create_scanner",
    }


def _event(observation_id: str, mint: str, timestamp: int, signature: str) -> dict:
    return {
        "observation_id": observation_id,
        "mint": mint,
        "token_mint": mint,
        "event_type": "pumpfun_trade",
        "timestamp": timestamp,
        "transaction_time": timestamp,
        "transaction_signature": signature,
        "source": "helius_birth_watch_followup",
    }


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
