#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.env_loader import load_env
from core.json_store import atomic_write_json
from core.rpc_provider import HeliusRpcProvider
from wallets.forward_free_rpc_provider_rotation import build_forward_free_rpc_provider_rotation_report


DEFAULT_REPORT = ROOT / "data" / "reports" / "forward_testing" / "forward_free_rpc_provider_rotation_report.json"


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def write_forward_free_rpc_provider_rotation_report(
    *,
    out_path: Path | str = DEFAULT_REPORT,
    free_rpc_urls: str | None = None,
    timeout: int = 8,
    generated_at: float | None = None,
    probe: Callable[[HeliusRpcProvider], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    load_env()
    report = build_forward_free_rpc_provider_rotation_report(
        free_rpc_urls=free_rpc_urls,
        probe=probe,
        generated_at=generated_at,
        timeout=timeout,
    )
    out = Path(out_path)
    atomic_write_json(out, report)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(report["generated_at"]))
    snapshot_path = out.parent / f"forward_free_rpc_provider_rotation_{stamp}.json"
    atomic_write_json(snapshot_path, report)
    report["report_path"] = display_path(out)
    report["snapshot_path"] = display_path(snapshot_path)
    atomic_write_json(out, report)
    atomic_write_json(snapshot_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Rank public/free Solana RPC endpoints without changing collection settings.")
    parser.add_argument("--free-rpc-urls", help="Comma-separated public/free Solana RPC URLs to test.")
    parser.add_argument("--timeout", type=int, default=8)
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    report = write_forward_free_rpc_provider_rotation_report(
        out_path=args.out,
        free_rpc_urls=args.free_rpc_urls,
        timeout=args.timeout,
    )
    print(json.dumps({
        "report_path": report["report_path"],
        "snapshot_path": report["snapshot_path"],
        "recommendation": report["recommendation"],
        "providers_tested": report["providers_tested"],
        "healthy_providers": report["healthy_providers"],
        "degraded_providers": report["degraded_providers"],
        "offline_providers": report["offline_providers"],
        "recommended_free_rpc_safe_urls": report["recommended_free_rpc_safe_urls"],
        "blockers": report["blockers"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
