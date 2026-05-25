from __future__ import annotations

import time
from typing import Any


MODE = "CANDIDATE_WALK_FORWARD_PAPER_READINESS_GATE_REVIEW_ONLY"
VERSION = "candidate_walk_forward_paper_readiness_gate.v1"

DEFAULT_GATE_CONFIG = {
    "required_walk_forward_conclusion": "continued_validation",
    "min_total_clean_rows": 100,
    "min_validation_clean_rows": 25,
    "min_validation_runner_count": 5,
    "min_validation_token_count": 15,
    "min_context_completion_rate": 0.8,
    "max_excluded_rate": 0.2,
}


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def rate(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else 0.0


def gate_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = dict(DEFAULT_GATE_CONFIG)
    if config:
        merged.update({key: value for key, value in config.items() if key in merged})
    return merged


def failed_gates_for_wallet(wallet: dict[str, Any], config: dict[str, Any]) -> list[str]:
    proof_metric_records = safe_int(wallet.get("proof_metric_records"))
    excluded_records = safe_int(wallet.get("excluded_records"))
    candidate_records = safe_int(wallet.get("candidate_records"), proof_metric_records + excluded_records)
    validation = as_dict(wallet.get("validation"))
    validation_clean = safe_int(validation.get("clean_records"))
    validation_runners = safe_int(validation.get("runner_count"))
    validation_tokens = safe_int(validation.get("token_count"))
    excluded_rate = rate(excluded_records, candidate_records)
    context_completion_rate = rate(proof_metric_records, candidate_records)
    failed: list[str] = []
    if wallet.get("walk_forward_conclusion") != config["required_walk_forward_conclusion"]:
        failed.append("walk_forward_conclusion_not_continued_validation")
    if proof_metric_records < safe_int(config["min_total_clean_rows"]):
        failed.append("min_total_clean_rows_not_met")
    if validation_clean < safe_int(config["min_validation_clean_rows"]):
        failed.append("min_validation_clean_rows_not_met")
    if validation_runners < safe_int(config["min_validation_runner_count"]):
        failed.append("min_validation_runner_count_not_met")
    if validation_tokens < safe_int(config["min_validation_token_count"]):
        failed.append("min_validation_token_count_not_met")
    if context_completion_rate < safe_float(config["min_context_completion_rate"]):
        failed.append("min_context_completion_rate_not_met")
    if excluded_rate > safe_float(config["max_excluded_rate"]):
        failed.append("max_excluded_rate_exceeded")
    return failed


def required_next_steps(status: str, failed_gates: list[str]) -> list[str]:
    if status == "eligible_for_manual_paper_simulation_review":
        return [
            "manual_operator_review_required_before_any_paper_simulation",
            "confirm_execution_safety_gate_remains_paper_safe",
            "prepare_separate_paper_simulation_plan_without_live_execution",
        ]
    steps = ["continue_forward_validation"]
    if any("context" in gate or "excluded" in gate for gate in failed_gates):
        steps.append("reduce_context_blockers_before_paper_review")
    if any("clean_rows" in gate or "runner_count" in gate or "token_count" in gate for gate in failed_gates):
        steps.append("collect_more_clean_candidate_rows")
    if "walk_forward_conclusion_not_continued_validation" in failed_gates:
        steps.append("exclude_from_paper_review_until_walk_forward_recovers")
    return steps


def wallet_gate_row(wallet: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    proof_metric_records = safe_int(wallet.get("proof_metric_records"))
    excluded_records = safe_int(wallet.get("excluded_records"))
    candidate_records = safe_int(wallet.get("candidate_records"), proof_metric_records + excluded_records)
    validation = as_dict(wallet.get("validation"))
    failed = failed_gates_for_wallet(wallet, config)
    status = "eligible_for_manual_paper_simulation_review" if not failed else "not_ready"
    return {
        "wallet_address": wallet.get("wallet_address"),
        "walk_forward_conclusion": wallet.get("walk_forward_conclusion"),
        "paper_readiness_status": status,
        "candidate_records": candidate_records,
        "proof_metric_records": proof_metric_records,
        "excluded_records": excluded_records,
        "excluded_rate": rate(excluded_records, candidate_records),
        "context_completion_rate": rate(proof_metric_records, candidate_records),
        "validation_clean_records": safe_int(validation.get("clean_records")),
        "validation_runner_count": safe_int(validation.get("runner_count")),
        "validation_runner_rate": safe_float(validation.get("runner_rate")),
        "validation_token_count": safe_int(validation.get("token_count")),
        "failed_gates": failed,
        "required_next_steps": required_next_steps(status, failed),
        "paper_simulation_enabled": False,
        "promotion_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "wallet_list_mutation_allowed": False,
    }


def build_candidate_walk_forward_paper_readiness_gate(
    *,
    survivor_review: dict[str, Any],
    generated_at: float | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    cfg = gate_config(config)
    source_wallets = survivor_review.get("wallets") if isinstance(survivor_review.get("wallets"), list) else []
    wallets = [wallet_gate_row(row, cfg) for row in source_wallets if isinstance(row, dict)]
    eligible = sum(1 for wallet in wallets if wallet["paper_readiness_status"] == "eligible_for_manual_paper_simulation_review")
    not_ready = len(wallets) - eligible
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "paper_simulation_enabled": False,
        "live_execution_locked": True,
        "promotion_allowed": False,
        "wallet_list_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "auto_trust_mutation_allowed": False,
        "wallet_list_mutated": False,
        "gate_config": cfg,
        "summary": {
            "wallets_evaluated": len(wallets),
            "eligible_for_manual_paper_simulation_review": eligible,
            "not_ready_wallets": not_ready,
            "paper_simulation_enabled": False,
            "promotions_allowed": 0,
            "wallet_list_mutations": 0,
            "wallet_trust_mutations": 0,
            "auto_trust_mutations": 0,
        },
        "wallets": wallets,
        "operator_note": (
            "This gate only determines whether a candidate can be manually reviewed for paper simulation. "
            "It does not start paper simulation, place trades, promote wallets, or mutate wallet trust."
        ),
    }
