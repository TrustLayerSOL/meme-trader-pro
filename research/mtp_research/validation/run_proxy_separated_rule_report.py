"""Build side-by-side rule diagnostics for native SOL proxy subsets."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from research.mtp_research.backtest.rule_backtester import RuleBacktester
from research.mtp_research.backtest.rule_library import default_rule_library
from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore
from research.mtp_research.pipeline.real_candidate_filter import real_token_mints_from_registry
from research.mtp_research.validation.native_sol_proxy_quality import NativeSolProxyQualityAnalyzer
from research.mtp_research.validation.native_sol_proxy_quality_models import NativeSolProxyQualityConfig
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.robust_return_metrics import summarize_robust_returns


def main() -> int:
    args = parse_args()
    rows = ResearchDatasetStore(args.dataset_path).load_all()
    if args.real_only:
        real_mints = real_token_mints_from_registry()
        rows = [row for row in rows if row.token_mint in real_mints]
    events = NormalizedEventStore(args.events_path).load_all()
    report = build_proxy_separated_rule_report(rows, events, args.dataset_path)
    output_dir = Path(args.output_dir)
    json_path = output_dir / f"{report['report_id']}.json"
    markdown_path = output_dir / f"{report['report_id']}.md"
    _write_json(report, json_path)
    _write_markdown(report, markdown_path)

    for subset_name, subset in report["subsets"].items():
        print(f"subset_{subset_name}.row_count={subset['row_count']}")
        for summary in subset["rule_summaries"]:
            print(f"subset_{subset_name}.{summary['rule_id']}.selected_count={summary['selected_count']}")
            print(f"subset_{subset_name}.{summary['rule_id']}.median_return={summary['median_return']}")
            print(f"subset_{subset_name}.{summary['rule_id']}.capped_mean={summary['capped_mean']}")
            print(f"subset_{subset_name}.{summary['rule_id']}.positive_rate={summary['positive_rate']}")
    print(f"markdown_path={markdown_path}")
    print(f"json_path={json_path}")
    print("network_calls=0")
    return 0


def build_proxy_separated_rule_report(
    rows: list[ResearchDatasetRow],
    events,
    dataset_path: str,
) -> dict[str, Any]:
    analyzer = NativeSolProxyQualityAnalyzer()
    _passed, decisions, _quality_report = analyzer.filter_rows(
        rows,
        events,
        NativeSolProxyQualityConfig(),
        dataset_path=dataset_path,
    )
    decisions_by_row = {decision.row_id: decision for decision in decisions}
    proxy_rows = [row for row in rows if decisions_by_row[row.row_id].is_native_sol_proxy_backed]
    non_proxy_rows = [row for row in rows if not decisions_by_row[row.row_id].is_native_sol_proxy_backed]
    proxy_gated_rows = [row for row in rows if decisions_by_row[row.row_id].passed]
    subsets = {
        "all_price_rows": _summarize_subset(rows),
        "native_sol_proxy_only": _summarize_subset(proxy_rows),
        "non_native_sol_proxy": _summarize_subset(non_proxy_rows),
        "native_sol_proxy_quality_gated": _summarize_subset(proxy_gated_rows),
    }
    return {
        "report_id": _report_id(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_path": str(dataset_path),
        "subsets": subsets,
        "warning_flags": ["diagnostic_only_not_trading_signal"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build proxy-separated rule report.")
    parser.add_argument("--dataset-path", default="data/backtests/diagnostics/research_dataset_nearest300.jsonl")
    parser.add_argument("--events-path", default="data/normalized/events.jsonl")
    parser.add_argument("--output-dir", default="data/backtests/diagnostics/reports")
    parser.add_argument("--real-only", action="store_true")
    return parser.parse_args()


def _summarize_subset(rows: list[ResearchDatasetRow]) -> dict[str, Any]:
    backtester = RuleBacktester()
    summaries = []
    for rule in default_rule_library():
        selected = [
            row for row in rows
            if row.forward_return is not None and backtester.row_passes_rule(row, rule)
        ]
        values = [row.forward_return for row in selected if row.forward_return is not None]
        capped = [min(max(value, -1.0), 1.0) for value in values]
        robust = summarize_robust_returns(values)
        summaries.append(
            {
                "rule_id": rule.rule_id,
                "rule_name": rule.name,
                "selected_count": len(selected),
                "median_return": robust["median"],
                "capped_mean": (sum(capped) / len(capped)) if capped else None,
                "positive_rate": robust["positive_rate"],
                "outlier_share": robust["top_1_outlier_contribution"],
                "classification": _classification(robust, len(selected)),
            }
        )
    return {
        "row_count": len(rows),
        "token_count": len({row.token_mint for row in rows}),
        "rule_summaries": summaries,
    }


def _classification(robust: dict[str, Any], selected_count: int) -> str:
    if selected_count == 0:
        return "no_selected_rows"
    if robust.get("top_1_outlier_contribution") is not None and robust["top_1_outlier_contribution"] > 0.5:
        return "outlier_sensitive"
    return "diagnostic_summary_only"


def _report_id() -> str:
    created = datetime.now(timezone.utc).isoformat()
    digest = sha256(f"proxy_separated_rule|{created}".encode("utf-8")).hexdigest()[:16]
    return f"proxy_separated_rule_{digest}"


def _write_json(report: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def _write_markdown(report: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Proxy-Separated Rule Report",
        "",
        "> Warning: Proxy-separated rule metrics are diagnostic only. They are not trading signals.",
        "",
    ]
    for subset_name, subset in report["subsets"].items():
        lines.extend(
            [
                f"## {subset_name}",
                "",
                f"- Row count: `{subset['row_count']}`",
                f"- Token count: `{subset['token_count']}`",
                "",
                "| Rule | Selected | Median | Capped Mean | Positive Rate | Outlier Share | Classification |",
                "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for summary in subset["rule_summaries"]:
            lines.append(
                "| "
                f"`{summary['rule_id']}` | {summary['selected_count']} | "
                f"{_fmt(summary['median_return'])} | {_fmt(summary['capped_mean'])} | "
                f"{_fmt(summary['positive_rate'])} | {_fmt(summary['outlier_share'])} | "
                f"`{summary['classification']}` |"
            )
        lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _fmt(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}"


if __name__ == "__main__":
    raise SystemExit(main())
