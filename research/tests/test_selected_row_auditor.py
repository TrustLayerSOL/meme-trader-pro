from research.mtp_research.backtest.rule_backtest_models import RuleCondition, RuleDefinition
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.selected_row_auditor import SelectedRowAuditor


def _row(
    row_id: str,
    token_mint: str = "mint-a",
    forward_return: float | None = 0.1,
    entry_price_source: str | None = "exact_snapshot",
    snapshot_ts: int = 1_000,
    entry_price_ts: int | None = 1_000,
    max_runup: float | None = 0.2,
) -> ResearchDatasetRow:
    return ResearchDatasetRow(
        row_id=row_id,
        snapshot_id=f"snapshot-{row_id}",
        outcome_id=f"outcome-{row_id}",
        token_mint=token_mint,
        snapshot_ts=snapshot_ts,
        window_name="1m",
        window_seconds=60,
        horizon_name="15m",
        horizon_seconds=900,
        possible_buy_count=2,
        possible_sell_count=0,
        unique_actor_count=3,
        confidence_weighted_net_flow=1.0,
        buy_sell_imbalance=0.8,
        avg_event_confidence=0.8,
        max_event_confidence=0.9,
        entry_price=1.0,
        entry_price_ts=entry_price_ts,
        entry_price_source=entry_price_source,
        end_price=1.1 if forward_return is not None else None,
        end_price_ts=1_900,
        forward_return=forward_return,
        max_runup=max_runup,
        max_drawdown=-0.1,
        label_quality="sparse",
    )


def test_selected_row_auditor_uses_rule_backtester_conditions() -> None:
    rule = RuleDefinition(
        rule_id="custom_rule",
        name="Custom Rule",
        conditions=[RuleCondition("possible_buy_count", "gte", 2)],
    )

    audit = SelectedRowAuditor().audit_rule([_row("a")], rule)

    assert audit.selected_count == 1
    assert audit.records[0].row_id == "a"


def test_row_warnings_detect_fallback_stale_and_extreme_return() -> None:
    record = SelectedRowAuditor().row_to_audit_record(
        _row(
            "a",
            forward_return=1.4,
            entry_price_source="nearest_research_fallback",
            snapshot_ts=1_000,
            entry_price_ts=500,
        ),
        "custom_rule",
        cost_drag=0.045,
        stale_entry_threshold_sec=300,
        outlier_return_threshold=1.0,
    )

    assert "nearest_research_fallback_entry" in record.warning_flags
    assert "stale_entry_price" in record.warning_flags
    assert "extreme_forward_return" in record.warning_flags


def test_rule_warnings_detect_outlier_negative_median_and_token_concentration() -> None:
    rows = [
        _row("win", token_mint="mint-a", forward_return=5.0),
        _row("loss-1", token_mint="mint-a", forward_return=-0.1),
        _row("loss-2", token_mint="mint-a", forward_return=-0.2),
    ]
    rule = RuleDefinition(
        rule_id="custom_rule",
        name="Custom Rule",
        conditions=[RuleCondition("possible_buy_count", "gte", 2)],
    )

    audit = SelectedRowAuditor().audit_rule(rows, rule, cost_drag=0.0)

    assert "outlier_dominated_average" in audit.warning_flags
    assert "low_median_negative" in audit.warning_flags
    assert "token_concentration" in audit.warning_flags


def test_report_recommendation_prioritizes_outlier_review() -> None:
    rule = RuleDefinition(
        rule_id="custom_rule",
        name="Custom Rule",
        conditions=[RuleCondition("possible_buy_count", "gte", 2)],
    )
    report = SelectedRowAuditor().audit_rules(
        [_row("win", forward_return=5.0), _row("loss", forward_return=-0.1)],
        [rule],
        ["custom_rule"],
        cost_drag=0.0,
    )

    assert report.recommended_next_action == "inspect_price_outliers_before_scaling"
