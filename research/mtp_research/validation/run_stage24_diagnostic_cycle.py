"""One-command offline Stage 24 diagnostic validation cycle."""

from __future__ import annotations

import argparse
import subprocess
import sys


def main() -> int:
    args = parse_args()
    commands = build_commands(args)
    outputs = []
    for label, command in commands:
        print(f"step_start={label}", flush=True)
        completed = run_step(command)
        outputs.append((label, completed.stdout))
        print(completed.stdout, end="")
        print(f"step_done={label}", flush=True)

    parsed = {label: parse_key_values(output) for label, output in outputs}
    thesis_status_changes = parsed.get("diagnostic_validation_review", {}).get(
        "thesis_status_changes",
        "{}",
    )
    print(f"best_fold_config={parsed.get('best_diagnostic_walk_forward', {}).get('best_config_name')}")
    print(f"diagnostic_rules_with_valid_folds={parsed.get('diagnostic_walk_forward_review', {}).get('rules_with_valid_folds')}")
    print(f"best_rule_by_consistency={parsed.get('diagnostic_walk_forward_review', {}).get('best_rule_by_consistency')}")
    print(f"best_rule_by_avg_test_net={parsed.get('diagnostic_walk_forward_review', {}).get('best_rule_by_avg_test_net')}")
    print(f"thesis_status_changes={thesis_status_changes}")
    print(f"recommended_next_action={parsed.get('diagnostic_walk_forward_review', {}).get('recommended_next_action')}")
    print(f"diagnostic_review_markdown_path={parsed.get('diagnostic_walk_forward_review', {}).get('markdown_path')}")
    print(f"diagnostic_review_json_path={parsed.get('diagnostic_walk_forward_review', {}).get('json_path')}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Stage 24 diagnostic cycle.")
    parser.add_argument("--real-only", action="store_true", default=True)
    parser.add_argument("--min-liquidity-usd", type=float)
    return parser.parse_args()


def build_commands(args: argparse.Namespace) -> list[tuple[str, list[str]]]:
    python = sys.executable
    real_args = ["--real-only"]
    if args.min_liquidity_usd is not None:
        real_args += ["--min-liquidity-usd", str(args.min_liquidity_usd)]
    return [
        (
            "best_diagnostic_walk_forward",
            [
                python,
                "-m",
                "research.mtp_research.validation.run_best_diagnostic_walk_forward",
                *real_args,
            ],
        ),
        (
            "diagnostic_walk_forward_review",
            [
                python,
                "-m",
                "research.mtp_research.validation.run_diagnostic_walk_forward_review",
                *real_args,
            ],
        ),
        (
            "diagnostic_validation_review",
            [
                python,
                "-m",
                "research.mtp_research.validation.run_diagnostic_validation_review",
            ],
        ),
        (
            "diagnostic_thesis_evaluation",
            [
                python,
                "-m",
                "research.mtp_research.validation.run_thesis_evaluation",
                "--walk-forward-store-path",
                "data/backtests/diagnostics/walk_forward_best_diagnostic.jsonl",
                "--decision-store-path",
                "data/backtests/diagnostics/thesis_decisions_diagnostic.jsonl",
                "--output-dir",
                "data/backtests/diagnostics/reports",
                "--sample-adequacy-dataset-path",
                "data/backtests/diagnostics/research_dataset_nearest300.jsonl",
            ],
        ),
    ]


def run_step(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=True, text=True)


def parse_key_values(output: str) -> dict[str, str]:
    parsed = {}
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            parsed[key.strip()] = value.strip()
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
