from __future__ import annotations

from collections import Counter
from pathlib import Path


def _buy_minus_event() -> dict:
    return {
        "signature": "sig-buy-minus",
        "event_type": "buy",
        "pool": "pool-a",
        "mint": "mint-a",
        "quote_asset": "SOL",
        "base_amount": 1000,
        "quote_amount": 100_000,
        "user_quote_amount": 98_765,
        "lp_fee": 19,
        "protocol_fee": 919,
        "coin_creator_fee": 0,
        "cashback": 297,
        "buyback_fee": 459,
        "lp_fee_basis_points": 2,
        "protocol_fee_basis_points": 93,
        "coin_creator_fee_basis_points": 0,
        "cashback_fee_basis_points": 30,
        "buyback_fee_basis_points": 5000,
    }


def _sell_buyback_event() -> dict:
    return {
        "signature": "sig-sell-buyback",
        "event_type": "sell",
        "pool": "pool-b",
        "mint": "mint-b",
        "quote_asset": "SOL",
        "base_amount": 2000,
        "quote_amount": 1_000_000,
        "user_quote_amount": 988_500,
        "lp_fee": 2_000,
        "protocol_fee": 500,
        "coin_creator_fee": 9_000,
        "cashback": 0,
        "buyback_fee": 2_500,
        "lp_fee_basis_points": 20,
        "protocol_fee_basis_points": 5,
        "coin_creator_fee_basis_points": 90,
        "cashback_fee_basis_points": 0,
        "buyback_fee_basis_points": 5000,
    }


def test_t007av_replay_validation_handles_buy_user_quote_below_event_quote() -> None:
    from research.mtp_research.validation.t007av_pumpswap_swap_event_fee_confirmation import (
        build_fee_formula_replay_validation_row,
    )

    row = build_fee_formula_replay_validation_row(_buy_minus_event())

    assert row["predicted_quote_with_event_fees"] == 98_765
    assert row["absolute_error"] == 0
    assert row["validation_status"] == "pass"


def test_t007av_replay_validation_excludes_buyback_from_user_quote_endpoint() -> None:
    from research.mtp_research.validation.t007av_pumpswap_swap_event_fee_confirmation import (
        build_fee_formula_replay_validation_row,
    )

    row = build_fee_formula_replay_validation_row(_sell_buyback_event())

    assert row["predicted_quote_with_event_fees"] == 988_500
    assert row["absolute_error"] == 0
    assert row["validation_status"] == "pass"


def test_t007ax_formula_variant_comparison_reports_pass_fail_counts_by_side() -> None:
    from research.mtp_research.validation.t007ax_pumpswap_fee_replay_failure_forensics import (
        compare_formula_variants,
    )

    rows = compare_formula_variants([_buy_minus_event(), _sell_buyback_event()])
    by_name = {row["variant_name"]: row for row in rows}

    assert by_name["event_active_user_fee_signed_by_observed_delta"]["pass_count"] == 2
    assert by_name["event_active_user_fee_signed_by_observed_delta"]["buy_pass_count"] == 1
    assert by_name["event_active_user_fee_signed_by_observed_delta"]["sell_pass_count"] == 1
    assert by_name["current_legacy_event_type_all_fees"]["fail_count"] == 2


def test_t007ax_failure_clustering_groups_fee_side_and_gross_net_mismatch() -> None:
    from research.mtp_research.validation.t007ax_pumpswap_fee_replay_failure_forensics import (
        enrich_failed_replay_rows,
    )

    enriched = enrich_failed_replay_rows([_buy_minus_event(), _sell_buyback_event()], failed_signatures={"sig-buy-minus", "sig-sell-buyback"})
    counts = Counter(row["failure_classification"] for row in enriched)

    assert counts["fee_side_mismatch"] == 1
    assert counts["amount_field_gross_net_mismatch"] == 1


def test_t007ax_multi_event_signatures_are_detected() -> None:
    from research.mtp_research.validation.t007ax_pumpswap_fee_replay_failure_forensics import (
        build_signature_event_counts,
        enrich_failed_replay_rows,
    )

    events = [_buy_minus_event(), {**_buy_minus_event(), "event_index": 1, "mint": "mint-c"}]
    counts = build_signature_event_counts(events)
    enriched = enrich_failed_replay_rows(events, failed_signatures={"sig-buy-minus"}, signature_event_counts=counts)

    assert counts["sig-buy-minus"] == 2
    assert all(row["transaction_has_multiple_pumpswap_events"] is True for row in enriched)


