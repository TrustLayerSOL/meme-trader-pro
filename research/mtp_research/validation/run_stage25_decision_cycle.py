"""Offline Stage 25 rule failure and evidence expansion decision cycle."""

from __future__ import annotations

import argparse
import subprocess
import sys


def main() -> int:
    args = parse_args()
    outputs = []
    for label, command in build_commands(args):
        print(f"step_start={label}", flush=True)
        completed = run_step(command)
        outputs.append((label, completed.stdout))
        print(completed.stdout, end="")
        print(f"step_done={label}", flush=True)
    parsed = {label: parse_key_values(output) for label, output in outputs}
    rule = parsed.get("rule_failure_review", {})
    final_decision = _final_decision(rule.get("recommended_next_action", "unknown"))
    print(f"final_decision={final_decision}")
    print(f"recommended_next_action={rule.get('recommended_next_action')}")
    print(f"evidence_scale_recommendation={rule.get('evidence_scale_recommendation')}")
    print(f"rule_review_recommendation={rule.get('rule_review_recommendation')}")
    print(f"rule_failure_markdown_path={rule.get('markdown_path')}")
    print(f"rule_failure_json_path={rule.get('json_path')}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Stage 25 decision cycle.")
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
            "diagnostic_walk_forward_review",
            [python, "-m", "research.mtp_research.validation.run_diagnostic_walk_forward_review", *real_args],
        ),
        (
            "rule_failure_review",
            [python, "-m", "research.mtp_research.validation.run_rule_failure_review", *real_args],
        ),
        (
            "fold_sufficiency_report",
            [python, "-m", "research.mtp_research.validation.run_fold_sufficiency_report", *real_args],
        ),
        (
            "dataset_sufficiency_report",
            [python, "-m", "research.mtp_research.validation.run_dataset_sufficiency_report", *real_args],
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


def _final_decision(recommended_next_action: str) -> str:
    if "candidate_diversity" in recommended_next_action:
        return "add more candidates"
    if "time_span" in recommended_next_action:
        return "expand time span"
    if "price_inference" in recommended_next_action:
        return "improve clean price inference"
    if "rule" in recommended_next_action or "manual" in recommended_next_action:
        return "inspect selected rule rows"
    if recommended_next_action == "unknown":
        return "blocked"
    return "bounded evidence retest"


if __name__ == "__main__":
    raise SystemExit(main())
