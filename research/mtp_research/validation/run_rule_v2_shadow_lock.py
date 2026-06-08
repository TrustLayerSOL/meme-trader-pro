"""CLI for writing the locked Rule V2 paper-shadow config."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.rule_v2_shadow_lock import write_rule_v2_shadow_lock_artifacts


def main() -> int:
    args = parse_args()
    result = write_rule_v2_shadow_lock_artifacts(
        data_root=Path(args.data_root).expanduser() if args.data_root else None,
        repo_root=Path(args.repo_root).expanduser() if args.repo_root else None,
    )
    print("## Rule V2 Shadow Lock")
    print(f"locked={result.get('locked')}")
    print(f"mode={result.get('mode')}")
    print(f"variant_ids={result.get('variant_ids')}")
    print(f"shared_exit_rule_id={result.get('shared_exit_rule_id')}")
    print(f"current_rule_d_overwritten={result.get('current_rule_d_overwritten')}")
    print(f"output_root={result.get('output_root')}")
    print(f"daily_status_path={result.get('daily_status_path')}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write locked Rule V2 paper-shadow buy/sell config artifacts.")
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--repo-root", default=None)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
