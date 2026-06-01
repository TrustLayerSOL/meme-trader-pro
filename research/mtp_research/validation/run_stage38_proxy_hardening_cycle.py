"""Offline Stage 38 native SOL proxy hardening cycle."""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path


def main() -> int:
    args = parse_args()
    result = run_cycle(args)
    print(f"native_proxy_backed_count={result.get('native_proxy_backed_count')}")
    print(f"native_proxy_passed_count={result.get('native_proxy_passed_count')}")
    print(f"native_proxy_failed_count={result.get('native_proxy_failed_count')}")
    print(f"proxy_separated_rule_metrics={result.get('proxy_separated_rule_metrics')}")
    print(f"outlier_sensitivity_improved={result.get('outlier_sensitivity_improved')}")
    print(f"recommended_next_action={result.get('recommended_next_action')}")
    print(f"native_sol_proxy_quality_json={result.get('native_sol_proxy_quality_json')}")
    print(f"proxy_separated_rule_report_json={result.get('proxy_separated_rule_report_json')}")
    print(f"report_paths={result.get('report_paths')}")
    print("network_calls=0")
    return 0


def run_cycle(args: argparse.Namespace) -> dict:
    python = sys.executable
    real_only = ["--real-only"] if args.real_only else []
    output_dir = str(Path(args.output_dir))

    gate_output = _run(
        [
            python,
            "-m",
            "research.mtp_research.validation.run_native_sol_proxy_quality_gate",
            "--dataset-path",
            args.dataset_path,
            "--events-path",
            args.events_path,
            "--output-dataset-path",
            args.proxy_gated_dataset_path,
            "--output-dir",
            output_dir,
            *real_only,
        ]
    )
    gate_values = _parse_key_values(gate_output)

    separated_output = _run(
        [
            python,
            "-m",
            "research.mtp_research.validation.run_proxy_separated_rule_report",
            "--dataset-path",
            args.dataset_path,
            "--events-path",
            args.events_path,
            "--output-dir",
            output_dir,
            *real_only,
        ]
    )
    separated_values = _parse_key_values(separated_output)

    price_quality_output = _run(
        [
            python,
            "-m",
            "research.mtp_research.validation.run_price_quality_validation_cycle",
            "--dataset-path",
            args.dataset_path,
            "--gated-dataset-path",
            args.price_quality_gated_dataset_path,
            "--output-dir",
            output_dir,
            *real_only,
        ]
    )
    price_quality_values = _parse_key_values(price_quality_output)

    outlier_output = _run(
        [
            python,
            "-m",
            "research.mtp_research.validation.run_outlier_adjusted_rule_report",
            "--dataset-path",
            args.proxy_gated_dataset_path,
            "--output-dir",
            output_dir,
            *real_only,
        ]
    )
    outlier_values = _parse_key_values(outlier_output)

    decision_output = _run(
        [
            python,
            "-m",
            "research.mtp_research.validation.run_evidence_expansion_decision",
            "--diagnostic-dataset-path",
            args.proxy_gated_dataset_path,
            "--output-dir",
            output_dir,
            *real_only,
        ]
    )
    decision_values = _parse_key_values(decision_output)

    return {
        "native_proxy_backed_count": gate_values.get("native_proxy_backed_count"),
        "native_proxy_passed_count": gate_values.get("native_proxy_passed_count"),
        "native_proxy_failed_count": gate_values.get("native_proxy_failed_count"),
        "proxy_separated_rule_metrics": _extract_subset_counts(separated_values),
        "outlier_sensitivity_improved": _outlier_sensitivity_improved(price_quality_values, outlier_values),
        "recommended_next_action": decision_values.get("recommended_next_action")
        or outlier_values.get("recommended_next_action")
        or "review_proxy_gated_rule_metrics_before_scaling",
        "native_sol_proxy_quality_json": gate_values.get("json_path"),
        "proxy_separated_rule_report_json": separated_values.get("json_path"),
        "report_paths": {
            "native_sol_proxy_quality_json": gate_values.get("json_path", ""),
            "proxy_separated_rule_report_json": separated_values.get("json_path", ""),
            "price_quality_report_paths": price_quality_values.get("report_paths", ""),
            "outlier_adjusted_json": outlier_values.get("json_path", ""),
            "evidence_expansion_json": decision_values.get("json_path", ""),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Stage 38 native SOL proxy hardening cycle offline.")
    parser.add_argument("--dataset-path", default="data/backtests/diagnostics/research_dataset_nearest300.jsonl")
    parser.add_argument("--events-path", default="data/normalized/events.jsonl")
    parser.add_argument("--proxy-gated-dataset-path", default="data/backtests/diagnostics/research_dataset_native_sol_proxy_gated.jsonl")
    parser.add_argument("--price-quality-gated-dataset-path", default="data/backtests/diagnostics/research_dataset_price_quality_gated.jsonl")
    parser.add_argument("--output-dir", default="data/backtests/diagnostics/reports")
    parser.add_argument("--real-only", action="store_true")
    return parser.parse_args()


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


def _extract_subset_counts(values: dict[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in values.items()
        if key.startswith("subset_") and key.endswith(".selected_count")
    }


def _outlier_sensitivity_improved(price_quality_values: dict[str, str], outlier_values: dict[str, str]) -> bool | None:
    classifications = _literal(price_quality_values.get("rule_classifications", "{}"))
    if isinstance(classifications, dict) and classifications:
        had_outlier = any(value == "outlier_dependent" for value in classifications.values())
        return False if had_outlier and outlier_values.get("recommended_next_action") else None
    return None


def _literal(value: str):
    try:
        return ast.literal_eval(value)
    except Exception:
        return value


if __name__ == "__main__":
    raise SystemExit(main())
