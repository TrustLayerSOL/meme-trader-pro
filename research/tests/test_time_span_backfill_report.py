from research.mtp_research.pipeline.time_span_backfill_models import (
    TimeSpanBackfillPlan,
    TimeSpanBackfillPlanItem,
    TokenEvidenceCoverage,
)
from research.mtp_research.pipeline.time_span_backfill_report import (
    PLAN_WARNING,
    plan_to_dict,
    write_plan_json,
    write_plan_markdown,
)


def _plan() -> TimeSpanBackfillPlan:
    return TimeSpanBackfillPlan(
        plan_id="plan-1",
        created_at="2026-05-31T00:00:00+00:00",
        candidate_count=1,
        real_candidate_count=1,
        coverage_items=[
            TokenEvidenceCoverage(
                token_mint="token-1",
                pool_address="pool-1",
                liquidity_usd=20000,
                raw_tx_count=0,
                needs_backfill=True,
                warning_flags=["no_raw_transactions"],
            )
        ],
        plan_items=[
            TimeSpanBackfillPlanItem(
                token_mint="token-1",
                pool_address="pool-1",
                target_address="pool-1",
                role="pool",
                reason="no_raw_transactions",
                recommended_signature_limit=75,
                recommended_transaction_limit=75,
            )
        ],
        recommended_next_command="run --execute",
    )


def test_time_span_plan_report_writes_markdown_and_json(tmp_path) -> None:
    plan = _plan()
    markdown_path = write_plan_markdown(plan, tmp_path / "plan.md")
    json_path = write_plan_json(plan, tmp_path / "plan.json")

    assert PLAN_WARNING in markdown_path.read_text(encoding="utf-8")
    assert plan_to_dict(plan)["warning"] == PLAN_WARNING
    assert '"plan_id": "plan-1"' in json_path.read_text(encoding="utf-8")
