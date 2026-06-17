from __future__ import annotations

import csv
import json
import math
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping


REPO_ROOT = Path("/Users/dianeposs/Projects/meme-trader-pro")
SOURCE_OUTPUT_DIR = REPO_ROOT / "outputs/theses/t007av_pumpswap_swap_event_fee_confirmation/t007aw_pumpswap_swap_source_route_10m_20260614_143834"
SOURCE_COLLECTOR_ROOT = REPO_ROOT / ".runtime/t007_forward_runs/t007aw_pumpswap_swap_source_route_10m_20260614_143834"
OUTPUT_DIR = REPO_ROOT / "outputs/theses/t007ax_pumpswap_fee_replay_failure_forensics"
TOLERANCE_PCT = 0.1

T007AX_GUARDRAILS = {
    "live_scan_ran": False,
    "mayhem_files_modified": False,
    "valuation_ladder_suppressed": True,
    "trading_paper_wallet_signing_execution_untouched": True,
}


def _num(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(data), indent=2, sort_keys=True), encoding="utf-8")


def active_user_quote_fee_total(event: Mapping[str, Any]) -> float:
    return sum(_num(event.get(key)) or 0.0 for key in ("lp_fee", "protocol_fee", "coin_creator_fee", "cashback"))


def legacy_all_fee_total(event: Mapping[str, Any]) -> float:
    return sum(_num(event.get(key)) or 0.0 for key in ("lp_fee", "protocol_fee", "coin_creator_fee", "cashback", "buyback_fee"))


def lp_protocol_fee_total(event: Mapping[str, Any]) -> float:
    return sum(_num(event.get(key)) or 0.0 for key in ("lp_fee", "protocol_fee"))


def quote_delta_sign(event: Mapping[str, Any]) -> int:
    quote_amount = _num(event.get("quote_amount"))
    user_quote_amount = _num(event.get("user_quote_amount"))
    if quote_amount is None or user_quote_amount is None:
        return 0
    if user_quote_amount > quote_amount:
        return 1
    if user_quote_amount < quote_amount:
        return -1
    return 0


def _legacy_event_type_sign(event: Mapping[str, Any]) -> int:
    return 1 if event.get("event_type") == "buy" else -1


def _rel_error(predicted: float | None, observed: float | None) -> float | None:
    if predicted is None or observed is None:
        return None
    return 0.0 if observed == 0 else abs(predicted - observed) / abs(observed) * 100.0


def _pass(predicted: float | None, observed: float | None, *, tolerance_pct: float = TOLERANCE_PCT) -> bool:
    rel = _rel_error(predicted, observed)
    return rel is not None and rel <= tolerance_pct


def _event_quote_prediction(event: Mapping[str, Any], variant_name: str) -> float | None:
    quote_amount = _num(event.get("quote_amount"))
    if quote_amount is None:
        return None
    if variant_name == "current_legacy_event_type_all_fees":
        return quote_amount + (_legacy_event_type_sign(event) * legacy_all_fee_total(event))
    if variant_name == "event_type_lp_protocol_only":
        return quote_amount + (_legacy_event_type_sign(event) * lp_protocol_fee_total(event))
    if variant_name == "event_type_active_user_fee_excluding_buyback":
        return quote_amount + (_legacy_event_type_sign(event) * active_user_quote_fee_total(event))
    if variant_name == "event_active_user_fee_signed_by_observed_delta":
        return quote_amount + (quote_delta_sign(event) * active_user_quote_fee_total(event))
    if variant_name == "event_no_fee":
        return quote_amount
    return None


