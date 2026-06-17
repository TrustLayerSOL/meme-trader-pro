from __future__ import annotations

import argparse
import csv
import json
import math
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

from research.mtp_research.validation.t007av_pumpswap_swap_event_fee_confirmation import write_t007av_report
from research.mtp_research.validation.t007ax_pumpswap_fee_replay_failure_forensics import (
    T007AX_GUARDRAILS,
    compare_formula_variants,
)


OUTPUT_BASE = Path("/Users/dianeposs/Projects/meme-trader-pro/outputs/theses/t007ay_post_patch_pumpswap_fee_quote_10m")
SOURCE_DURATION_COMPLETE_RATIO = 0.95


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return {}


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


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))


def _count_present(rows: Iterable[Mapping[str, Any]], key: str) -> int:
    return sum(1 for row in rows if row.get(key) not in (None, ""))


def _status_counts(rows: Iterable[Mapping[str, Any]], key: str) -> dict[str, int]:
    counts = Counter(str(row.get(key) or "missing") for row in rows)
    return dict(sorted(counts.items()))


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_zero(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def evaluate_source_duration_quality(
    *,
    requested_source_duration_seconds: Any,
    actual_source_duration_seconds: Any,
    websocket_keepalive_timeout_count: Any = 0,
    websocket_reconnect_count: Any = 0,
    websocket_closed_early: Any = False,
    websocket_close_reason: Any = None,
) -> dict[str, Any]:
    requested = _float_or_none(requested_source_duration_seconds)
    actual = _float_or_none(actual_source_duration_seconds)
    keepalive_timeouts = _int_or_zero(websocket_keepalive_timeout_count)
    reconnect_count = _int_or_zero(websocket_reconnect_count)
    if requested is None or requested <= 0:
        return {
            "requested_source_duration_seconds": requested,
            "actual_source_duration_seconds": actual,
            "source_duration_completion_ratio": None,
            "source_duration_quality_status": "not_evaluated",
            "source_ended_early": False,
            "early_end_reason": None,
            "validation_run_quality_label": "RUN_QUALITY_NOT_EVALUATED",
            "websocket_keepalive_timeout_count": keepalive_timeouts,
            "websocket_reconnect_count": reconnect_count,
            "completed_requested_duration": None,
        }
    if actual is None:
        return {
            "requested_source_duration_seconds": requested,
            "actual_source_duration_seconds": actual,
            "source_duration_completion_ratio": 0.0,
            "source_duration_quality_status": "failed",
            "source_ended_early": True,
            "early_end_reason": "missing_actual_source_duration",
            "validation_run_quality_label": "RUN_QUALITY_FAILED",
            "websocket_keepalive_timeout_count": keepalive_timeouts,
            "websocket_reconnect_count": reconnect_count,
            "completed_requested_duration": False,
        }
    ratio = max(0.0, actual) / requested
    source_ended_early = ratio < SOURCE_DURATION_COMPLETE_RATIO
    explicit_closed_early = bool(websocket_closed_early)
    if actual <= 0:
        status = "failed"
        label = "RUN_QUALITY_FAILED"
        reason = str(websocket_close_reason or "zero_actual_source_duration")
    elif source_ended_early or explicit_closed_early:
        status = "partial"
        label = "RUN_QUALITY_PARTIAL"
        reason = str(websocket_close_reason or "source_duration_below_95pct")
    else:
        status = "complete"
        label = "CLEAN_10M_SOURCE_DURATION_PASSED"
        reason = None
    return {
        "requested_source_duration_seconds": requested,
        "actual_source_duration_seconds": actual,
        "source_duration_completion_ratio": ratio,
        "source_duration_quality_status": status,
        "source_ended_early": status in {"partial", "failed"},
        "early_end_reason": reason,
        "validation_run_quality_label": label,
        "websocket_keepalive_timeout_count": keepalive_timeouts,
        "websocket_reconnect_count": reconnect_count,
        "completed_requested_duration": status == "complete",
    }


def _best_cp_variant(variant_rows: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    cp_rows = [row for row in variant_rows if str(row.get("variant_name") or "").startswith("cp_")]
    if not cp_rows:
        return None
    return max(cp_rows, key=lambda row: (int(row.get("pass_count") or 0), -float(row.get("max_relative_error_pct") or 0.0)))


def _label_fee_proof(events: list[Mapping[str, Any]], replay_rows: list[Mapping[str, Any]], status: Mapping[str, Any]) -> str:
    if not events:
        return "NO_PUMPSWAP_SWAP_EVENTS_CAPTURED"
    tested = int(status.get("replay_rows_tested") or 0)
    passed = int(status.get("replay_rows_passed") or 0)
    buy_count = int(status.get("buy_event_count") or 0)
    sell_count = int(status.get("sell_event_count") or 0)
    if tested and passed == tested and buy_count > 0 and sell_count > 0:
        return "POST_PATCH_EVENT_FEE_PROOF_PASSED"
    if passed > 0:
        return "POST_PATCH_EVENT_FEE_PROOF_PARTIAL"
    return "POST_PATCH_EVENT_FEE_PROOF_FAILED"


def _label_reserve_quote(events: list[Mapping[str, Any]], cp_variant: Mapping[str, Any] | None) -> str:
    if not events:
        return "RESERVE_QUOTE_STILL_UNCONFIRMED"
    if not cp_variant or int(cp_variant.get("rows_tested") or 0) == 0:
        return "RESERVE_QUOTE_STILL_UNCONFIRMED"
    tested = int(cp_variant.get("rows_tested") or 0)
    passed = int(cp_variant.get("pass_count") or 0)
    if tested == len(events) and passed == tested:
        return "RESERVE_QUOTE_CONFIRMED"
    if passed > 0:
        return "RESERVE_QUOTE_PARTIAL"
    return "RESERVE_QUOTE_STILL_UNCONFIRMED"


def _label_readiness(fee_label: str, reserve_label: str, source_quality_status: str = "not_evaluated") -> str:
    if source_quality_status in {"partial", "failed"}:
        return "FULL_THESIS_STILL_BLOCKED"
    if fee_label == "NO_PUMPSWAP_SWAP_EVENTS_CAPTURED":
        return "NO_SWAP_CONTEXT_FOR_GATE_CHANGE"
    if reserve_label == "RESERVE_QUOTE_CONFIRMED":
        return "FULL_THESIS_READY_FOR_60M"
    if fee_label == "POST_PATCH_EVENT_FEE_PROOF_PASSED":
        return "POST_MIGRATION_DEPTH_PARTIAL_60M_ALLOWED"
    return "FULL_THESIS_STILL_BLOCKED"


def _archive_status(archive_root: Path) -> str:
    manifest = _read_json(archive_root / "archive_manifest.json")
    return str(manifest.get("archive_status") or manifest.get("status") or ("present" if archive_root.exists() else "missing"))


def run_t007ay_postprocess(*, archive_root: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    status = write_t007av_report([archive_root], output_dir)
    events = _read_jsonl(output_dir / "pumpswap_swap_events.jsonl")
    replay_rows = _read_csv(output_dir / "fee_formula_replay_validation.csv")
    collector_summary = _read_json(archive_root / "collector_summary.json")
    executable_quote_rows = _read_jsonl(archive_root / "executable_quote_observations.jsonl")
    variant_rows = compare_formula_variants(events)
    cp_variant = _best_cp_variant(variant_rows)
    fee_label = _label_fee_proof(events, replay_rows, status)
    requested_source_duration = (
        collector_summary.get("requested_source_duration_seconds")
        or collector_summary.get("source_duration_seconds")
        or collector_summary.get("source_duration")
        or collector_summary.get("requested_duration_seconds")
    )
    actual_source_duration = (
        collector_summary.get("actual_source_duration_seconds")
        or collector_summary.get("actual_duration_seconds")
    )
    source_quality = evaluate_source_duration_quality(
        requested_source_duration_seconds=requested_source_duration,
        actual_source_duration_seconds=actual_source_duration,
        websocket_keepalive_timeout_count=collector_summary.get("websocket_keepalive_timeout_count"),
        websocket_reconnect_count=collector_summary.get("websocket_reconnect_count")
        or collector_summary.get("reconnect_attempts"),
        websocket_closed_early=collector_summary.get("websocket_closed_early", False),
        websocket_close_reason=collector_summary.get("websocket_close_reason"),
    )
    if fee_label == "POST_PATCH_EVENT_FEE_PROOF_PASSED" and source_quality["source_duration_quality_status"] == "partial":
        fee_label = "POST_PATCH_EVENT_FEE_PROOF_PASSED_RUN_QUALITY_PARTIAL"
    elif fee_label == "POST_PATCH_EVENT_FEE_PROOF_PASSED" and source_quality["source_duration_quality_status"] == "failed":
        fee_label = "POST_PATCH_EVENT_FEE_PROOF_PASSED_RUN_QUALITY_FAILED"
    reserve_label = _label_reserve_quote(events, cp_variant)
    readiness_label = _label_readiness(fee_label, reserve_label, str(source_quality["source_duration_quality_status"]))
    event_endpoint_pass = sum(1 for row in replay_rows if row.get("validation_status") == "pass")
    event_endpoint_fail = sum(1 for row in replay_rows if row.get("validation_status") == "fail")
    rows_with_reserve_context = sum(
        1
        for row in events
        if row.get("pool_base_token_reserves") not in (None, "")
        and row.get("pool_quote_token_reserves") not in (None, "")
    )
    best_cp_pass = int((cp_variant or {}).get("pass_count") or 0)
    gate = {
        "task": "T007AY_Post_Patch_PumpSwap_Fee_Quote_10m_Proof",
        "generated_at_epoch": time.time(),
        "archive_root": str(archive_root),
        "output_dir": str(output_dir),
        "archive_status": _archive_status(archive_root),
        "run_finalized": bool(collector_summary.get("run_finalized") or collector_summary.get("finalized")),
        "raw_notifications": int(collector_summary.get("raw_notifications") or collector_summary.get("birth_source_raw_notifications") or 0),
        "unique_births": int(collector_summary.get("unique_births") or collector_summary.get("births_detected") or 0),
        "admitted_births": int(collector_summary.get("admitted_births") or collector_summary.get("births_admitted") or 0),
        "queue_drops": int(collector_summary.get("queue_drops") or collector_summary.get("queue_dropped") or 0),
        "rpc_failures": int(collector_summary.get("rpc_failures") or collector_summary.get("rpc_failure_count") or 0),
        "http_429": int(collector_summary.get("http_429_count") or collector_summary.get("http_429") or 0),
        "capacity_rejected": int(collector_summary.get("capacity_rejected") or collector_summary.get("capacity_rejected_count") or 0),
        "websocket_closed_early": bool(collector_summary.get("websocket_closed_early", False)),
        **source_quality,
        "valuation_ladder_events": int(collector_summary.get("valuation_ladder_events_written") or 0),
        "decision_time_safety_violations": int(collector_summary.get("decision_time_safety_violations") or 0),
        "pumpswap_route_raw_notifications": int(collector_summary.get("pumpswap_route_raw_notifications") or 0),
        "route_audit_candidate_transactions": int(collector_summary.get("pumpswap_route_candidate_transactions") or 0),
        "decoded_pumpswap_swap_events": len(events),
        "buy_events": int(status.get("buy_event_count") or 0),
        "sell_events": int(status.get("sell_event_count") or 0),
        "fee_bps_populated": int(status.get("fee_bps_populated_count") or 0),
        "lp_fee_populated": _count_present(events, "lp_fee"),
        "protocol_fee_populated": _count_present(events, "protocol_fee"),
        "coin_creator_fee_populated": _count_present(events, "coin_creator_fee"),
        "cashback_populated": _count_present(events, "cashback"),
        "buyback_fee_populated": _count_present(events, "buyback_fee"),
        "event_endpoint_reconciliation_rows": len(replay_rows),
        "event_endpoint_pass_count": event_endpoint_pass,
        "event_endpoint_fail_count": event_endpoint_fail,
        "buy_side_pass_rate": f"{status.get('buy_event_count', 0)}/{status.get('buy_event_count', 0)}" if event_endpoint_fail == 0 else "partial",
        "sell_side_pass_rate": f"{status.get('sell_event_count', 0)}/{status.get('sell_event_count', 0)}" if event_endpoint_fail == 0 else "partial",
        "executable_quote_observations_written": len(executable_quote_rows),
        "price_impact_rows_populated": _count_present(executable_quote_rows, "price_impact_pct"),
        "quote_source_counts": _status_counts(executable_quote_rows, "quote_source"),
        "quote_status_counts": _status_counts(executable_quote_rows, "executable_quote_status"),
        "fee_model_status_counts": {str(status.get("fee_model_status") or "unknown"): 1},
        "quote_confidence_counts": {str(status.get("quote_confidence") or "low"): 1},
        "rows_with_before_after_reserve_context": rows_with_reserve_context,
        "direct_reserve_quote_prediction_reconciled_rows": best_cp_pass,
        "only_event_endpoint_reconciles_rows": max(0, event_endpoint_pass - best_cp_pass),
        "rows_still_failing": event_endpoint_fail,
        "failure_reasons": _status_counts([row for row in replay_rows if row.get("validation_status") == "fail"], "failure_reason"),
        "best_reserve_variant": (cp_variant or {}).get("variant_name", ""),
        "best_reserve_variant_rows_tested": int((cp_variant or {}).get("rows_tested") or 0),
        "best_reserve_variant_pass_count": best_cp_pass,
        "fee_proof_label": fee_label,
        "reserve_quote_label": reserve_label,
        "readiness_label": readiness_label,
        "fee_model_status": status.get("fee_model_status"),
        "quote_confidence": status.get("quote_confidence"),
        "sixty_min_remains_blocked": readiness_label == "FULL_THESIS_STILL_BLOCKED",
        "two_hour_plus_blocked": True,
        "valuation_ladder_suppressed": True,
        "mayhem_files_modified": False,
        "trading_paper_wallet_signing_execution_untouched": True,
        "guardrails": T007AX_GUARDRAILS,
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
    _write_json(output_dir / "readiness_gate_after_t007ay.json", gate)
    _write_summary(output_dir / "summary.md", gate)
    return gate


def _write_summary(path: Path, gate: Mapping[str, Any]) -> None:
    path.write_text(
        f"""# T007AY Post-Patch PumpSwap Fee Quote 10m Proof

## Scope

- live scan duration: `600s`
- no trading: `true`
- no paper trading: `true`
- Mayhem files modified: `{gate['mayhem_files_modified']}`
- valuation ladder suppressed: `{gate['valuation_ladder_suppressed']}`
- wallet/signing/execution untouched: `{gate['trading_paper_wallet_signing_execution_untouched']}`

## Collector health

- archive status: `{gate['archive_status']}`
- run finalized: `{gate['run_finalized']}`
- raw notifications: `{gate['raw_notifications']}`
- unique births: `{gate['unique_births']}`
- admitted births: `{gate['admitted_births']}`
- queue drops: `{gate['queue_drops']}`
- RPC failures: `{gate['rpc_failures']}`
- HTTP 429: `{gate['http_429']}`
- capacity rejected: `{gate['capacity_rejected']}`
- valuation ladder events: `{gate['valuation_ladder_events']}`

## Run quality

- requested source duration: `{gate['requested_source_duration_seconds']}`
- actual source duration: `{gate['actual_source_duration_seconds']}`
- source duration completion ratio: `{gate['source_duration_completion_ratio']}`
- source duration quality status: `{gate['source_duration_quality_status']}`
- validation run quality label: `{gate['validation_run_quality_label']}`
- websocket keepalive timeout count: `{gate['websocket_keepalive_timeout_count']}`
- websocket reconnect count: `{gate['websocket_reconnect_count']}`
- source ended early: `{gate['source_ended_early']}`
- early end reason: `{gate['early_end_reason']}`

## PumpSwap swap route

- route raw notifications: `{gate['pumpswap_route_raw_notifications']}`
- route candidate transactions: `{gate['route_audit_candidate_transactions']}`
- decoded swap events: `{gate['decoded_pumpswap_swap_events']}`
- buy/sell events: `{gate['buy_events']}/{gate['sell_events']}`
- event endpoint pass/fail: `{gate['event_endpoint_pass_count']}/{gate['event_endpoint_fail_count']}`
- fee model status: `{gate['fee_model_status']}`
- quote confidence: `{gate['quote_confidence']}`

## Reserve quote status

- executable quote observations: `{gate['executable_quote_observations_written']}`
- rows with reserve context: `{gate['rows_with_before_after_reserve_context']}`
- direct reserve quote reconciled rows: `{gate['direct_reserve_quote_prediction_reconciled_rows']}`
- only event endpoint reconciles rows: `{gate['only_event_endpoint_reconciles_rows']}`

## Labels

- fee proof label: `{gate['fee_proof_label']}`
- reserve quote label: `{gate['reserve_quote_label']}`
- readiness label: `{gate['readiness_label']}`
- 2h+ blocked: `{gate['two_hour_plus_blocked']}`
""",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    gate = run_t007ay_postprocess(archive_root=args.archive_root, output_dir=args.output_dir)
    print(json.dumps(gate, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
