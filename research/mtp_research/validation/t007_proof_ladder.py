"""Formal T007 proof ladder.

The ladder separates implementation completeness from live production evidence.
No strategy, wallet, paper-trading, or execution logic belongs here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

L0_COMPILE = "L0_COMPILE"
L1_DETERMINISTIC_FIXTURES = "L1_DETERMINISTIC_FIXTURES"
L2_LIVE_NO_MIGRATION_PROOF = "L2_LIVE_NO_MIGRATION_PROOF"
L3_CONTROLLED_MIGRATION_PROOF = "L3_CONTROLLED_MIGRATION_PROOF"

@dataclass(frozen=True)
class ProofLevelResult:
    level: str
    passed: bool
    blockers: tuple[str, ...]
    evidence: dict[str, Any]


def evaluate_l0_compile(evidence: Mapping[str, Any]) -> ProofLevelResult:
    blockers = []
    if not evidence.get("py_compile_passed"):
        blockers.append("py_compile_not_passed")
    if evidence.get("import_errors"):
        blockers.append("import_errors_present")
    if not evidence.get("schema_migration_clean", False):
        blockers.append("schema_migration_not_proven")
    return ProofLevelResult(L0_COMPILE, not blockers, tuple(blockers), dict(evidence))


def evaluate_l1_fixtures(evidence: Mapping[str, Any]) -> ProofLevelResult:
    required = (
        "golden_birth_fixture_passed",
        "rejected_birth_fixture_passed",
        "curve_decode_fixture_passed",
        "pumpswap_pool_fixture_passed",
        "quote_depth_fixture_passed",
    )
    blockers = [f"missing_or_failed:{name}" for name in required if not evidence.get(name)]
    return ProofLevelResult(L1_DETERMINISTIC_FIXTURES, not blockers, tuple(blockers), dict(evidence))


def evaluate_l2_live_no_migration(summary: Mapping[str, Any]) -> ProofLevelResult:
    blockers = []
    if not summary.get("event_first_sqlite_enabled"):
        blockers.append("event_first_sqlite_not_enabled")
    if not summary.get("db_ledger_consistent", True):
        blockers.append("db_ledger_inconsistent")
    if int(summary.get("queue_dropped_total") or summary.get("queue_dropped") or 0) > 0:
        blockers.append("queue_dropped")
    if int(summary.get("verified_births") or 0) == 0:
        blockers.append("no_verified_births")
    if int(summary.get("curve_state_decoded") or summary.get("progress_decoded_count") or 0) == 0:
        blockers.append("no_curve_state_decoded")
    if int(summary.get("market_cap_available") or summary.get("market_cap_progress_count") or 0) == 0:
        blockers.append("no_market_cap_progress")
    if not summary.get("required_watcher_fields_present", False):
        blockers.append("watcher_contract_incomplete")
    return ProofLevelResult(L2_LIVE_NO_MIGRATION_PROOF, not blockers, tuple(blockers), dict(summary))


def evaluate_l3_controlled_migration(summary: Mapping[str, Any]) -> ProofLevelResult:
    blockers = list(evaluate_l2_live_no_migration(summary).blockers)
    if int(summary.get("global_migration_mints_seen") or summary.get("global_migrations_seen") or 0) == 0:
        blockers.append("no_global_migrations_seen")
    if int(summary.get("decision_safe_full_paths") or summary.get("migrations_with_decision_safe_full_path") or 0) == 0:
        blockers.append("no_decision_safe_full_path_migrations")
    if int(summary.get("quote_ready_verified") or 0) == 0:
        blockers.append("no_strict_quote_ready_migration")
    return ProofLevelResult(L3_CONTROLLED_MIGRATION_PROOF, not blockers, tuple(sorted(set(blockers))), dict(summary))


def highest_passed_level(results: list[ProofLevelResult]) -> str | None:
    passed = [result.level for result in results if result.passed]
    return passed[-1] if passed else None
