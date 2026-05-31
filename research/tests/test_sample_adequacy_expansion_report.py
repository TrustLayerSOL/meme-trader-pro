from pathlib import Path

from research.mtp_research.pipeline.sample_adequacy_expansion_models import (
    SampleAdequacyExpansionPlan,
)
from research.mtp_research.pipeline.sample_adequacy_expansion_report import (
    PLAN_WARNING,
    write_expansion_plan_json,
    write_expansion_plan_markdown,
)
from research.mtp_research.pipeline.time_span_backfill_models import TimeSpanBackfillPlan
from research.mtp_research.validation.thesis_models import SampleAdequacyReport


def _plan() -> SampleAdequacyExpansionPlan:
    return SampleAdequacyExpansionPlan(
        plan_id="plan-1",
        created_at="2026-05-31T00:00:00+00:00",
        sample_adequacy=SampleAdequacyReport(
            real_token_count=3,
            time_span_seconds=8040,
            valid_test_fold_count=10,
            total_test_selected_count=100,
            adequate_for_rejection=False,
            adequate_for_promotion=False,
            recommended_data_expansion="add_more_real_candidates_and_expand_time_span",
        ),
        time_span_plan=TimeSpanBackfillPlan(
            plan_id="time-plan-1",
            created_at="2026-05-31T00:00:00+00:00",
        ),
        recommended_next_action="add_more_real_candidates_and_expand_time_span",
    )


def test_expansion_report_writes_markdown_and_json(tmp_path: Path) -> None:
    markdown_path = write_expansion_plan_markdown(_plan(), tmp_path / "plan.md")
    json_path = write_expansion_plan_json(_plan(), tmp_path / "plan.json")

    assert markdown_path.exists()
    assert json_path.exists()
    assert PLAN_WARNING in markdown_path.read_text(encoding="utf-8")
    assert "add_more_real_candidates_and_expand_time_span" in json_path.read_text(encoding="utf-8")
