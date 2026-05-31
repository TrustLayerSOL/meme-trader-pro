"""CLI for comparing ungated and price-quality-gated diagnostic artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.price_quality_validation_comparison import (
    build_price_quality_validation_comparison,
    write_comparison_json,
    write_comparison_markdown,
)


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    ungated_fold = (
        Path(args.ungated_fold_json)
        if args.ungated_fold_json
        else _latest_report_for_dataset(output_dir, "fold_sufficiency_*.json", args.ungated_dataset_path)
    )
    gated_fold = (
        Path(args.gated_fold_json)
        if args.gated_fold_json
        else _latest_report_for_dataset(output_dir, "fold_sufficiency_*.json", args.gated_dataset_path)
    )
    ungated_robust = (
        Path(args.ungated_robust_json)
        if args.ungated_robust_json
        else _latest_report_for_dataset(output_dir, "outlier_adjusted_rule_*.json", args.ungated_dataset_path)
    )
    gated_robust = (
        Path(args.gated_robust_json)
        if args.gated_robust_json
        else _latest_report_for_dataset(output_dir, "outlier_adjusted_rule_*.json", args.gated_dataset_path)
    )
    report = build_price_quality_validation_comparison(
        ungated_dataset_path=args.ungated_dataset_path,
        gated_dataset_path=args.gated_dataset_path,
        ungated_fold_json_path=ungated_fold,
        gated_fold_json_path=gated_fold,
        ungated_robust_json_path=ungated_robust,
        gated_robust_json_path=gated_robust,
    )
    markdown_path = write_comparison_markdown(report, output_dir / f"{report['report_id']}.md")
    json_path = write_comparison_json(report, output_dir / f"{report['report_id']}.json")
    print(f"row_loss_count={report['row_loss_count']}")
    print(f"row_loss_rate={report['row_loss_rate']}")
    print(f"token_loss_count={report['token_loss_count']}")
    print(f"fold_loss_count={report['fold_loss_count']}")
    print(f"selected_trade_loss_count={report['selected_trade_loss_count']}")
    print(f"outlier_dependence_improved={report['outlier_dependence_improved']}")
    print(f"recommended_next_action={report['recommended_next_action']}")
    print(f"markdown_path={markdown_path}")
    print(f"json_path={json_path}")
    print(f"ungated_fold_json={ungated_fold}")
    print(f"gated_fold_json={gated_fold}")
    print(f"ungated_robust_json={ungated_robust}")
    print(f"gated_robust_json={gated_robust}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare price-quality-gated validation.")
    parser.add_argument("--ungated-dataset-path", default="data/backtests/diagnostics/research_dataset_nearest300.jsonl")
    parser.add_argument("--gated-dataset-path", default="data/backtests/diagnostics/research_dataset_price_quality_gated.jsonl")
    parser.add_argument("--ungated-fold-json")
    parser.add_argument("--gated-fold-json")
    parser.add_argument("--ungated-robust-json")
    parser.add_argument("--gated-robust-json")
    parser.add_argument("--output-dir", default="data/backtests/diagnostics/reports")
    return parser.parse_args()


def _latest_report_for_dataset(output_dir: Path, pattern: str, dataset_path: str) -> Path | None:
    import json

    matches: list[Path] = []
    for path in output_dir.glob(pattern):
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if payload.get("dataset_path") == dataset_path:
            matches.append(path)
    return sorted(matches, key=lambda item: item.stat().st_mtime)[-1] if matches else None


if __name__ == "__main__":
    raise SystemExit(main())