def test_t007ax_confirmation_requires_both_buy_and_sell_to_pass() -> None:
    from research.mtp_research.validation.t007ax_pumpswap_fee_replay_failure_forensics import (
        assign_fee_model_status_from_variant,
    )

    status = assign_fee_model_status_from_variant(
        {
            "rows_tested": 10,
            "pass_count": 10,
            "fail_count": 0,
            "buy_pass_count": 10,
            "sell_pass_count": 0,
            "buy_fail_count": 0,
            "sell_fail_count": 0,
        },
        unexplained_failure_count=0,
    )

    assert status["fee_model_status"] == "unknown"
    assert status["quote_confidence"] == "low"


def test_t007ax_status_assumed_for_most_rows_with_documented_failures() -> None:
    from research.mtp_research.validation.t007ax_pumpswap_fee_replay_failure_forensics import (
        assign_fee_model_status_from_variant,
    )

    status = assign_fee_model_status_from_variant(
        {
            "rows_tested": 100,
            "pass_count": 96,
            "fail_count": 4,
            "buy_pass_count": 40,
            "sell_pass_count": 56,
            "buy_fail_count": 2,
            "sell_fail_count": 2,
        },
        unexplained_failure_count=0,
    )

    assert status["fee_model_status"] == "assumed"
    assert status["quote_confidence"] == "medium"


def test_t007ax_status_unknown_with_unexplained_failure_cluster() -> None:
    from research.mtp_research.validation.t007ax_pumpswap_fee_replay_failure_forensics import (
        assign_fee_model_status_from_variant,
    )

    status = assign_fee_model_status_from_variant(
        {
            "rows_tested": 100,
            "pass_count": 96,
            "fail_count": 4,
            "buy_pass_count": 40,
            "sell_pass_count": 56,
            "buy_fail_count": 2,
            "sell_fail_count": 2,
        },
        unexplained_failure_count=1,
    )

    assert status["fee_model_status"] == "unknown"
    assert status["quote_confidence"] == "low"


def test_t007ax_guardrails_keep_valuation_mayhem_and_trading_paths_off() -> None:
    from research.mtp_research.validation.t007ax_pumpswap_fee_replay_failure_forensics import (
        T007AX_GUARDRAILS,
    )

    assert T007AX_GUARDRAILS["live_scan_ran"] is False
    assert T007AX_GUARDRAILS["valuation_ladder_suppressed"] is True
    assert T007AX_GUARDRAILS["mayhem_files_modified"] is False
    assert T007AX_GUARDRAILS["trading_paper_wallet_signing_execution_untouched"] is True


def test_t007ay_postprocess_writes_required_outputs_and_partial_60m_gate(tmp_path: Path) -> None:
    import json

    from research.mtp_research.validation.t007ay_post_patch_pumpswap_fee_quote_proof import (
        run_t007ay_postprocess,
    )

    archive = tmp_path / "archive"
    output = tmp_path / "out"
    archive.mkdir()
    (archive / "pumpswap_swap_events.jsonl").write_text(
        json.dumps(_buy_minus_event()) + "\n" + json.dumps(_sell_buyback_event()) + "\n",
        encoding="utf-8",
    )
    (archive / "collector_summary.json").write_text(
        json.dumps(
            {
                "run_finalized": True,
                "raw_notifications": 2,
                "unique_births": 1,
                "admitted_births": 1,
                "queue_drops": 0,
                "rpc_failures": 0,
                "http_429_count": 0,
                "capacity_rejected": 0,
                "valuation_ladder_events_written": 0,
                "decision_time_safety_violations": 0,
                "source_duration_seconds": 600,
                "actual_duration_seconds": 600,
            }
        ),
        encoding="utf-8",
    )

    gate = run_t007ay_postprocess(archive_root=archive, output_dir=output)

    assert gate["fee_proof_label"] == "POST_PATCH_EVENT_FEE_PROOF_PASSED"
    assert gate["source_duration_quality_status"] == "complete"
    assert gate["validation_run_quality_label"] == "CLEAN_10M_SOURCE_DURATION_PASSED"
    assert gate["reserve_quote_label"] == "RESERVE_QUOTE_STILL_UNCONFIRMED"
    assert gate["readiness_label"] == "POST_MIGRATION_DEPTH_PARTIAL_60M_ALLOWED"
    assert gate["event_endpoint_pass_count"] == 2
    assert gate["event_endpoint_fail_count"] == 0
    assert (output / "summary.md").exists()
    assert (output / "fee_model_status.json").exists()
    assert (output / "pumpswap_swap_candidate_inventory.csv").exists()
    assert (output / "fee_formula_replay_validation.csv").exists()
    assert (output / "formula_variant_comparison.csv").exists()
    assert (output / "readiness_gate_after_t007ay.json").exists()


