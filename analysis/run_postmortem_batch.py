"""Batch-generate Phase A structured post-mortems from data/paper_trades.json."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional


def main(argv: Optional[list] = None) -> int:
    from analysis.trade_postmortem import (
        DEFAULT_POSTMORTEM_PATH,
        append_postmortem_jsonl,
        build_postmortem_record,
        iter_closed_trades,
        load_postmortem_ids,
        snapshot_from_paper_file,
    )

    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(description="Append structured JSONL post-mortems for closed paper trades.")
    parser.add_argument(
        "--paper",
        type=Path,
        default=Path("data/paper_trades.json"),
        help="Paper trades JSON (gitignored locally; operator supplies path)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_POSTMORTEM_PATH,
        help="Append-only JSONL target",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-write fingerprints even when already logged (not usual)",
    )

    ns = parser.parse_args(argv)

    if not ns.paper.exists():
        sys.stderr.write("paper trades file not found: {}\n".format(ns.paper))
        return 2

    blob = snapshot_from_paper_file(ns.paper)
    existing = load_postmortem_ids(ns.output) if not ns.force else set()

    appended = 0
    skipped = 0

    for trade in iter_closed_trades(blob):
        rec = build_postmortem_record(trade)
        pid = rec.get("postmortem_id")
        if pid in existing:
            skipped += 1
            continue
        append_postmortem_jsonl(rec, ns.output)
        if pid:
            existing.add(pid)
        appended += 1

    print(
        "postmortem batch: appended={appended}, skipped_duplicate={skipped}, output={path}".format(
            appended=appended,
            skipped=skipped,
            path=ns.output,
        )
    )
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
