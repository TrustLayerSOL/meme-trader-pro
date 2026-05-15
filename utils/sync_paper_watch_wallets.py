#!/usr/bin/env python3
"""
Build the paper-watch wallet lane from reviewed candidate wallets.

This writes data/paper_watch_wallets.json only. It does not edit the trusted
tracked-wallet list and does not enable live execution.
"""

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.json_store import atomic_write_json, read_json
from core.wallet_lifecycle import sync_paper_watch_wallets


CANDIDATE_WALLETS = ROOT / "data" / "candidate_wallets.json"
PAPER_WATCH_WALLETS = ROOT / "data" / "paper_watch_wallets.json"
WALLET_PERFORMANCE = ROOT / "data" / "wallet_performance.json"
BAD_WALLETS = ROOT / "data" / "bad_wallets.json"


def build_report():
    return sync_paper_watch_wallets(
        current_wallets=read_json(PAPER_WATCH_WALLETS, {"wallets": []}).get("wallets", []),
        candidate_report=read_json(CANDIDATE_WALLETS, {"candidates": []}),
        performance=read_json(WALLET_PERFORMANCE, {"wallets": {}}),
        bad_wallets=read_json(BAD_WALLETS, []),
    )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Sync paper-watch wallets from candidate review decisions.")
    parser.add_argument("--write", action="store_true", help=f"Write {PAPER_WATCH_WALLETS.relative_to(ROOT)}.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    report = build_report()
    if args.write:
        atomic_write_json(PAPER_WATCH_WALLETS, report)
        print(f"Wrote {PAPER_WATCH_WALLETS}")
    else:
        print(json.dumps({
            "mode": report["mode"],
            "summary": report["summary"],
            "wallets": report["wallets"][:10],
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
