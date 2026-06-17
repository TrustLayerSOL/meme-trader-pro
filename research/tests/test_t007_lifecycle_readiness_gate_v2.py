from __future__ import annotations

from research.mtp_research.validation.t007_lifecycle_readiness_gate_v2 import evaluate_t007_lifecycle_readiness_v2


def test_v2_gate_blocks_without_level_a_migration() -> None:
    gate = evaluate_t007_lifecycle_readiness_v2({"level_b_migration_count": 4, "source_gap_gate_passed": True})

    assert gate["decision_label"] == "T007_LEVEL_A_MIGRATION_SOURCE_STILL_BROKEN"
    assert gate["can_run_60m_thesis_scan"] is False
    assert "level_a_migration_count_zero" in gate["blocking_reasons"]


def test_v2_gate_blocks_source_gaps_even_with_level_a() -> None:
    gate = evaluate_t007_lifecycle_readiness_v2(
        {
            "level_a_migration_count": 2,
            "pool_state_ready_count": 2,
            "source_gap_gate_passed": False,
            "unbackfilled_gap_count": 1,
            "summary_raw_counter_match": True,
        }
    )

    assert gate["decision_label"] == "T007_SOURCE_GAP_BACKFILL_BROKEN"
    assert "unbackfilled_gap_count_nonzero" in gate["blocking_reasons"]


def test_v2_gate_allows_60m_only_after_level_a_pool_state_and_clean_sources() -> None:
    gate = evaluate_t007_lifecycle_readiness_v2(
        {
            "level_a_migration_count": 3,
            "pool_state_ready_count": 3,
            "quote_ready_count": 0,
            "trade_data_ready_count": 0,
            "source_gap_gate_passed": True,
            "unbackfilled_gap_count": 0,
            "summary_raw_counter_match": True,
            "decoder_schema_ok": True,
            "watcher_schema_ok": True,
            "valuation_ladder_suppressed": True,
            "trading_disabled": True,
            "paper_trading_disabled": True,
            "wallet_signing_disabled": True,
            "mayhem_untouched": True,
        }
    )

    assert gate["decision_label"] == "T007_LEVEL_A_PROOF_READY"
    assert gate["can_run_10m_feature_proof"] is True
    assert gate["can_run_60m_thesis_scan"] is True
    assert gate["can_run_2h_plus_scan"] is False
    assert gate["full_post_migration_exit_thesis_allowed"] is False
