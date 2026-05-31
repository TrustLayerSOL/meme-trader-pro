"""CLI for offline evidence audit reports."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.pipeline.evidence_audit_report import (
    write_report_json,
    write_report_markdown,
)
from research.mtp_research.pipeline.evidence_auditor import EvidenceAuditor


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit local evidence population artifacts.")
    parser.add_argument("--output-dir", default="data/backtests/reports")
    args = parser.parse_args()

    report = EvidenceAuditor().build_report()
    output_dir = Path(args.output_dir)
    markdown_path = write_report_markdown(report, output_dir / f"{report.report_id}.md")
    json_path = write_report_json(report, output_dir / f"{report.report_id}.json")

    print(f"bottleneck_stage={report.bottleneck_stage}")
    print(f"top_warnings={report.top_warnings}")
    print(f"recommended_next_actions={report.recommended_next_actions}")
    print(f"markdown_path={markdown_path}")
    print(f"json_path={json_path}")
    print("network_calls=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
