"""CLI for T012 pre-migration paper-readiness audits."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research.mtp_research.validation.t012_paper_readiness_gate import run_t012_paper_readiness_audit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run T012 pre-migration paper-readiness audit.")
    parser.add_argument("--run-root", required=True)
    args = parser.parse_args(argv)
    report = run_t012_paper_readiness_audit(Path(args.run_root))
    print(json.dumps({
        "gate_passed": report.get("gate_passed"),
        "paper_ready_status": report.get("paper_ready_status"),
        "blocking_reasons": report.get("blocking_reasons"),
        "paper_readiness_audit_json_path": report.get("paper_readiness_audit_json_path"),
        "paper_readiness_audit_md_path": report.get("paper_readiness_audit_md_path"),
    }, indent=2, sort_keys=True))
    return 0 if report.get("gate_passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