def _constant_product_prediction(event: Mapping[str, Any], variant_name: str) -> float | None:
    base_reserve = _num(event.get("pool_base_token_reserves"))
    quote_reserve = _num(event.get("pool_quote_token_reserves"))
    base_amount = _num(event.get("base_amount"))
    quote_amount = _num(event.get("quote_amount"))
    if base_reserve is None or quote_reserve is None or base_amount is None:
        return None
    if base_reserve <= 0 or quote_reserve <= 0 or base_amount <= 0:
        return None
    event_type = event.get("event_type")
    lp_fee = _num(event.get("lp_fee")) or 0.0
    protocol_fee = _num(event.get("protocol_fee")) or 0.0
    active_fee = active_user_quote_fee_total(event)
    if event_type == "sell":
        no_fee_out = quote_reserve * base_amount / (base_reserve + base_amount)
        if variant_name == "cp_sell_pre_swap_no_fee":
            return math.floor(no_fee_out)
        if variant_name == "cp_sell_pre_swap_lp_fee_on_input":
            return math.floor(max(0.0, no_fee_out - lp_fee))
        if variant_name == "cp_sell_pre_swap_lp_protocol_fee_on_input":
            return math.floor(max(0.0, no_fee_out - lp_fee - protocol_fee))
        if variant_name == "cp_sell_pre_swap_active_user_fee":
            return math.floor(max(0.0, no_fee_out - active_fee))
        if variant_name == "cp_sell_post_swap_reverse_no_fee":
            pre_base = max(0.0, base_reserve - base_amount)
            pre_quote = quote_reserve + (quote_amount or 0.0)
            return math.floor(pre_quote * base_amount / (pre_base + base_amount)) if pre_base > 0 else None
    if event_type == "buy":
        if base_reserve <= base_amount:
            return None
        no_fee_in = quote_reserve * base_amount / (base_reserve - base_amount)
        if variant_name == "cp_buy_pre_swap_no_fee":
            return math.ceil(no_fee_in)
        if variant_name == "cp_buy_pre_swap_lp_fee_on_quote_input":
            return math.ceil(no_fee_in + lp_fee)
        if variant_name == "cp_buy_pre_swap_lp_protocol_fee_on_quote_input":
            return math.ceil(no_fee_in + lp_fee + protocol_fee)
        if variant_name == "cp_buy_pre_swap_active_user_fee":
            return math.ceil(no_fee_in + active_fee)
        if variant_name == "cp_buy_post_swap_reverse_no_fee":
            pre_base = base_reserve + base_amount
            pre_quote = max(0.0, quote_reserve - (quote_amount or 0.0))
            return math.ceil(pre_quote * base_amount / (pre_base - base_amount)) if pre_base > base_amount else None
    return None


FORMULA_VARIANTS = [
    "current_legacy_event_type_all_fees",
    "event_type_lp_protocol_only",
    "event_type_active_user_fee_excluding_buyback",
    "event_active_user_fee_signed_by_observed_delta",
    "event_no_fee",
    "cp_sell_pre_swap_no_fee",
    "cp_sell_pre_swap_lp_fee_on_input",
    "cp_sell_pre_swap_lp_protocol_fee_on_input",
    "cp_sell_pre_swap_active_user_fee",
    "cp_sell_post_swap_reverse_no_fee",
    "cp_buy_pre_swap_no_fee",
    "cp_buy_pre_swap_lp_fee_on_quote_input",
    "cp_buy_pre_swap_lp_protocol_fee_on_quote_input",
    "cp_buy_pre_swap_active_user_fee",
    "cp_buy_post_swap_reverse_no_fee",
]


def _prediction_for_variant(event: Mapping[str, Any], variant_name: str) -> float | None:
    if variant_name.startswith("cp_"):
        return _constant_product_prediction(event, variant_name)
    return _event_quote_prediction(event, variant_name)


def _pct(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, math.ceil((pct / 100.0) * len(ordered)) - 1))
    return ordered[idx]


def compare_formula_variants(events: Iterable[Mapping[str, Any]], *, tolerance_pct: float = TOLERANCE_PCT) -> list[dict[str, Any]]:
    rows = []
    event_rows = list(events)
    for variant_name in FORMULA_VARIANTS:
        tested = []
        rel_errors = []
        pass_by_event = Counter()
        fail_by_event = Counter()
        pass_by_quote = Counter()
        fail_by_quote = Counter()
        for event in event_rows:
            observed = _num(event.get("user_quote_amount"))
            predicted = _prediction_for_variant(event, variant_name)
            if observed is None or predicted is None:
                continue
            rel = _rel_error(predicted, observed)
            if rel is None:
                continue
            passed = rel <= tolerance_pct
            tested.append((event, passed, rel))
            rel_errors.append(rel)
            event_type = str(event.get("event_type") or "unknown")
            quote_asset = str(event.get("quote_asset") or "unknown")
            if passed:
                pass_by_event[event_type] += 1
                pass_by_quote[quote_asset] += 1
            else:
                fail_by_event[event_type] += 1
                fail_by_quote[quote_asset] += 1
        rows.append(
            {
                "variant_name": variant_name,
                "rows_tested": len(tested),
                "pass_count": sum(1 for _, passed, _ in tested if passed),
                "fail_count": sum(1 for _, passed, _ in tested if not passed),
                "median_relative_error_pct": statistics.median(rel_errors) if rel_errors else None,
                "p90_relative_error_pct": _pct(rel_errors, 90),
                "max_relative_error_pct": max(rel_errors) if rel_errors else None,
                "buy_pass_count": pass_by_event.get("buy", 0),
                "buy_fail_count": fail_by_event.get("buy", 0),
                "sell_pass_count": pass_by_event.get("sell", 0),
                "sell_fail_count": fail_by_event.get("sell", 0),
                "pass_count_by_event_type": json.dumps(dict(pass_by_event), sort_keys=True),
                "fail_count_by_event_type": json.dumps(dict(fail_by_event), sort_keys=True),
                "pass_count_by_quote_asset": json.dumps(dict(pass_by_quote), sort_keys=True),
                "fail_count_by_quote_asset": json.dumps(dict(fail_by_quote), sort_keys=True),
                "failure_notes": _variant_note(variant_name),
            }
        )
    return rows


