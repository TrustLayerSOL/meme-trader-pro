"""T012 local forward-run retention.

Keeps the newest local run folders available on the internal disk and moves
older finalized runs to cold storage. This module never touches active or
unfinalized runs and never enables trading, paper trading, signing, or sending.
"""

from __future__ import annotations

import json
import os
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STAGE = "T012_PRE_MIGRATION_PAPER_READY_INFRA"
DEFAULT_LOCAL_RETENTION_KEEP_LATEST = 1
DEFAULT_LOCAL_RETENTION_ARCHIVE_ROOT = Path(
    "/Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1"
)
GUARDRAILS: dict[str, Any] = {
    "stage": STAGE,
    "paper_trading_enabled": False,
    "live_trading_enabled": False,
    "buy_sell_signal_generated": False,
    "paper_trade_generated": False,
    "private_keys_signing_execution_added": False,
    "wallet_private_key_signing_execution_absent": True,
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def _run_is_finalized(path: Path) -> bool:
    summary = _read_json(path / "collector_summary.json")
    live_status = _read_json(path / "live_status.json")
    if str(summary.get("run_status") or live_status.get("run_status") or "").startswith("running"):
        return False
    if str(summary.get("runtime_phase") or live_status.get("runtime_phase") or "") in {"source", "drain", "finalization"}:
        return False
    return bool(
        summary.get("run_finalized") is True
        or str(summary.get("run_status") or "").startswith("finalized")
        or str(live_status.get("run_status") or "").startswith("finalized")
    )


def _folder_stats(path: Path) -> dict[str, int]:
    files = 0
    symlinks = 0
    bytes_total = 0
    for item in path.rglob("*"):
        if item.name.startswith("._"):
            continue
        if item.is_symlink():
            symlinks += 1
        elif item.is_file():
            files += 1
            bytes_total += int(item.stat().st_size)
    return {"files": files, "symlinks": symlinks, "bytes": bytes_total}


def _copytree_verified(source: Path, destination: Path) -> dict[str, Any]:
    if destination.exists():
        if not (destination / "collector_summary.json").exists():
            return {"status": "failed", "reason": "destination_exists_without_collector_summary"}
        source_stats = _folder_stats(source)
        dest_stats = _folder_stats(destination)
        if source_stats == dest_stats:
            return {"status": "already_archived", **dest_stats}
        shutil.rmtree(destination, ignore_errors=True)
        if destination.exists():
            return {"status": "failed", "reason": "destination_mismatch_cleanup_failed", "destination_stats": dest_stats}
    shutil.copytree(source, destination, symlinks=True)
    source_stats = _folder_stats(source)
    dest_stats = _folder_stats(destination)
    if source_stats != dest_stats:
        return {
            "status": "failed",
            "reason": "copy_verification_mismatch",
            "source_stats": source_stats,
            "destination_stats": dest_stats,
        }
    return {"status": "copied", **dest_stats}


def _replace_local_with_symlink(source: Path, destination: Path) -> None:
    removed = source.with_name(source.name + f".retention_remove_{os.getpid()}")
    source.rename(removed)
    try:
        os.symlink(destination, source, target_is_directory=True)
        shutil.rmtree(removed)
    except Exception:
        if source.exists() or source.is_symlink():
            try:
                source.unlink()
            except Exception:
                pass
        removed.rename(source)
        raise


def apply_local_run_retention(
    local_root: Path | str,
    archive_root: Path | str | None = None,
    *,
    keep_latest: int = DEFAULT_LOCAL_RETENTION_KEEP_LATEST,
) -> dict[str, Any]:
    local = Path(local_root)
    archive = Path(archive_root) if archive_root is not None else DEFAULT_LOCAL_RETENTION_ARCHIVE_ROOT
    report: dict[str, Any] = {
        **GUARDRAILS,
        "retention_policy": "keep_latest_local_archive_older_finalized_runs",
        "local_root": str(local),
        "archive_root": str(archive),
        "keep_latest": max(0, int(keep_latest)),
        "retention_status": "not_run",
        "archived_count": 0,
        "archived_runs": [],
        "kept_local_runs": [],
        "skipped_runs": [],
        "skipped_by_reason": {},
        "errors": [],
        "ran_at": datetime.now(timezone.utc).isoformat(),
    }
    if not local.exists() or not local.is_dir():
        report["retention_status"] = "skipped"
        report["errors"].append(f"local_root_missing_or_not_directory:{local}")
        return report
    try:
        archive.mkdir(parents=True, exist_ok=True)
        probe = archive / ".retention_write_test.tmp"
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except Exception as exc:
        report["retention_status"] = "skipped"
        report["errors"].append(f"archive_root_not_writable:{archive}:{exc}")
        return report

    run_dirs = [
        path
        for path in local.iterdir()
        if path.is_dir() and not path.is_symlink() and path.name not in {".", ".."}
    ]
    run_dirs.sort(key=lambda item: (item.stat().st_mtime, item.name), reverse=True)
    keep_set = {path.name for path in run_dirs[: report["keep_latest"]]}
    skipped = Counter()
    for run_dir in run_dirs:
        if run_dir.name in keep_set:
            report["kept_local_runs"].append(run_dir.name)
            continue
        if not _run_is_finalized(run_dir):
            skipped["not_finalized_or_active"] += 1
            report["skipped_runs"].append({"run_name": run_dir.name, "reason": "not_finalized_or_active"})
            continue
        destination = archive / run_dir.name
        copy_result = _copytree_verified(run_dir, destination)
        if copy_result.get("status") not in {"copied", "already_archived"}:
            skipped[str(copy_result.get("reason") or "archive_copy_failed")] += 1
            report["skipped_runs"].append({"run_name": run_dir.name, "reason": copy_result.get("reason"), **copy_result})
            continue
        try:
            manifest = {
                **GUARDRAILS,
                "run_name": run_dir.name,
                "local_pointer_path": str(run_dir),
                "archive_path": str(destination),
                "retention_status": "archived_to_cold_storage",
                "archived_at": datetime.now(timezone.utc).isoformat(),
                "copy_status": copy_result.get("status"),
                "files": copy_result.get("files"),
                "bytes": copy_result.get("bytes"),
            }
            _write_json(destination / "local_retention_manifest.json", manifest)
            _replace_local_with_symlink(run_dir, destination)
            report["archived_count"] += 1
            report["archived_runs"].append(manifest)
        except Exception as exc:
            skipped["local_symlink_failed"] += 1
            report["skipped_runs"].append({"run_name": run_dir.name, "reason": "local_symlink_failed", "error": str(exc)})
    report["skipped_by_reason"] = dict(skipped)
    report["retention_status"] = "complete" if not report["errors"] else "partial"
    try:
        _write_json(local / "local_retention_report_latest.json", report)
    except Exception as exc:
        report["errors"].append(f"retention_report_write_failed:{exc}")
        report["retention_status"] = "partial"
    return report
