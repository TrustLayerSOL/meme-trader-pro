"""CLI for robust return summaries of default exploratory rules."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from research.mtp_research.backtest.rule_library import default_rule_library
from research.mtp_research.backtest.rule_backtester import RuleBacktester
from research.mtp_research.pipeline.real_candidate_filter import real_token_mints_from_registry
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.robust_return_metrics import summarize_robust_returns


def main() -> int:
    args = parse_args()
    rows = ResearchDatasetStore(args.dataset_path).load_all()
    if args.real_only:
        real_mints = real_token_mints_from_registry(min_liquidity_usd=args.min_liquidity_usd)
        rows = [row for row in rows if row.token_mint in real_mints]
    selected_rule_ids = args.rule_id
    rules = [
        rule for rule in default_rule_library()
        if not selected_rule_ids or rule.rule_id in selected_rule_ids
    ]
    backtester = RuleBacktester()
    summaries: list[dict[str, Any]] = []
    for rule in rules:
        selected = [
            row for row in rows
            if row.forward_return is not None and backtester.row_passes_rule(row, rule)
        ]
        values = [row.forward_return for row in selected if row.forward_return is not None]
        robust = summarize_robust_returns(values)
        summary = {
            "rule_id": rule.rule_id,
            "rule_name": rule.name,
            "selected_count": len(selected),
            "token_count": len({row.token_mint for row in selected}),
            "robust_returns": robust,
        }
        summaries.append(summary)
        print(f"{rule.rule_id}.selected_count={summary['selected_count']}")
        print(f"{rule.rule_id}.mean_forward_return={robust['mean']}")
        print(f"{rule.rule_id}.median_forward_return={robust['median']}")
        print(f"{rule.rule_id}.trimmed_mean={robust['trimmed_mean']}")
        print(f"{rule.rule_id}.winsorized_mean={robust['winsorized_mean']}")
        print(f"{rule.rule_id}.positive_rate={robust['positive_rate']}")
        print(f"{rule.rule_id}.top_1_outlier_contribution={robust['top_1_outlier_contribution']}")
    report = {
        "report_id": _report_id(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_path": args.dataset_path,
        "rule_summaries": summaries,
        "warning_flags": ["diagnostic_only_not_trading_signal"],
    }
    output_dir = Path(args.output_dir)
    markdown_path = output_dir / f"{report['report_id']}.md"
    json_path = output_dir / f"{report['report_id']}.json"
    _write_json(report, json_path)
    _write_markdown(report, markdown_path)
    print(f"markdown_path={markdown_path}")
    print(f"json_path={json_path}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build robust rule return report.")
    parser.add_argument("--dataset-path", default="data/backtests/diagnostics/research_dataset_nearest300.jsonl")
    parser.add_argument("--rule-id", action="append")
    parser.add_argument("--real-only", action="store_true")
    parser.add_argument("--min-liquidity-usd", type=float)
    parser.add_argument("--output-dir", default="data/backtests/diagnostics/reports")
    return parser.parse_args()


def _report_id() -> str:
    created = datetime.now(timezone.utc).isoformat()
    digest = sha256(f"rule_robust_return|{created}".encode("utf-8")).hexdigest()[:16]
    return f"rule_robust_return_{digest}"


def _write_json(report: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def _write_markdown(report: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Rule Robust Return Report",
        "",
        "> Warning: Robust return report is diagnostic only. It is not a trading signal.",
        "",
        "| Rule | Selected | Mean | Median | Trimmed | Winsorized | Positive Rate | Top 1 Share |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in report["rule_summaries"]:
        robust = item["robust_returns"]
        lines.append(
            "| "
            f"`{item['rule_id']}` | {item['selected_count']} | "
            f"{_fmt(robust['mean'])} | {_fmt(robust['median'])} | "
            f"{_fmt(robust['trimmed_mean'])} | {_fmt(robust['winsorized_mean'])} | "
            f"{_fmt(robust['positive_rate'])} | {_fmt(robust['top_1_outlier_contribution'])} |"
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def _fmt(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}"


if __name__ == "__main__":
    raise SystemExit(main())