def test_t007ay_postprocess_no_swap_events_keeps_gate_unchanged(tmp_path: Path) -> None:
    import json

    from research.mtp_research.validation.t007ay_post_patch_pumpswap_fee_quote_proof import (
        run_t007ay_postprocess,
    )

    archive = tmp_path / "archive"
    output = tmp_path / "out"
    archive.mkdir()
    (archive / "collector_summary.json").write_text(json.dumps({"run_finalized": True}), encoding="utf-8")

    gate = run_t007ay_postprocess(archive_root=archive, output_dir=output)

    assert gate["fee_proof_label"] == "NO_PUMPSWAP_SWAP_EVENTS_CAPTURED"
    assert gate["reserve_quote_label"] == "RESERVE_QUOTE_STILL_UNCONFIRMED"
    assert gate["readiness_label"] == "NO_SWAP_CONTEXT_FOR_GATE_CHANGE"
    assert gate["two_hour_plus_blocked"] is True
    assert gate["valuation_ladder_suppressed"] is True


def test_t007ay_source_duration_quality_flags_partial_131s_run() -> None:
    from research.mtp_research.validation.t007ay_post_patch_pumpswap_fee_quote_proof import (
        evaluate_source_duration_quality,
    )

    quality = evaluate_source_duration_quality(
        requested_source_duration_seconds=600,
        actual_source_duration_seconds=131.11073303222656,
        websocket_keepalive_timeout_count=3,
        websocket_reconnect_count=0,
        websocket_closed_early=False,
    )

    assert quality["source_duration_quality_status"] == "partial"
    assert quality["source_ended_early"] is True
    assert quality["validation_run_quality_label"] == "RUN_QUALITY_PARTIAL"
    assert quality["source_duration_completion_ratio"] < 0.95
    assert quality["early_end_reason"] == "source_duration_below_95pct"


def test_t007ay_partial_source_duration_blocks_60m_even_when_fee_proof_passes(tmp_path: Path) -> None:
    import json

    from research.mtp_research.validation.t007ay_post_patch_pumpswap_fee_quote_proof import (
        run_t007ay_postprocess,
    )

    archive = tmp_path / "archive"
    output = tmp_path / "out"
    archive.mkdir()
    (archive / "pumpswap_swap_events.jsonl").write_text(
        json.dumps(_buy_minus_event()) + "\n" + json.dumps(_sell_buyback_event()) + "\n",
        encoding="utf-8",
    )
    (archive / "collector_summary.json").write_text(
        json.dumps(
            {
                "run_finalized": True,
                "raw_notifications": 3128,
                "unique_births": 133,
                "admitted_births": 110,
                "queue_drops": 0,
                "rpc_failures": 0,
                "http_429_count": 0,
                "capacity_rejected": 0,
                "valuation_ladder_events_written": 0,
                "decision_time_safety_violations": 0,
                "source_duration_seconds": 600,
                "actual_duration_seconds": 131.11073303222656,
                "websocket_closed_early": False,
                "websocket_keepalive_timeout_count": 5,
                "websocket_reconnect_count": 0,
            }
        ),
        encoding="utf-8",
    )

    gate = run_t007ay_postprocess(archive_root=archive, output_dir=output)

    assert gate["fee_model_status"] == "confirmed"
    assert gate["fee_proof_label"] == "POST_PATCH_EVENT_FEE_PROOF_PASSED_RUN_QUALITY_PARTIAL"
    assert gate["source_duration_quality_status"] == "partial"
    assert gate["validation_run_quality_label"] == "RUN_QUALITY_PARTIAL"
    assert gate["readiness_label"] == "FULL_THESIS_STILL_BLOCKED"
    assert gate["sixty_min_remains_blocked"] is True
    assert gate["valuation_ladder_suppressed"] is True
