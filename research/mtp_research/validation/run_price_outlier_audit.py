"""CLI for offline price outlier diagnostics."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from research.mtp_research.pipeline.real_candidate_filter import real_token_mints_from_registry
from research.mtp_research.validation.price_outlier_auditor import (
    find_extreme_return_rows,
    find_extreme_runup_rows,
    group_outliers_by_entry_source,
    group_outliers_by_token,
)
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore


def main() -> int:
    args = parse_args()
    rows = ResearchDatasetStore(args.dataset_path).load_all()
    if args.real_only:
        real_mints = real_token_mints_from_registry(min_liquidity_usd=args.min_liquidity_usd)
        rows = [row for row in rows if row.token_mint in real_mints]

    extreme_returns = find_extreme_return_rows(rows, threshold=args.threshold, limit=args.limit)
    extreme_runups = find_extreme_runup_rows(rows, threshold=args.threshold, limit=args.limit)
    outlier_rows = extreme_returns + extreme_runups
    report_id = _report_id()
    report = {
        "report_id": report_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_path": args.dataset_path,
        "threshold": args.threshold,
        "limit": args.limit,
        "row_count": len(rows),
        "extreme_forward_return_count": len(extreme_returns),
        "extreme_runup_count": len(extreme_runups),
        "token_concentration": group_outliers_by_token(outlier_rows),
        "entry_price_source_counts": group_outliers_by_entry_source(outlier_rows),
        "extreme_forward_return_rows": [_row_summary(row) for row in extreme_returns],
        "extreme_runup_rows": [_row_summary(row) for row in extreme_runups],
        "warning_flags": ["diagnostic_only_not_trading_signal"],
    }
    output_dir = Path(args.output_dir)
    markdown_path = output_dir / f"{report_id}.md"
    json_path = output_dir / f"{report_id}.json"
    _write_json(report, json_path)
    _write_markdown(report, markdown_path)

    print(f"extreme_forward_return_rows={len(extreme_returns)}")
    print(f"extreme_runup_rows={len(extreme_runups)}")
    print(f"token_concentration={report['token_concentration']}")
    print(f"entry_price_source_counts={report['entry_price_source_counts']}")
    print(f"markdown_path={markdown_path}")
    print(f"json_path={json_path}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit extreme return and runup rows.")
    parser.add_argument("--dataset-path", default="data/backtests/diagnostics/research_dataset_nearest300.jsonl")
    parser.add_argument("--threshold", type=float, default=1.0)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--real-only", action="store_true")
    parser.add_argument("--min-liquidity-usd", type=float)
    parser.add_argument("--output-dir", default="data/backtests/diagnostics/reports")
    return parser.parse_args()


def _report_id() -> str:
    created = datetime.now(timezone.utc).isoformat()
    digest = sha256(f"price_outlier_audit|{created}".encode("utf-8")).hexdigest()[:16]
    return f"price_outlier_audit_{digest}"


def _row_summary(row: ResearchDatasetRow) -> dict[str, Any]:
    return {
        "row_id": row.row_id,
        "token_mint": row.token_mint,
        "snapshot_ts": row.snapshot_ts,
        "window_name": row.window_name,
        "horizon_name": row.horizon_name,
        "entry_price_source": row.entry_price_source,
        "entry_price_ts": row.entry_price_ts,
        "forward_return": row.forward_return,
        "max_runup": row.max_runup,
        "max_drawdown": row.max_drawdown,
        "label_quality": row.label_quality,
    }


def _write_json(report: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def _write_markdown(report: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Price Outlier Audit",
        "",
        "> Warning: Price outlier audit is diagnostic only. It is not a trading signal.",
        "",
        f"- Report ID: `{report['report_id']}`",
        f"- Dataset path: `{report['dataset_path']}`",
        f"- Row count: `{report['row_count']}`",
        f"- Threshold: `{report['threshold']}`",
        f"- Extreme forward return rows: `{report['extreme_forward_return_count']}`",
        f"- Extreme runup rows: `{report['extreme_runup_count']}`",
        f"- Token concentration: `{report['token_concentration']}`",
        f"- Entry price source counts: `{report['entry_price_source_counts']}`",
        "",
        "## Extreme Forward Return Rows",
        "",
    ]
    lines.extend(_row_lines(report["extreme_forward_return_rows"]))
    lines.extend(["", "## Extreme Runup Rows", ""])
    lines.extend(_row_lines(report["extreme_runup_rows"]))
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def _row_lines(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["- None."]
    return [
        "- "
        f"`{row['row_id']}` token `{row['token_mint']}` "
        f"source `{row['entry_price_source']}` "
        f"forward `{row['forward_return']}` runup `{row['max_runup']}`"
        for row in rows
    ]


if __name__ == "__main__":
    raise SystemExit(main())