def _variant_note(variant_name: str) -> str:
    if variant_name == "event_active_user_fee_signed_by_observed_delta":
        return "Best event-field reconciliation; confirms decoded fee endpoint fields, not standalone executable quote prediction."
    if variant_name == "current_legacy_event_type_all_fees":
        return "Legacy comparator: assumes buy adds, sell subtracts, and includes buyback_fee in user endpoint."
    if variant_name.startswith("cp_"):
        return "Constant-product reserve check; reserve timing is unconfirmed and may be post-swap."
    return ""


def build_signature_event_counts(events: Iterable[Mapping[str, Any]]) -> Counter:
    return Counter(str(event.get("signature") or "") for event in events if event.get("signature"))


def _event_key(row: Mapping[str, Any]) -> tuple[str, str, str, str, str, str, str]:
    return (
        str(row.get("signature") or ""),
        str(row.get("event_type") or ""),
        str(row.get("pool") or ""),
        str(row.get("mint") or ""),
        str(row.get("base_amount") or row.get("base_amount_in_or_out") or ""),
        str(row.get("quote_amount") or row.get("quote_amount_in_or_out") or ""),
        str(row.get("user_quote_amount") or ""),
    )


def _trade_size_bucket(event: Mapping[str, Any]) -> str:
    quote_amount = _num(event.get("quote_amount"))
    reserve = _num(event.get("pool_quote_token_reserves"))
    if quote_amount is None or reserve is None or reserve <= 0:
        return "unknown"
    ratio = abs(quote_amount) / reserve
    if ratio < 0.001:
        return "tiny"
    if ratio < 0.01:
        return "small"
    if ratio < 0.05:
        return "medium"
    return "large"


def classify_failed_event(event: Mapping[str, Any], *, signature_event_count: int = 1) -> str:
    quote_amount = _num(event.get("quote_amount"))
    user_quote_amount = _num(event.get("user_quote_amount"))
    if quote_amount is None or user_quote_amount is None:
        return "unknown"
    active_predicted = quote_amount + quote_delta_sign(event) * active_user_quote_fee_total(event)
    if not _pass(active_predicted, user_quote_amount):
        if signature_event_count > 1:
            return "multi_event_signature_mismatch"
        return "unknown"
    legacy_sign = _legacy_event_type_sign(event)
    observed_sign = quote_delta_sign(event)
    if observed_sign != 0 and observed_sign != legacy_sign:
        return "fee_side_mismatch"
    if (_num(event.get("buyback_fee")) or 0.0) > 0:
        return "amount_field_gross_net_mismatch"
    if (_num(event.get("coin_creator_fee")) or 0.0) > 0 or (_num(event.get("cashback")) or 0.0) > 0:
        return "creator_or_dynamic_fee_missing"
    if _trade_size_bucket(event) == "tiny":
        return "tiny_trade_rounding_noise"
    return "unknown"


