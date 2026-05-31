"""Writers for offline rebuild timing profile reports."""

from __future__ import annotations

import json
from pathlib import Path

from research.mtp_research.pipeline.offline_rebuild_profile import OfflineRebuildProfile


DEFAULT_REPORT_DIR = Path("data/backtests/diagnostics/reports")


def write_profile_json(
    profile: OfflineRebuildProfile,
    output_dir: Path | str = DEFAULT_REPORT_DIR,
) -> Path:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{profile.profile_id}.json"
    path.write_text(json.dumps(profile.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_profile_markdown(
    profile: OfflineRebuildProfile,
    output_dir: Path | str = DEFAULT_REPORT_DIR,
) -> Path:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{profile.profile_id}.md"
    lines = [
        "# Offline Rebuild Profile",
        "",
        f"- Profile ID: `{profile.profile_id}`",
        f"- Created at: `{profile.created_at}`",
        f"- Total elapsed seconds: `{profile.total_elapsed_seconds}`",
        f"- Warning flags: `{profile.warning_flags}`",
        "",
        "| Step | Skipped | Input | Output | Seconds | Warnings |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for step in profile.steps:
        lines.append(
            "| "
            f"{step.step_name} | "
            f"{step.skipped} | "
            f"{step.input_count} | "
            f"{step.output_count} | "
            f"{step.elapsed_seconds} | "
            f"`{step.warning_flags}` |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
