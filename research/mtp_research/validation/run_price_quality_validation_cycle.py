"""Run offline price-quality-gated diagnostic validation."""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path


DEFAULT_GATED_DATASET = "data/backtests/diagnostics/research_dataset_price_quality_gated.jsonl"
DEFAULT_GATED_WALK_FORWARD = "data/backtests/diagnostics/walk_forward_price_quality_gated.jsonl"
DEFAULT_REPORT_DIR = "data/backtests/diagnostics/reports"


def main() -> int:
    args = parse_args()
    result = run_cycle(args)
    print(f"gated_row_count={result.get('gated_row_count')}")
    print(f"pass_rate={result.get('pass_rate')}")
    print(f"token_count={result.get('token_count')}")
    print(f"best_fold_config={result.get('best_fold_config')}")
    print(f"valid_folds={result.get('valid_folds')}")
    print(f"rule_classifications={result.get('rule_classifications')}")
    print(f"robust_metrics={result.get('robust_metrics')}")
    print(f"recommended_next_action={result.get('recommended_next_action')}")
    print(f"report_paths={result.get('report_paths')}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run price-quality-gated validation cycle.")
    parser.add_argument("--dataset-path", default="data/backtests/diagnostics/research_dataset_nearest300.jsonl")
    parser.add_argument("--gated-dataset-path", default=DEFAULT_GATED_DATASET)
    parser.add_argument("--walk-forward-store-path", default=DEFAULT_GATED_WALK_FORWARD)
    parser.add_argument("--output-dir", default=DEFAULT_REPORT_DIR)
    parser.add_argument("--real-only", action="store_true")
    return parser.parse_args()