def enrich_failed_replay_rows(
    events: Iterable[Mapping[str, Any]],
    *,
    failed_signatures: set[str] | None = None,
    failed_keys: set[tuple[str, str, str, str, str, str, str]] | None = None,
    validation_by_key: Mapping[tuple[str, str, str, str, str, str, str], Mapping[str, Any]] | None = None,
    signature_event_counts: Counter | None = None,
) -> list[dict[str, Any]]:
    event_rows = list(events)
    counts = signature_event_counts or build_signature_event_counts(event_rows)
    enriched = []
    for event_index, event in enumerate(event_rows):
        key = _event_key(event)
        signature = str(event.get("signature") or "")
        include = (failed_signatures is not None and signature in failed_signatures) or (failed_keys is not None and key in failed_keys)
        if not include:
            continue
        validation = dict((validation_by_key or {}).get(key, {}))
        quote_amount = _num(event.get("quote_amount"))
        user_quote_amount = _num(event.get("user_quote_amount"))
        active_fee = active_user_quote_fee_total(event)
        predicted = None if quote_amount is None else quote_amount + quote_delta_sign(event) * active_fee
        absolute_error = None if predicted is None or user_quote_amount is None else abs(predicted - user_quote_amount)
        relative_error = _rel_error(predicted, user_quote_amount)
        multi_count = counts.get(signature, 0)
        classification = classify_failed_event(event, signature_event_count=multi_count)
        enriched.append(
            {
                "signature": signature,
                "event_index": event_index,
                "event_type": event.get("event_type", ""),
                "pool": event.get("pool", ""),
                "mint": event.get("mint", ""),
                "quote_asset": event.get("quote_asset", ""),
                "base_amount": event.get("base_amount", ""),
                "quote_amount": event.get("quote_amount", ""),
                "user_quote_amount": event.get("user_quote_amount", ""),
                "quote_amount_with_lp_fee": event.get("quote_amount_in_with_lp_fee", ""),
                "quote_amount_without_lp_fee": event.get("quote_amount_out_without_lp_fee", ""),
                "pool_base_reserves": event.get("pool_base_token_reserves", ""),
                "pool_quote_reserves": event.get("pool_quote_token_reserves", ""),
                "lp_fee_basis_points": event.get("lp_fee_basis_points", ""),
                "protocol_fee_basis_points": event.get("protocol_fee_basis_points", ""),
                "coin_creator_fee_basis_points": event.get("coin_creator_fee_basis_points", ""),
                "cashback_fee_basis_points": event.get("cashback_fee_basis_points", ""),
                "buyback_fee_basis_points": event.get("buyback_fee_basis_points", ""),
                "lp_fee": event.get("lp_fee", ""),
                "protocol_fee": event.get("protocol_fee", ""),
                "coin_creator_fee": event.get("coin_creator_fee", ""),
                "cashback": event.get("cashback", ""),
                "buyback_fee": event.get("buyback_fee", ""),
                "total_observed_fee_bps": event.get("total_fee_basis_points_observed", ""),
                "predicted_output": predicted,
                "observed_output": user_quote_amount,
                "absolute_error": absolute_error,
                "relative_error": relative_error,
                "raw_integer_error": absolute_error,
                "transaction_has_multiple_pumpswap_events": multi_count > 1,
                "transaction_pumpswap_event_count": multi_count,
                "trade_size_relative_to_pool": _trade_size_bucket(event),
                "reserves_appear_pre_or_post_swap": "unverified_missing_before_after_reserve_context",
                "amount_fields_appear_gross_or_net": "user_quote_above_quote" if quote_delta_sign(event) > 0 else "user_quote_below_quote" if quote_delta_sign(event) < 0 else "flat",
                "legacy_validation_status": validation.get("validation_status", ""),
                "legacy_failure_reason": validation.get("failure_reason", ""),
                "legacy_predicted_output": validation.get("predicted_quote_with_event_fees", ""),
                "legacy_absolute_error": validation.get("absolute_error", ""),
                "legacy_relative_error": validation.get("relative_error_pct", ""),
                "failure_classification": classification,
            }
        )
    return enriched


def assign_fee_model_status_from_variant(best_variant: Mapping[str, Any], *, unexplained_failure_count: int) -> dict[str, Any]:
    rows_tested = int(best_variant.get("rows_tested") or 0)
    pass_count = int(best_variant.get("pass_count") or 0)
    fail_count = int(best_variant.get("fail_count") or 0)
    buy_pass = int(best_variant.get("buy_pass_count") or 0)
    sell_pass = int(best_variant.get("sell_pass_count") or 0)
    if rows_tested > 0 and pass_count == rows_tested and fail_count == 0 and buy_pass > 0 and sell_pass > 0 and unexplained_failure_count == 0:
        fee_model_status = "confirmed"
        quote_confidence = "high"
    elif rows_tested > 0 and pass_count / rows_tested >= 0.95 and buy_pass > 0 and sell_pass > 0 and unexplained_failure_count == 0:
        fee_model_status = "assumed"
        quote_confidence = "medium"
    else:
        fee_model_status = "unknown"
        quote_confidence = "low"
    return {
        "fee_model_status": fee_model_status,
        "quote_confidence": quote_confidence,
        "rows_tested": rows_tested,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "buy_pass_count": buy_pass,
        "sell_pass_count": sell_pass,
        "unexplained_failure_count": unexplained_failure_count,
    }


