#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wallets.forward_merged_calibration_recommendations import build_forward_merged_calibration_recommendations  # noqa: E402


DEFAULT_MERGED_SCORECARD = ROOT / "data" / "reports" / "forward_testing" / "forward_merged_calibration_scorecard.json"
DEFAULT_REPORT = ROOT / "data" / "reports" / "forward_testing" / "forward_merged_calibration_recommendations.json"
DEFAULT_MARKDOWN = ROOT / "data" / "reports" / "forward_testing" / "forward_merged_calibration_recommendations.md"


def read_json(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        parsed = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def relative_path(path: Path | str) -> str:
    p = Path(path)
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    merged = report.get("merged_scorecard_summary") if isinstance(report.get("merged_scorecard_summary"), dict) else {}
    lines = [
        "# MemeTraderPro Merged Forward Calibration Recommendations",
        "",
        "Conservative review-only recommendations from original plus repaired forward outcomes.",
        "",
        "## Summary",
        "",
        f"- Wallets: {summary.get('wallets', 0)}",
        f"- Review signal wallets: {summary.get('review_forward_signal_wallets', 0)}",
        f"- Risk review wallets: {summary.get('risk_review_wallets', 0)}",
        f"- Flat-only hold wallets: {summary.get('flat_only_hold_wallets', 0)}",
        f"- Fix context wallets: {summary.get('fix_context_wallets', 0)}",
        f"- Promotions allowed: {summary.get('promotions_allowed', 0)}",
        f"- Repaired records considered: {merged.get('repaired_records', 0)}",
        "",
        "## Recommendations",
        "",
        "| Wallet | Action | Known 15m | Runner | Rug | Flat | Blocked |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in report.get("recommendations") or []:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"| {row.get('wallet')} | {row.get('recommendation_action')} | {row.get('known_15m')} | "
            f"{row.get('runner_15m')} | {row.get('rug_15m')} | {row.get('flat_15m')} | "
            f"{row.get('blocked_records')} |"
        )
    lines.extend(
        [
            "",
            "Safety:",
            "- Review-only output.",
            "- Review signal is not promotion permission.",
            "- Live execution remains locked.",
            "- Wallet trust and wallet lists are not mutated.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_forward_merged_calibration_recommendations(
    *,
    merged_scorecard_path: Path | str = DEFAULT_MERGED_SCORECARD,
    report_path: Path | str = DEFAULT_REPORT,
    markdown_path: Path | str = DEFAULT_MARKDOWN,
    generated_at: float | None = None,
) -> dict[str, Any]:
    merged_scorecard_path = Path(merged_scorecard_path)
    report_path = Path(report_path)
    markdown_path = Path(markdown_path)
    report = build_forward_merged_calibration_recommendations(
        read_json(merged_scorecard_path),
        generated_at=generated_at,
    )
    report["input_paths"] = {"forward_merged_calibration_scorecard": relative_path(merged_scorecard_path)}
    report["output_paths"] = {"report": relative_path(report_path), "markdown": relative_path(markdown_path)}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build conservative merged forward calibration recommendations.")
    parser.add_argument("--merged-scorecard", type=Path, default=DEFAULT_MERGED_SCORECARD)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--markdown-path", type=Path, default=DEFAULT_MARKDOWN)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_forward_merged_calibration_recommendations(
        merged_scorecard_path=args.merged_scorecard,
        report_path=args.report_path,
        markdown_path=args.markdown_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