def run_cycle(args: argparse.Namespace) -> dict:
    python = sys.executable
    real_only = ["--real-only"] if args.real_only else []
    report_paths: dict[str, str] = {}
    outputs: dict[str, str] = {}

    gate = _run(
        [
            python,
            "-m",
            "research.mtp_research.validation.run_price_quality_gate",
            "--dataset-path",
            args.dataset_path,
            "--output-dataset-path",
            args.gated_dataset_path,
            "--output-dir",
            args.output_dir,
            *real_only,
        ]
    )
    outputs["gate"] = gate
    gate_values = _parse_key_values(gate)
    report_paths["gate_markdown"] = gate_values.get("markdown_path", "")
    report_paths["gate_json"] = gate_values.get("json_path", "")

    dataset = _run(
        [
            python,
            "-m",
            "research.mtp_research.validation.run_dataset_sufficiency_report",
            "--dataset-path",
            args.gated_dataset_path,
            "--output-dir",
            args.output_dir,
            *real_only,
        ]
    )
    dataset_values = _parse_key_values(dataset)
    report_paths["dataset_sufficiency_json"] = dataset_values.get("json_path", "")

    fold = _run(
        [
            python,
            "-m",
            "research.mtp_research.validation.run_fold_sufficiency_report",
            "--dataset-path",
            args.gated_dataset_path,
            "--output-dir",
            args.output_dir,
            *real_only,
        ]
    )
    fold_values = _parse_key_values(fold)
    report_paths["fold_sufficiency_json"] = fold_values.get("json_path", "")

    walk_forward = _run(
        [
            python,
            "-m",
            "research.mtp_research.validation.run_best_diagnostic_walk_forward",
            "--dataset-path",
            args.gated_dataset_path,
            "--store-path",
            args.walk_forward_store_path,
            "--output-dir",
            args.output_dir,
            *real_only,
        ]
    )
    wf_values = _parse_key_values(walk_forward)
    report_paths["walk_forward_json"] = wf_values.get("walk_forward_json_path", "")

    review = ""
    review_values: dict[str, str] = {}
    if wf_values.get("walk_forward_ran") == "True":
        review = _run(
            [
                python,
                "-m",
                "research.mtp_research.validation.run_diagnostic_walk_forward_review",
                "--dataset-path",
                args.gated_dataset_path,
                "--walk-forward-store-path",
                args.walk_forward_store_path,
                "--output-dir",
                args.output_dir,
                *real_only,
            ]
        )
        review_values = _parse_key_values(review)
        report_paths["diagnostic_walk_forward_review_json"] = review_values.get("json_path", "")

    outlier = _run(
        [
            python,
            "-m",
            "research.mtp_research.validation.run_outlier_price_path_review",
            "--dataset-path",
            args.gated_dataset_path,
            "--output-dir",
            args.output_dir,
            *real_only,
        ]
    )
    outlier_values = _parse_key_values(outlier)
    report_paths["outlier_price_path_json"] = outlier_values.get("json_path", "")

    robust = _run(
        [
            python,
            "-m",
            "research.mtp_research.validation.run_rule_robust_return_report",
            "--dataset-path",
            args.gated_dataset_path,
            "--output-dir",
            args.output_dir,
            *real_only,
        ]
    )
    robust_values = _parse_key_values(robust)
    report_paths["robust_rule_json"] = robust_values.get("json_path", "")

    adjusted = _run(
        [
            python,
            "-m",
            "research.mtp_research.validation.run_outlier_adjusted_rule_report",
            "--dataset-path",
            args.gated_dataset_path,
            "--outlier-report-path",
            report_paths["outlier_price_path_json"],
            "--output-dir",
            args.output_dir,
            *real_only,
        ]
    )
    adjusted_values = _parse_key_values(adjusted)
    report_paths["outlier_adjusted_json"] = adjusted_values.get("json_path", "")

    decision = _run(
        [
            python,
            "-m",
            "research.mtp_research.validation.run_evidence_expansion_decision",
            "--diagnostic-dataset-path",
            args.gated_dataset_path,
            "--output-dir",
            args.output_dir,
            "--robust-rule-report-json",
            report_paths["robust_rule_json"],
            "--outlier-price-path-json",
            report_paths["outlier_price_path_json"],
            "--fold-sufficiency-json",
            report_paths["fold_sufficiency_json"],
            "--diagnostic-walk-forward-review-json",
            report_paths.get("diagnostic_walk_forward_review_json", ""),
            "--dataset-sufficiency-json",
            report_paths["dataset_sufficiency_json"],
            *real_only,
        ]
    )
    decision_values = _parse_key_values(decision)
    report_paths["evidence_expansion_json"] = decision_values.get("json_path", "")

    outputs.update(
        {
            "dataset": dataset,
            "fold": fold,
            "walk_forward": walk_forward,
            "review": review,
            "outlier": outlier,
            "robust": robust,
            "adjusted": adjusted,
            "decision": decision,
        }
    )
    return {
        "gated_row_count": gate_values.get("passed_row_count"),
        "pass_rate": gate_values.get("pass_rate"),
        "token_count": gate_values.get("token_count_passed"),
        "best_fold_config": fold_values.get("best_config_name") or wf_values.get("best_config_name"),
        "valid_folds": _valid_folds_from_output(fold),
        "rule_classifications": _literal_value(decision_values.get("rule_signal_classifications", "{}")),
        "robust_metrics": _robust_metrics_from_output(robust),
        "recommended_next_action": decision_values.get("recommended_next_action") or adjusted_values.get("recommended_next_action"),
        "report_paths": {k: v for k, v in report_paths.items() if v},
        "outputs": outputs,
    }


def _run(command: list[str]) -> str:
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return completed.stdout


def _parse_key_values(output: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def _literal_value(value: str):
    try:
        return ast.literal_eval(value)
    except Exception:
        return value


def _valid_folds_from_output(output: str) -> int | None:
    for line in output.splitlines():
        if "valid_folds:" in line:
            marker = "valid_folds:"
            start = line.index(marker) + len(marker)
            end = line.find(",", start)
            text = line[start:] if end == -1 else line[start:end]
            try:
                return int(text)
            except ValueError:
                return None
    return None


def _robust_metrics_from_output(output: str) -> dict[str, dict[str, str]]:
    metrics: dict[str, dict[str, str]] = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if "." not in key:
            continue
        rule_id, metric = key.split(".", 1)
        if metric in {"selected_count", "median_forward_return", "winsorized_mean", "positive_rate"}:
            metrics.setdefault(rule_id, {})[metric] = value
    return metrics


if __name__ == "__main__":
    raise SystemExit(main())
