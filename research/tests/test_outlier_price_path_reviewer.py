from research.mtp_research.backtest.rule_backtest_models import RuleCondition, RuleDefinition
from research.mtp_research.ingestion.normalization_models import NormalizedEvent
from research.mtp_research.validation.outlier_price_path_reviewer import OutlierPricePathReviewer
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow


def _row(
    row_id: str,
    source: str = "exact_snapshot",
    entry: float | None = 1.0,
    end: float | None = 2.2,
    forward_return: float | None = 1.2,
) -> ResearchDatasetRow:
    return ResearchDatasetRow(
        row_id=row_id,
        snapshot_id=f"snapshot-{row_id}",
        outcome_id=f"outcome-{row_id}",
        token_mint="mint-a",
        snapshot_ts=1_000,
        window_name="1m",
        window_seconds=60,
        horizon_name="15m",
        horizon_seconds=900,
        possible_buy_count=2,
        unique_actor_count=3,
        confidence_weighted_net_flow=1.0,
        buy_sell_imbalance=0.8,
        entry_price=entry,
        entry_price_ts=1_000,
        entry_price_source=source,
        end_price=end,
        end_price_ts=1_900,
        forward_return=forward_return,
        max_runup=1.3,
        max_drawdown=-0.1,
        label_quality="sparse",
    )


def _event(event_id: str, ts: int, price: float) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=event_id,
        signature=f"sig-{event_id}",
        slot=None,
        block_time=ts,
        event_type="trade",
        token_mint="mint-a",
        actor="actor-a",
        side="buy",
        base_qty=1.0,
        quote_qty=price,
        price_quote=price,
        metadata_json={"confidence": 0.9},
    )


def _rule() -> RuleDefinition:
    return RuleDefinition(
        rule_id="buy_imbalance_basic",
        name="Buy Imbalance Basic",
        conditions=[RuleCondition("buy_sell_imbalance", "gte", 0.5)],
    )


def test_reviewer_selects_outlier_rows_matching_rule_conditions() -> None:
    rows = [_row("selected"), _row("not-outlier", forward_return=0.1)]

    selected = OutlierPricePathReviewer().select_outlier_rows(
        rows,
        [_rule()],
        ["buy_imbalance_basic"],
        return_threshold=1.0,
    )

    assert [(rule_id, row.row_id) for rule_id, row in selected] == [
        ("buy_imbalance_basic", "selected")
    ]


def test_price_path_builds_local_points_around_snapshot() -> None:
    points = OutlierPricePathReviewer().build_price_path(
        "mint-a",
        1_000,
        900,
        [_event("before", 950, 1.0), _event("after", 1_010, 1.1), _event("late", 2_500, 2.0)],
        pre_window_seconds=100,
    )

    assert [point.event_id for point in points] == ["before", "after"]
    assert points[0].entry_distance_sec == 50


def test_classification_detects_plausible_fallback_isolated_suspicious_and_unusable() -> None:
    reviewer = OutlierPricePathReviewer()
    plausible = reviewer.review_row(
        "buy_imbalance_basic",
        _row("plausible"),
        [_event("a", 995, 1.0), _event("b", 1_100, 1.5), _event("c", 1_500, 2.0), _event("d", 1_900, 2.2)],
    )
    assert plausible.outlier_classification == "plausible_price_path"

    fallback = reviewer.review_row("buy_imbalance_basic", _row("fallback", source="nearest_research_fallback"), [])
    assert fallback.outlier_classification == "fallback_dependent"

    isolated = reviewer.review_row("buy_imbalance_basic", _row("isolated"), [_event("only", 1_800, 2.2)])
    assert isolated.outlier_classification == "isolated_price_print"

    suspicious = reviewer.review_row(
        "buy_imbalance_basic",
        _row("jump", end=50.0, forward_return=49.0),
        [_event("a", 995, 1.0), _event("b", 1_800, 50.0)],
    )
    assert suspicious.outlier_classification in {"suspicious_price_jump", "isolated_price_print"}

    unusable = reviewer.review_row("buy_imbalance_basic", _row("bad", entry=None), [])
    assert unusable.outlier_classification == "unusable_for_validation"
