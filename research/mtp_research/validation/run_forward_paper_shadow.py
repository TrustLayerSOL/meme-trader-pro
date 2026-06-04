"""CLI for initializing the disabled forward paper/shadow scaffold."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.forward_paper_shadow import initialize_forward_paper_shadow


def main() -> int:
    args = parse_args()
    result = initialize_forward_paper_shadow(
        data_root=Path(args.data_root).expanduser() if args.data_root else None,
        execute=args.execute,
    )
    print("## Forward Paper/Shadow Scaffold")
    print(f"execute={result.get('execute')}")
    print(f"enabled={result.get('enabled')}")
    print(f"readiness={result.get('readiness')}")
    print(f"config_path={result.get('config_path')}")
    print(f"decisions_path={result.get('decisions_path')}")
    print(f"status_path={result.get('status_path')}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize disabled forward paper/shadow scaffold.")
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
