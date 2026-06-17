"""T007AT PumpSwap fee/formula confirmation report.

This module is offline analysis only. It does not stream, trade, paper trade,
build transactions, sign, use wallets, or send orders.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from statistics import median
from typing import Any

from research.mtp_research.collectors.bonding_curve_progress_recorder_v1 import evaluate_t007_thesis_ready_gate


SEARCH_TERMS = (
    "PumpSwap",
    "pAMM",
    "fee_bps",
    "lp_fee",
    "protocol_fee",
    "creator_fee",
    "constant_product",
    "quote_amount",
    "base_reserve",
    "quote_reserve",
    "ceilDiv",
    "floor",
    "rounding",
    "swap",
)
ARCHIVE_NAMES = (
    "trade_flow_events.jsonl",
    "global_migration_events.jsonl",
    "post_migration_observations.jsonl",
    "executable_quote_observations.jsonl",
    "pumpswap_route_candidates.jsonl",
)


def classify_quote_math_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    formula_confirmed = bool(evidence.get("formula_source_confirmed"))
    fee_complete = bool(evidence.get("fee_model_complete"))
    replay_passed = bool(evidence.get("replay_validation_passed"))
    rounding_confirmed = bool(evidence.get("rounding_confirmed"))
    if formula_confirmed and fee_complete and replay_passed and rounding_confirmed:
        return {
            "fee_model_status": "confirmed",
            "quote_confidence": "high",
            "confirmed": True,
            "reason": "formula_fee_rounding_and_replay_confirmed",
            "lp_fee_bps": evidence.get("lp_fee_bps"),
            "protocol_fee_bps": evidence.get("protocol_fee_bps"),
            "creator_fee_bps": evidence.get("creator_fee_bps"),
        }
    if formula_confirmed and replay_passed and bool(evidence.get("allow_assumed")):
        return {
            "fee_model_status": "assumed",
            "quote_confidence": "medium",
            "confirmed": False,
            "reason": "formula_likely_but_fee_or_rounding_not_fully_confirmed",
            "lp_fee_bps": evidence.get("lp_fee_bps"),
            "protocol_fee_bps": evidence.get("protocol_fee_bps"),
            "creator_fee_bps": evidence.get("creator_fee_bps"),
        }
    return {
        "fee_model_status": "unknown",
        "quote_confidence": "low",
        "confirmed": False,
        "reason": "missing_required_source_fee_or_replay_confirmation",
        "lp_fee_bps": evidence.get("lp_fee_bps"),
        "protocol_fee_bps": evidence.get("protocol_fee_bps"),
        "creator_fee_bps": evidence.get("creator_fee_bps"),
    }


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = sorted({key for row in rows for key in row})
    if not fieldnames:
        fieldnames = ["status"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def build_swap_replay_validation_row(candidate: dict[str, Any], *, fee_bps_candidate: float = 0.0) -> dict[str, Any]:
    observed_output = _float(candidate.get("output_amount_observed"))
    input_amount = _float(candidate.get("input_amount_observed"))
    reserve_base = _float(candidate.get("reserve_base_before"))
    reserve_quote = _float(candidate.get("reserve_quote_before"))
    row = {
        "signature": candidate.get("signature"),
        "pool": candidate.get("pool"),
        "mint": candidate.get("mint"),
        "quote_asset": candidate.get("quote_asset"),
        "direction": candidate.get("direction"),
        "input_amount_observed": input_amount,
        "output_amount_observed": observed_output,
        "reserve_base_before": reserve_base,
        "reserve_quote_before": reserve_quote,
        "fee_bps_candidate": fee_bps_candidate,
        "predicted_output_no_fee": None,
        "predicted_output_with_candidate_fee": None,
        "absolute_error": None,
        "relative_error_pct": None,
        "rounding_error_units": None,
        "validation_status": "fail",
        "failure_reason": "",
    }
    if not all(value is not None and value > 0 for value in (observed_output, input_amount, reserve_base, reserve_quote)):
        row["failure_reason"] = "missing_observed_amounts_or_reserves"
        return row
    predicted_no_fee = _constant_product_exit_quote(input_amount, reserve_base, reserve_quote, fee_bps=0.0)
    predicted_with_fee = _constant_product_exit_quote(input_amount, reserve_base, reserve_quote, fee_bps=fee_bps_candidate)
    error = abs(predicted_with_fee - observed_output)
    relative_error = (error / observed_output) * 100.0 if observed_output else None
    row.update(
        {
            "predicted_output_no_fee": predicted_no_fee,
            "predicted_output_with_candidate_fee": predicted_with_fee,
            "absolute_error": error,
            "relative_error_pct": relative_error,
            "rounding_error_units": error,
            "validation_status": "pass" if relative_error is not None and relative_error <= 0.10 else "fail",
            "failure_reason": "" if relative_error is not None and relative_error <= 0.10 else "relative_error_above_tolerance",
        }
    )
    return row


def _constant_product_exit_quote(input_token: float, reserve_base: float, reserve_quote: float, *, fee_bps: float = 0.0) -> float:
    effective_input = input_token * max(0.0, 1.0 - (float(fee_bps) / 10_000.0))
    invariant = reserve_base * reserve_quote
    return reserve_quote - (invariant / (reserve_base + effective_input))


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_repo_source_inventory(repo_root: Path) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    allowed_suffixes = {".py", ".ts", ".tsx", ".js", ".json", ".md", ".yaml", ".yml", ".toml", ".rs"}
    skip_parts = {".git", ".runtime", "outputs", "__pycache__", "node_modules", ".venv"}
    for path in repo_root.rglob("*"):
        if not path.is_file() or path.suffix not in allowed_suffixes:
            continue
        if any(part in skip_parts for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        hits = [term for term in SEARCH_TERMS if term.lower() in text.lower()]
        if not hits:
            continue
        rel = str(path.relative_to(repo_root))
        lower_rel = rel.lower()
        trusted = any(token in lower_rel for token in ("idl", "sdk", "official", "vendor/pumpswap", "pumpswap-sdk"))
        confirms_formula = any(term in hits for term in ("constant_product", "base_reserve", "quote_reserve"))
        confirms_fees = any(term in hits for term in ("fee_bps", "lp_fee", "protocol_fee", "creator_fee"))
        confirms_rounding = any(term in hits for term in ("ceilDiv", "floor", "rounding"))
        inventory.append(
            {
                "file": rel,
                "relevant_symbols": ", ".join(hits),
                "trusted_source": trusted,
                "confirms_formula": confirms_formula,
                "confirms_fees": confirms_fees,
                "confirms_rounding": confirms_rounding,
            }
        )
    return inventory


def extract_swap_replay_candidates(archive_roots: list[Path]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for root in archive_roots:
        for name in ARCHIVE_NAMES:
            for row in _jsonl(root / name):
                signature = row.get("signature")
                mint = row.get("mint")
                if not signature or not mint:
                    continue
                side = row.get("side") or row.get("quote_direction")
                input_amount = row.get("token_amount") if side in {"sell", "exit_token_to_quote"} else row.get("quote_amount")
                output_amount = row.get("quote_amount") if side in {"sell", "exit_token_to_quote"} else row.get("token_amount")
                pool = row.get("pool_or_pair_address") or row.get("pool")
                candidates.append(
                    {
                        "archive_root": str(root),
                        "source_artifact": name,
                        "signature": signature,
                        "mint": mint,
                        "pool": pool,
                        "side": side,
                        "direction": "exit_token_to_quote" if side in {"sell", "exit_token_to_quote"} else "entry_quote_to_token" if side == "buy" else "",
                        "input_mint": row.get("base_mint") or mint,
                        "output_mint": row.get("quote_mint"),
                        "input_amount": input_amount,
                        "output_amount": output_amount,
                        "quote_asset": row.get("quote_asset"),
                        "slot": row.get("slot") or row.get("observation_slot"),
                        "timestamp": row.get("received_at") or row.get("observation_received_at"),
                        "reserve_base_before": row.get("pool_base_reserve") or row.get("pool_base_reserve_scaled"),
                        "reserve_quote_before": row.get("pool_quote_reserve") or row.get("pool_quote_reserve_scaled"),
                        "candidate_status": _candidate_status(row, name),
                    }
                )
    return candidates


def _candidate_status(row: dict[str, Any], artifact: str) -> str:
    if artifact == "trade_flow_events.jsonl":
        return "trade_flow_has_amounts_but_not_confirmed_pumpswap_pool_swap"
    if not row.get("signature"):
        return "missing_signature"
    if str(row.get("signature", "")).startswith("program-subscribe:"):
        return "program_subscribe_pool_create_not_swap"
    return "insufficient_swap_delta_context"


def build_fee_model_comparison(validation_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    models = [("no_fee", 0.0)]
    rows: list[dict[str, Any]] = []
    for name, fee_bps in models:
        errors = [
            float(row["relative_error_pct"])
            for row in validation_rows
            if row.get("fee_bps_candidate") == fee_bps and row.get("relative_error_pct") not in (None, "")
        ]
        rows.append(
            {
                "candidate_model": name,
                "fee_bps_candidate": fee_bps,
                "swap_rows_tested": len(errors),
                "median_relative_error_pct": median(errors) if errors else None,
                "p90_relative_error_pct": _percentile(errors, 0.90) if errors else None,
                "max_relative_error_pct": max(errors) if errors else None,
                "pass_fail": "pass" if errors and max(errors) <= 0.10 else "fail",
                "mismatch_likely_reason": "no_observed_pumpswap_swap_delta_rows" if not errors else "unknown",
            }
        )
    return rows


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    idx = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * q))))
    return ordered[idx]


def write_t007at_fee_formula_confirmation_report(repo_root: Path, archive_roots: list[Path], output_root: Path) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    inventory = build_repo_source_inventory(repo_root)
    candidates = extract_swap_replay_candidates(archive_roots)
    replay_candidates = [
        {
            "signature": row.get("signature"),
            "pool": row.get("pool"),
            "mint": row.get("mint"),
            "quote_asset": row.get("quote_asset"),
            "direction": row.get("direction"),
            "input_amount_observed": row.get("input_amount"),
            "output_amount_observed": row.get("output_amount"),
            "reserve_base_before": row.get("reserve_base_before"),
            "reserve_quote_before": row.get("reserve_quote_before"),
        }
        for row in candidates
        if row.get("candidate_status") == "ready_for_formula_validation"
    ]
    validation_rows = [build_swap_replay_validation_row(row, fee_bps_candidate=0.0) for row in replay_candidates]
    fee_comparison = build_fee_model_comparison(validation_rows)
    source_confirms_formula = any(row["trusted_source"] and row["confirms_formula"] for row in inventory)
    source_confirms_fee = any(row["trusted_source"] and row["confirms_fees"] for row in inventory)
    source_confirms_rounding = any(row["trusted_source"] and row["confirms_rounding"] for row in inventory)
    replay_passed = bool(validation_rows) and all(row.get("validation_status") == "pass" for row in validation_rows)
    status = classify_quote_math_evidence(
        {
            "formula_source_confirmed": source_confirms_formula,
            "fee_model_complete": source_confirms_fee,
            "rounding_confirmed": source_confirms_rounding,
            "replay_validation_passed": replay_passed,
            "allow_assumed": source_confirms_formula and bool(validation_rows),
        }
    )
    gate = evaluate_t007_thesis_ready_gate(
        {
            "unique_birth_mints": 1,
            "progress_decoded_exact_count": 1,
            "true_curve_threshold_crossings_written": 1,
            "curve_velocity_events_written": 1,
            "curve_acceleration_events_written": 1,
            "trade_flow_events_written": 1,
            "buyer_breadth_available_count": 1,
            "global_migration_events": 1,
            "token_path_summary_rows": 1,
            "decision_time_safety_violation_count": 0,
            "organic_flow_events_written": 1,
            "holder_distribution_snapshots_written": 1,
            "dev_behavior_events_written": 1,
            "post_migration_observations_written": 1,
            "execution_cost_observations_written": 1,
            "valuation_ladder_emission_policy": "market_cap_confirmed_only",
            "pool_liquidity_quote_present_count": 1,
            "pool_liquidity_usd_present_count": 1,
            "executable_quote_observations_written": 1,
            "price_impact_available_count": 1,
            "executable_quote_decision_time_safe_count": 1,
            f"fee_model_{status['fee_model_status']}_count": 1,
            "valid_60m_thesis_collection_passed": False,
        },
        thesis_scope="full_post_migration_exit_depth",
    )
    _write_repo_inventory_md(output_root / "repo_source_inventory.md", inventory)
    _write_csv(output_root / "swap_replay_candidates.csv", candidates)
    _write_csv(output_root / "swap_replay_validation.csv", validation_rows, fieldnames=[
        "signature", "pool", "mint", "quote_asset", "direction", "input_amount_observed", "output_amount_observed",
        "reserve_base_before", "reserve_quote_before", "predicted_output_no_fee", "predicted_output_with_candidate_fee",
        "fee_bps_candidate", "absolute_error", "relative_error_pct", "rounding_error_units", "validation_status", "failure_reason",
    ])
    _write_csv(output_root / "fee_model_comparison.csv", fee_comparison)
    (output_root / "readiness_gate_after_t007at.json").write_text(json.dumps(gate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    status_payload = {
        **status,
        "source_confirms_formula": source_confirms_formula,
        "source_confirms_fee": source_confirms_fee,
        "source_confirms_rounding": source_confirms_rounding,
        "swap_replay_candidates": len(candidates),
        "swap_replay_rows_tested": len(validation_rows),
        "live_scan_ran": False,
        "valuation_ladder_suppressed": True,
        "mayhem_files_modified": False,
        "trading_paper_wallet_signing_execution_untouched": True,
    }
    (output_root / "quote_math_status.json").write_text(json.dumps(status_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_summary_md(output_root / "summary.md", status_payload, gate, fee_comparison)
    return status_payload


def _write_repo_inventory_md(path: Path, inventory: list[dict[str, Any]]) -> None:
    lines = [
        "# T007AT Repo Source Inventory",
        "",
        "| file | relevant symbols | trusted | confirms formula | confirms fees | confirms rounding |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in inventory:
        lines.append(
            f"| `{row['file']}` | {row['relevant_symbols']} | {row['trusted_source']} | {row['confirms_formula']} | {row['confirms_fees']} | {row['confirms_rounding']} |"
        )
    if not inventory:
        lines.append("| none | none | false | false | false | false |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_summary_md(path: Path, status: dict[str, Any], gate: dict[str, Any], fee_comparison: list[dict[str, Any]]) -> None:
    lines = [
        "# T007AT PumpSwap Fee/Formula Confirmation",
        "",
        "No live scan was run. No trading, paper trading, wallet, signing, or execution code was used.",
        "",
        f"- Fee model status: `{status.get('fee_model_status')}`",
        f"- Quote confidence: `{status.get('quote_confidence')}`",
        f"- Source confirms formula: `{status.get('source_confirms_formula')}`",
        f"- Source confirms fees: `{status.get('source_confirms_fee')}`",
        f"- Source confirms rounding: `{status.get('source_confirms_rounding')}`",
        f"- Swap replay candidates: `{status.get('swap_replay_candidates')}`",
        f"- Swap replay rows tested: `{status.get('swap_replay_rows_tested')}`",
        f"- Gate quote depth status: `{gate.get('quote_depth_status')}`",
        f"- Gate allowed scan scope: `{gate.get('allowed_scan_scope')}`",
        f"- 60m thesis scan allowed: `{gate.get('can_run_60m_thesis_scan')}`",
        f"- 2h+ scan allowed: `{gate.get('can_run_2h_plus_scan')}`",
        "",
        "## Fee model comparison",
        "",
        "| model | rows tested | median relative error pct | p90 relative error pct | max relative error pct | pass/fail |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in fee_comparison:
        lines.append(
            f"| {row.get('candidate_model')} | {row.get('swap_rows_tested')} | {row.get('median_relative_error_pct')} | {row.get('p90_relative_error_pct')} | {row.get('max_relative_error_pct')} | {row.get('pass_fail')} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
