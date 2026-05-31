import json
from pathlib import Path

from research.mtp_research.pipeline.evidence_audit_models import EvidenceStoreCount
from research.mtp_research.pipeline.evidence_auditor import EvidenceAuditor


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row))
            f.write("\n")


def test_count_jsonl_handles_missing_file(tmp_path: Path) -> None:
    count = EvidenceAuditor().count_jsonl(tmp_path / "missing.jsonl")

    assert count.exists is False
    assert count.row_count == 0
    assert "missing_file" in count.warning_flags


def test_count_jsonl_counts_rows(tmp_path: Path) -> None:
    path = tmp_path / "rows.jsonl"
    _write_jsonl(path, [{"a": 1}, {"a": 2}])

    count = EvidenceAuditor().count_jsonl(path)

    assert count.exists is True
    assert count.row_count == 2
    assert count.file_size_bytes > 0


def test_count_jsonl_handles_malformed_lines_with_warning(tmp_path: Path) -> None:
    path = tmp_path / "rows.jsonl"
    path.write_text('{"a": 1}\nnot-json\n', encoding="utf-8")

    count = EvidenceAuditor().count_jsonl(path)

    assert count.row_count == 1
    assert "malformed_jsonl_lines" in count.warning_flags


def test_audit_target_quality_flags_target_and_candidate_gaps() -> None:
    candidates = [
        {
            "token_mint": "mint-1",
            "pool_address": None,
            "creator_wallet": None,
            "metadata_json": {"is_mock": True},
        },
        {
            "token_mint": "mint-2",
            "metadata_json": {"example_only": True},
        },
    ]
    targets = [
        {"role": "mint", "address": "mint-1", "token_mint": "mint-1"},
        {"role": "mint", "address": "mint-2", "token_mint": "mint-2"},
    ]

    summary = EvidenceAuditor().audit_target_quality(candidates, targets)

    assert summary.role_counts == {"mint": 2}
    assert summary.targets_with_token_mint == 2
    assert "mint_only_targets" in summary.warning_flags
    assert "missing_pool_addresses" in summary.warning_flags
    assert "missing_creator_wallets" in summary.warning_flags
    assert "low_targets_per_candidate" in summary.warning_flags
    assert "mock_candidates_present" in summary.warning_flags


def test_count_event_types_works() -> None:
    counts = EvidenceAuditor().count_event_types(
        [{"event_type": "possible_buy"}, {"event_type": "possible_buy"}, {"event_type": "observed"}]
    )

    assert counts == {"observed": 1, "possible_buy": 2}


def test_count_label_quality_works() -> None:
    counts = EvidenceAuditor().count_label_quality(
        [{"label_quality": "valid"}, {"quality": "stale"}],
        [{"label_quality": "joined"}, {"outcome_label_quality": "missing"}],
    )

    assert counts == {"joined": 1, "missing": 1, "stale": 1, "valid": 1}


def test_count_thesis_recommendations_works() -> None:
    counts = EvidenceAuditor().count_thesis_recommendations(
        [{"recommended_status": "needs_more_data"}, {"recommended_status": "rejected"}]
    )

    assert counts == {"needs_more_data": 1, "rejected": 1}


def test_calculate_dropoffs_calculates_retained_ratio_and_flags() -> None:
    counts = [
        EvidenceStoreCount("candidate_registry", "candidates", True, 20),
        EvidenceStoreCount("backfill_targets_plan", "targets", True, 20),
        EvidenceStoreCount("raw_transactions", "raw", True, 0),
        EvidenceStoreCount("normalized_events", "events", True, 2),
    ]

    dropoffs = EvidenceAuditor().calculate_dropoffs(counts)

    assert dropoffs[0].retained_ratio == 1.0
    assert dropoffs[1].dropped_count == 20
    assert "empty_to_stage" in dropoffs[1].warning_flags
    assert "large_dropoff" in dropoffs[1].warning_flags
    assert "missing_source_stage" in dropoffs[2].warning_flags


def test_infer_bottlenecks() -> None:
    auditor = EvidenceAuditor()

    assert auditor.infer_bottleneck(auditor.build_report_from_counts({"candidate_registry": 0})) == "candidate_registry_empty"
    assert auditor.infer_bottleneck(
        auditor.build_report_from_counts({"candidate_registry": 1, "backfill_targets_plan": 0})
    ) == "no_backfill_targets"
    assert auditor.infer_bottleneck(
        auditor.build_report_from_counts(
            {"candidate_registry": 1, "backfill_targets_plan": 1, "raw_transactions": 0},
            target_warnings=["mint_only_targets"],
        )
    ) == "low_value_backfill_targets"
    assert auditor.infer_bottleneck(
        auditor.build_report_from_counts({"candidate_registry": 1, "backfill_targets_plan": 1, "raw_transactions": 0})
    ) == "no_raw_transactions"
    assert auditor.infer_bottleneck(
        auditor.build_report_from_counts(
            {"candidate_registry": 1, "backfill_targets_plan": 1, "raw_transactions": 1, "normalized_events": 0}
        )
    ) == "parser_coverage"
    assert auditor.infer_bottleneck(
        auditor.build_report_from_counts(
            {
                "candidate_registry": 1,
                "backfill_targets_plan": 1,
                "raw_transactions": 1,
                "normalized_events": 1,
                "feature_snapshots": 0,
            },
            event_type_counts={"transaction_observed": 1},
        )
    ) == "trade_event_inference"
    assert auditor.infer_bottleneck(
        auditor.build_report_from_counts(
            {
                "candidate_registry": 1,
                "backfill_targets_plan": 1,
                "raw_transactions": 1,
                "normalized_events": 1,
                "feature_snapshots": 1,
                "outcome_labels": 0,
            },
            event_type_counts={"possible_buy": 1},
        )
    ) == "outcome_labeling_or_price_proxy"
    assert auditor.infer_bottleneck(
        auditor.build_report_from_counts(
            {
                "candidate_registry": 1,
                "backfill_targets_plan": 1,
                "raw_transactions": 1,
                "normalized_events": 1,
                "feature_snapshots": 1,
                "outcome_labels": 1,
                "research_dataset": 1,
                "walk_forward_results": 1,
                "thesis_decisions": 1,
            },
            event_type_counts={"possible_buy": 1},
            thesis_counts={"needs_more_data": 2},
        )
    ) == "insufficient_test_evidence"


def test_recommend_next_actions_returns_useful_actions() -> None:
    auditor = EvidenceAuditor()
    report = auditor.build_report_from_counts(
        {"candidate_registry": 1, "backfill_targets_plan": 1, "raw_transactions": 0},
        target_warnings=["mint_only_targets"],
    )
    report.bottleneck_stage = "low_value_backfill_targets"

    actions = auditor.recommend_next_actions(report)

    assert any("pool_address" in action for action in actions)
    assert any("creator_wallet" in action for action in actions)