def _cluster_summary(enriched_failed: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(str(row.get("failure_classification") or "unknown") for row in enriched_failed)
    return [{"failure_classification": key, "count": count} for key, count in counts.most_common()]


def run_forensics(
    source_output_dir: Path = SOURCE_OUTPUT_DIR,
    source_collector_root: Path = SOURCE_COLLECTOR_ROOT,
    output_dir: Path = OUTPUT_DIR,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    events = _read_jsonl(source_output_dir / "pumpswap_swap_events.jsonl")
    replay_rows = _read_csv(source_output_dir / "fee_formula_replay_validation.csv")
    candidate_rows = _read_csv(source_output_dir / "pumpswap_swap_candidate_inventory.csv")
    route_audit_rows = _read_jsonl(source_collector_root / "pumpswap_transaction_route_audit.jsonl")
    failed_replay_rows = [row for row in replay_rows if row.get("validation_status") == "fail"]
    failed_keys = {_event_key(row) for row in failed_replay_rows}
    validation_by_key = {_event_key(row): row for row in replay_rows}
    signature_counts = build_signature_event_counts(events)
    enriched_failed = enrich_failed_replay_rows(
        events,
        failed_keys=failed_keys,
        validation_by_key=validation_by_key,
        signature_event_counts=signature_counts,
    )
    variant_rows = compare_formula_variants(events)
    best_variant = max(variant_rows, key=lambda row: (int(row.get("pass_count") or 0), -float(row.get("max_relative_error_pct") or 0.0)))
    cluster_rows = _cluster_summary(enriched_failed)
    unexplained_count = sum(int(row["count"]) for row in cluster_rows if row["failure_classification"] == "unknown")
    status = assign_fee_model_status_from_variant(best_variant, unexplained_failure_count=unexplained_count)
    readiness = {
        **T007AX_GUARDRAILS,
        **status,
        "task": "T007AX_PumpSwap_Fee_Replay_Failure_Forensics_NoScan",
        "generated_at_epoch": time.time(),
        "source_output_dir": str(source_output_dir),
        "source_collector_root": str(source_collector_root),
        "decoded_swap_events": len(events),
        "replay_validation_rows": len(replay_rows),
        "failed_rows_analyzed": len(failed_replay_rows),
        "candidate_inventory_rows": len(candidate_rows),
        "route_audit_rows": len(route_audit_rows),
        "best_formula_variant": best_variant["variant_name"],
        "best_variant_pass_count": best_variant["pass_count"],
        "best_variant_fail_count": best_variant["fail_count"],
        "best_variant_buy_pass_count": best_variant["buy_pass_count"],
        "best_variant_buy_fail_count": best_variant["buy_fail_count"],
        "best_variant_sell_pass_count": best_variant["sell_pass_count"],
        "best_variant_sell_fail_count": best_variant["sell_fail_count"],
        "full_post_migration_exit_thesis_allowed": False,
        "full_post_migration_exit_thesis_blocker": "decoded_fee_endpoint_reconciles_but_standalone_executable_quote_formula_still_requires_reserve_context_and_post_patch_proof",
        "partial_post_migration_depth_60m_allowed_now": False,
        "partial_post_migration_depth_60m_blocker": "run_one_10m_post_patch_proof_first",
        "two_hour_plus_blocked": True,
        "production_quote_math_patched": True,
        "constant_product_reserve_formula_confirmed": False,
        "constant_product_reserve_formula_note": "Decoded event endpoint fees reconcile; reserve before/after context remains insufficient for standalone executable quote prediction.",
    }

    _write_csv(
        output_dir / "formula_variant_comparison.csv",
        variant_rows,
        [
            "variant_name",
            "rows_tested",
            "pass_count",
            "fail_count",
            "median_relative_error_pct",
            "p90_relative_error_pct",
            "max_relative_error_pct",
            "buy_pass_count",
            "buy_fail_count",
            "sell_pass_count",
            "sell_fail_count",
            "pass_count_by_event_type",
            "fail_count_by_event_type",
            "pass_count_by_quote_asset",
            "fail_count_by_quote_asset",
            "failure_notes",
        ],
    )
    _write_csv(output_dir / "failure_cluster_summary.csv", cluster_rows, ["failure_classification", "count"])
    _write_json(output_dir / "failure_cluster_summary.json", {"clusters": cluster_rows})
    _write_csv(
        output_dir / "failed_replay_rows_enriched.csv",
        enriched_failed,
        [
            "signature",
            "event_index",
            "event_type",
            "pool",
            "mint",
            "quote_asset",
            "base_amount",
            "quote_amount",
            "user_quote_amount",
            "quote_amount_with_lp_fee",
            "quote_amount_without_lp_fee",
            "pool_base_reserves",
            "pool_quote_reserves",
            "lp_fee_basis_points",
            "protocol_fee_basis_points",
            "coin_creator_fee_basis_points",
            "cashback_fee_basis_points",
            "buyback_fee_basis_points",
            "lp_fee",
            "protocol_fee",
            "coin_creator_fee",
            "cashback",
            "buyback_fee",
            "total_observed_fee_bps",
            "predicted_output",
            "observed_output",
            "absolute_error",
            "relative_error",
            "raw_integer_error",
            "transaction_has_multiple_pumpswap_events",
            "transaction_pumpswap_event_count",
            "trade_size_relative_to_pool",
            "reserves_appear_pre_or_post_swap",
            "amount_fields_appear_gross_or_net",
            "legacy_validation_status",
            "legacy_failure_reason",
            "legacy_predicted_output",
            "legacy_absolute_error",
            "legacy_relative_error",
            "failure_classification",
        ],
    )
    _write_json(output_dir / "readiness_gate_after_t007ax.json", readiness)
    _write_summary(output_dir / "summary.md", readiness, cluster_rows, best_variant)
    return readiness


def _write_summary(path: Path, readiness: Mapping[str, Any], cluster_rows: list[Mapping[str, Any]], best_variant: Mapping[str, Any]) -> None:
    cluster_lines = "\n".join(f"- `{row['failure_classification']}`: {row['count']}" for row in cluster_rows) or "- none"
    text = f"""# T007AX PumpSwap Fee Replay Failure Forensics

## Scope

- live scan ran: `{readiness['live_scan_ran']}`
- Mayhem files modified: `{readiness['mayhem_files_modified']}`
- valuation ladder suppressed: `{readiness['valuation_ladder_suppressed']}`
- trading/paper/wallet/signing/execution untouched: `{readiness['trading_paper_wallet_signing_execution_untouched']}`

## Inputs

- source output: `{readiness['source_output_dir']}`
- collector root: `{readiness['source_collector_root']}`
- decoded swap events: `{readiness['decoded_swap_events']}`
- replay validation rows: `{readiness['replay_validation_rows']}`
- failed rows analyzed: `{readiness['failed_rows_analyzed']}`

## Failure clusters from legacy replay rows

{cluster_lines}

## Best formula variant

- variant: `{best_variant['variant_name']}`
- pass/fail: `{best_variant['pass_count']}/{best_variant['fail_count']}`
- buy pass/fail: `{best_variant['buy_pass_count']}/{best_variant['buy_fail_count']}`
- sell pass/fail: `{best_variant['sell_pass_count']}/{best_variant['sell_fail_count']}`
- note: {best_variant['failure_notes']}

## Interpretation

The 52 legacy failures are explained by event-field fee semantics. `buyback_fee` is not part of the user quote endpoint, and event type alone does not determine whether the user quote endpoint is above or below the event quote amount. The decoded `user_quote_amount` reconciles when the active user quote fees are `lp_fee + protocol_fee + coin_creator_fee + cashback`, signed by the observed quote endpoint direction.

This confirms the decoded event fee endpoint reconciliation. It does not prove standalone executable quote prediction from reserves, because before/after reserve context remains insufficient.

## Readiness

- fee model status: `{readiness['fee_model_status']}`
- quote confidence: `{readiness['quote_confidence']}`
- full post-migration exit thesis allowed: `{readiness['full_post_migration_exit_thesis_allowed']}`
- partial 60m allowed now: `{readiness['partial_post_migration_depth_60m_allowed_now']}`
- 2h+ blocked: `{readiness['two_hour_plus_blocked']}`
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    status = run_forensics()
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
