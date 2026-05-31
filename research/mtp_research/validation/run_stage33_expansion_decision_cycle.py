"""Offline Stage 33 evidence expansion decision cycle."""

from __future__ import annotations

import argparse
import subprocess
import sys


def main() -> int:
    args = parse_args()
    python = sys.executable
    real_args = ["--real-only"] if args.real_only else []
    commands = [
        (
            "rule_robust_return_report",
            [python, "-m", "research.mtp_research.validation.run_rule_robust_return_report", *real_args],
        ),
        (
            "outlier_price_path_review",
            [python, "-m", "research.mtp_research.validation.run_outlier_price_path_review", *real_args],
        ),
        (
            "selected_row_audit",
            [python, "-m", "research.mtp_research.validation.run_selected_row_audit", *real_args],
        ),
        (
            "price_coverage_report",
            [python, "-m", "research.mtp_research.validation.run_price_coverage_report", *real_args],
        ),
        (
            "dataset_sufficiency_report",
            [python, "-m", "research.mtp_research.validation.run_dataset_sufficiency_report", "--dataset-path", "data/backtests/diagnostics/research_dataset_nearest300.jsonl", *real_args, "--output-dir", "data/backtests/diagnostics/reports"],
        ),
        (
            "fold_sufficiency_report",
            [python, "-m", "research.mtp_research.validation.run_fold_sufficiency_report", *real_args],
        ),
        (
            "diagnostic_walk_forward_review",
            [python, "-m", "research.mtp_research.validation.run_diagnostic_walk_forward_review", *real_args],
        ),
        (
            "evidence_expansion_decision",
            [python, "-m", "research.mtp_research.validation.run_evidence_expansion_decision", *real_args],
        ),
    ]
    parsed = {}
    for label, command in commands:
        print(f"stage33_{label}=starting")
        output = run_command(label, command)
        print(output, end="" if output.endswith("\n") else "\n")
        parsed[label] = _parse_key_values(output)
    decision = parsed.get("evidence_expansion_decision", {})
    print(f"final_recommended_next_action={decision.get('recommended_next_action')}")
    print(f"bounded_command={decision.get('recommended_command')}")
    print(f"rule_classifications={decision.get('rule_signal_classifications')}")
    print(f"markdown_path={decision.get('markdown_path')}")
    print(f"json_path={decision.get('json_path')}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Stage 33 offline decision cycle.")
    parser.add_argument("--real-only", action="store_true")
    return parser.parse_args()


def run_command(label: str, command: list[str]) -> str:
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return result.stdout


def _parse_key_values(output: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
