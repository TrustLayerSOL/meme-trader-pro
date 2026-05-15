#!/usr/bin/env python3
"""
Apply approved wallet promotion/demotion decisions with backup and audit.

Default mode is dry-run. Use --apply to write changes.
"""

import argparse
import uuid
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.json_store import JsonFileLock, atomic_write_json, locked_update_json, read_json
from core.wallet_discovery import normalize_tracked_wallets
from core.wallet_lifecycle import build_wallet_lifecycle_report
from core.wallet_list_apply import apply_wallet_review_decisions


TRACKED_WALLETS = ROOT / "data" / "tracked_wallets.json"
PAPER_WATCH_WALLETS = ROOT / "data" / "paper_watch_wallets.json"
CANDIDATE_WALLETS = ROOT / "data" / "candidate_wallets.json"
WALLET_PERFORMANCE = ROOT / "data" / "wallet_performance.json"
BAD_WALLETS = ROOT / "data" / "bad_wallets.json"
REVIEW_DECISIONS = ROOT / "data" / "wallet_review_decisions.json"
CANDIDATE_AUDIT = ROOT / "data" / "wallet_candidate_audit.json"
AUDIT_FILE = ROOT / "data" / "wallet_list_update_audit.json"
ARCHIVE_DIR = ROOT / "data" / "archives"
APPLY_LOCK = ROOT / "data" / "wallet_review_apply.lock"


def utc_stamp(timestamp=None):
    timestamp = time.time() if timestamp is None else float(timestamp)
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def build_lifecycle_report():
    tracked = normalize_tracked_wallets(read_json(TRACKED_WALLETS, []))
    paper_watch = read_json(PAPER_WATCH_WALLETS, {"wallets": []})
    return build_wallet_lifecycle_report(
        tracked_wallets=tracked,
        paper_watch_wallets=paper_watch.get("wallets", []) if isinstance(paper_watch, dict) else [],
        candidate_report=read_json(CANDIDATE_WALLETS, {"candidates": []}),
        performance=read_json(WALLET_PERFORMANCE, {"wallets": {}}),
    )


def create_backup(paths, stamp):
    backup_dir = ARCHIVE_DIR / f"wallet_apply_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for path in paths:
        if path.exists():
            shutil.copy2(path, backup_dir / path.name)
    return backup_dir


def append_audit(audit_entry):
    def updater(current):
        if not isinstance(current, dict):
            current = {"updates": []}
        current.setdefault("updates", []).insert(0, audit_entry)
        current["updates"] = current["updates"][:500]
        return current

    locked_update_json(AUDIT_FILE, {"updates": []}, updater)


def run_apply(dry_run=True):
    with JsonFileLock(APPLY_LOCK):
        stamp = f"{utc_stamp()}_{uuid.uuid4().hex[:8]}"
        lifecycle = build_lifecycle_report()
        result = apply_wallet_review_decisions(
            tracked_wallets=read_json(TRACKED_WALLETS, []),
            paper_watch_wallets=read_json(PAPER_WATCH_WALLETS, {"wallets": []}),
            bad_wallets=read_json(BAD_WALLETS, []),
            review_decisions=read_json(REVIEW_DECISIONS, {"decisions": []}),
            lifecycle_report=lifecycle,
            candidate_audit=read_json(CANDIDATE_AUDIT, {"candidates": []}),
            applied_at=time.time(),
            dry_run=dry_run,
        )
        result["stamp"] = stamp

        if dry_run:
            return result

        backup_dir = create_backup([TRACKED_WALLETS, PAPER_WATCH_WALLETS, BAD_WALLETS, REVIEW_DECISIONS, CANDIDATE_AUDIT, AUDIT_FILE], stamp)
        atomic_write_json(TRACKED_WALLETS, result["tracked_wallets"])
        atomic_write_json(PAPER_WATCH_WALLETS, result["paper_watch_wallets"])
        atomic_write_json(BAD_WALLETS, result["bad_wallets"])

        audit_entry = dict(result["audit"])
        audit_entry["backup_dir"] = str(backup_dir.relative_to(ROOT))
        audit_entry["summary"] = result["summary"]
        atomic_write_json(backup_dir / "APPLY_SUMMARY.json", audit_entry)
        append_audit(audit_entry)
        result["backup_dir"] = str(backup_dir)
        return result


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Apply approved wallet promotion/demotion decisions.")
    parser.add_argument("--apply", action="store_true", help="Write approved changes. Without this, only dry-run.")
    parser.add_argument("--init-decisions", action="store_true", help="Create an empty decision file if missing.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.init_decisions and not REVIEW_DECISIONS.exists():
        atomic_write_json(REVIEW_DECISIONS, {
            "decisions": [],
            "notes": "Add approved decisions here. Example decision values: approve_promotion, approve_demotion.",
        })
        print(f"Created {REVIEW_DECISIONS}")

    result = run_apply(dry_run=not args.apply)
    mode = "DRY RUN" if result["dry_run"] else "APPLIED"
    print(f"{mode} wallet review apply")
    print(f"Promoted: {result['summary']['promoted']}")
    print(f"Demoted: {result['summary']['demoted']}")
    print(f"Skipped: {result['summary']['skipped']}")
    if result.get("backup_dir"):
        print(f"Backup: {result['backup_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
