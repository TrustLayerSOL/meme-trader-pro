from __future__ import annotations

import json
from pathlib import Path

from research.mtp_research.validation.t012_local_run_retention import apply_local_run_retention


def _write_run(root: Path, name: str, *, finalized: bool = True, payload: str = "x") -> Path:
    run = root / name
    run.mkdir(parents=True)
    (run / "collector_summary.json").write_text(
        json.dumps(
            {
                "run_id": name,
                "run_status": "finalized" if finalized else "running",
                "run_finalized": finalized,
            }
        ),
        encoding="utf-8",
    )
    (run / "payload.txt").write_text(payload, encoding="utf-8")
    return run


def test_retention_keeps_latest_three_and_links_archived_finalized_runs(tmp_path: Path) -> None:
    local = tmp_path / "local"
    archive = tmp_path / "orico"
    runs = [_write_run(local, f"run-{idx}", payload=str(idx)) for idx in range(5)]
    for idx, run in enumerate(runs):
        mtime = 1_700_000_000 + idx
        run.touch()
        for child in run.iterdir():
            child.touch()
        # Update directory mtime after child writes.
        run.touch()

    report = apply_local_run_retention(local, archive, keep_latest=3)

    assert report["retention_status"] == "complete"
    assert report["archived_count"] == 2
    assert sorted(item["run_name"] for item in report["archived_runs"]) == ["run-0", "run-1"]
    assert (archive / "run-0" / "payload.txt").read_text(encoding="utf-8") == "0"
    assert (archive / "run-1" / "payload.txt").read_text(encoding="utf-8") == "1"
    assert (local / "run-0").is_symlink()
    assert (local / "run-1").is_symlink()
    assert (local / "run-4").is_dir() and not (local / "run-4").is_symlink()


def test_retention_never_moves_active_or_unfinalized_runs(tmp_path: Path) -> None:
    local = tmp_path / "local"
    archive = tmp_path / "orico"
    finalized_old = _write_run(local, "run-finalized-old", finalized=True)
    active_old = _write_run(local, "run-active-old", finalized=False)
    for idx, run in enumerate([finalized_old, active_old]):
        run.touch()

    report = apply_local_run_retention(local, archive, keep_latest=0)

    assert report["archived_count"] == 1
    assert (archive / "run-finalized-old").exists()
    assert (local / "run-finalized-old").is_symlink()
    assert (local / "run-active-old").is_dir()
    assert report["skipped_by_reason"]["not_finalized_or_active"] == 1
