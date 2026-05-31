from pathlib import Path

from research.mtp_research.pipeline.offline_rebuild_profile import (
    OfflineRebuildProfile,
    OfflineRebuildStepProfile,
    utc_now_iso,
)
from research.mtp_research.pipeline.offline_rebuild_profile_report import (
    write_profile_json,
    write_profile_markdown,
)


def test_offline_rebuild_profile_report_writes_markdown_and_json(tmp_path: Path) -> None:
    profile = OfflineRebuildProfile.create({"mode": "test"})
    step = OfflineRebuildStepProfile(
        step_name="clean_outcomes",
        started_at=utc_now_iso(),
        input_count=10,
    )
    step.finish(output_count=20)
    profile.steps.append(step)
    profile.finish()

    markdown_path = write_profile_markdown(profile, tmp_path)
    json_path = write_profile_json(profile, tmp_path)

    assert markdown_path.exists()
    assert json_path.exists()
    assert "Offline Rebuild Profile" in markdown_path.read_text(encoding="utf-8")
    assert profile.profile_id in json_path.read_text(encoding="utf-8")
