"""Offline FDV-efficiency field repair for FP001."""

from __future__ import annotations

import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.fp001_formal_descriptive_thesis import (
    DEFAULT_SUPPORT_SUMMARY_PATH,
    build_fp001_formal_descriptive_thesis,
)


REPORT_ID = "fp001_fdv_field_repair_v0"
DEFAULT_COMBINED_DATASET_PATH = data_lake_path(
    "data", "backtests", "structural_enrichment", "combined_aligned_p0_structural_fingerprint.parquet"
)
DEFAULT_SOURCE_PATHS = [
    data_lake_path(
        "data",
        "backtests",
        "diagnostics",
        "reports",
        "T011_expanded_rerun",
        "expanded_trigger_20k_feature_rows.csv",
    ),
    data_lake_path(
        "data",
        "backtests",
        "diagnostics",
        "reports",
        "T011_expanded_rerun",
        "raw_flow",
        "trigger_20k_feature_rows.csv",
    ),
    data_lake_path(
        "data",
        "backtests",
        "diagnostics",
        "reports",
        "T011_explosive_runner_raw_flow",
        "trigger_20k_feature_rows.csv",
    ),
]
DEFAULT_REPAIRED_PARQUET_PATH = data_lake_path(
    "data", "backtests", "structural_enrichment", "combined_aligned_p0_structural_fingerprint_fdv_repaired.parquet"
)
DEFAULT_REPAIRED_JSONL_PATH = data_lake_path(
    "data", "backtests", "structural_enrichment", "combined_aligned_p0_structural_fingerprint_fdv_repaired.jsonl"
)
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "FP001_fdv_field_repair"
)
DEFAULT_FP001_OUTPUT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "FP001_formal_descriptive_thesis_fdv_repaired"
)
DEFAULT_STATUS_PATH = Path("theses/FP001_FDV_FIELD_REPAIR_STATUS.md")
DEFAULT_FP001_STATUS_PATH = Path("theses/FP001_FORMAL_DESCRIPTIVE_THESIS_FDV_REPAIRED_STATUS.md")

FDV_FIELDS = [
    "fdv_per_event_at_20k",
    "fdv_per_buy_at_20k",
    "fdv_per_active_wallet_at_20k",
    "active_wallets_at_20k",
    "event_count_at_20k",
    "buy_count_at_20k",
    "sell_count_at_20k",
    "buy_sell_ratio_at_20k",
    "trigger_20k_time",
]
REQUIRED_FP001_FIELDS = [
    "fdv_per_event_at_20k",
    "fdv_per_buy_at_20k",
    "fdv_per_active_wallet_at_20k",
    "active_wallets_at_20k",
    "shared_funding_proxy",
    "time_linked_funding_proxy",
    "launches_sharing_funder",
    "creators_sharing_funder",
]
HIDDEN_FIELDS = [
    "shared_funding_proxy",
    "time_linked_funding_proxy",
    "launches_sharing_funder",
    "creators_sharing_funder",
]
UNSUPPORTED_TERMS = ("insider", "scammer", "wash trader", "manipulator")


def build_fp001_fdv_field_repair(
    *,
    combined_dataset_path: Path | str = DEFAULT_COMBINED_DATASET_PATH,
    source_paths: list[Path | str] | None = None,
    support_summary_path: Path | str = DEFAULT_SUPPORT_SUMMARY_PATH,
    repaired_parquet_path: Path | str = DEFAULT_REPAIRED_PARQUET_PATH,
    repaired_jsonl_path: Path | str = DEFAULT_REPAIRED_JSONL_PATH,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    fp001_output_dir: Path | str = DEFAULT_FP001_OUTPUT_DIR,
    status_path: Path | str = DEFAULT_STATUS_PATH,
    fp001_status_path: Path | str = DEFAULT_FP001_STATUS_PATH,
) -> tuple[dict[str, Any], dict[str, Path]]:
    sources = [Path(path) for path in (source_paths or DEFAULT_SOURCE_PATHS)]
    combined_rows = _read_records(Path(combined_dataset_path))
    source_discovery = discover_fdv_source(sources, combined_rows=combined_rows)
    selected_source = Path(source_discovery["selected_source_path"]) if source_discovery.get("selected_source_path") else None
    source_rows = _read_records(selected_source) if selected_source else []
    repaired_rows, join_audit, unmatched_rows = _repair_rows(combined_rows, source_rows)
    readiness = _repair_readiness(join_audit)

    repaired_parquet = Path(repaired_parquet_path)
    repaired_jsonl = Path(repaired_jsonl_path)
    if repaired_rows:
        _write_jsonl(repaired_jsonl, repaired_rows)
        _write_parquet(repaired_parquet, repaired_rows)

    fp001_rerun = {"rerun_executed": False, "reason": "repair_not_ready", "classification": None}
    fp001_paths: dict[str, str] = {}
    if readiness == "fdv_repair_ready_for_FP001_rerun":
        fp001_report, fp001_output_paths = build_fp001_formal_descriptive_thesis(
            support_summary_path=support_summary_path,
            combined_dataset_path=repaired_parquet,
            output_dir=fp001_output_dir,
            status_path=fp001_status_path,
        )
        fp001_rerun = {
            "rerun_executed": True,
            "reason": "repair_ready",
            "classification": fp001_report.get("classification"),
            "rows_analyzed": fp001_report.get("rows_analyzed"),
            "rows_with_all_fp001_fields": (fp001_report.get("feature_coverage") or {}).get("rows_with_all_fp001_fields"),
        }
        fp001_paths = {key: str(path) for key, path in fp001_output_paths.items()}

    report = {
        "report_id": REPORT_ID,
        "report_type": "fp001_fdv_field_repair",
        "methodology_flags": [
            "offline_local_repair_only",
            "no_network_calls",
            "no_helius_calls",
            "no_validation_execution",
            "no_backtest",
            "no_paper_trading",
            "no_live_trading",
            "no_auto_buy_sell",
            "no_private_key_logic",
            "no_wallet_execution",
            "no_order_routing",
            "no_trading_logic",
            "no_profitability_claims",
            "no_strategy_generation",
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml_black_boxes",
            "no_fuzzy_joins",
        ],
        "source_paths": {
            "combined_dataset_path": str(combined_dataset_path),
            "candidate_source_paths": [str(path) for path in sources],
            "selected_source_path": source_discovery.get("selected_source_path"),
            "repaired_parquet_path": str(repaired_parquet),
            "repaired_jsonl_path": str(repaired_jsonl),
        },
        "source_discovery": source_discovery,
        "join_audit": join_audit,
        "repair_readiness": readiness,
        "fp001_rerun": fp001_rerun,
        "fp001_report_paths": fp001_paths,
        "next_recommendation": _next_recommendation(readiness, fp001_rerun),
        "limitations": [
            "fdv_per_active_wallet_at_20k_is_derived_from_trigger_fdv_proxy_over_active_wallets_when_missing",
            "trigger_20k_time_not_present_in_source_rows",
            "launch_id_join_only_no_fuzzy_matching",
            "true_market_cap_claims_remain_blocked",
        ],
    }
    _assert_guardrails(report)
    paths = _write_outputs(report, unmatched_rows, Path(output_dir), Path(status_path))
    paths["repaired_parquet_path"] = repaired_parquet
    paths["repaired_jsonl_path"] = repaired_jsonl
    return report, paths


def discover_fdv_source(source_paths: list[Path | str], *, combined_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    combined_launch_ids = {str(row.get("launch_id")) for row in (combined_rows or []) if _clean(row.get("launch_id"))}
    source_reports = []
    best: dict[str, Any] | None = None
    for path_like in source_paths:
        path = Path(path_like)
        rows = _read_records(path)
        launch_ids = [str(row.get("launch_id")) for row in rows if _clean(row.get("launch_id"))]
        mint_key = "mint" if rows and "mint" in rows[0] else "token_mint"
        mints = [str(row.get(mint_key)) for row in rows if _clean(row.get(mint_key))]
        field_availability = _field_availability(rows)
        overlap = len(set(launch_ids) & combined_launch_ids) if combined_launch_ids else 0
        report = {
            "path": str(path),
            "exists": path.exists(),
            "row_count": len(rows),
            "unique_launch_id_count": len(set(launch_ids)),
            "unique_mint_count": len(set(mints)),
            "duplicate_launch_id_count": len(launch_ids) - len(set(launch_ids)),
            "duplicate_mint_count": len(mints) - len(set(mints)),
            "combined_launch_id_overlap": overlap,
            "field_availability": field_availability,
        }
        source_reports.append(report)
        score = (
            overlap,
            int(field_availability["fdv_per_event_at_20k"]["available"]),
            int(field_availability["fdv_per_buy_at_20k"]["available"]),
            int(field_availability["fdv_per_active_wallet_at_20k"]["available"] or field_availability["fdv_per_active_wallet_at_20k"]["derivable"]),
            len(rows),
        )
        if best is None or score > best["_score"]:
            best = {**report, "_score": score}
    selected = best or {}
    return {
        "selected_source_path": selected.get("path"),
        "source_reports": source_reports,
        "row_count": selected.get("row_count", 0),
        "unique_launch_id_count": selected.get("unique_launch_id_count", 0),
        "unique_mint_count": selected.get("unique_mint_count", 0),
        "duplicate_launch_id_count": selected.get("duplicate_launch_id_count", 0),
        "duplicate_mint_count": selected.get("duplicate_mint_count", 0),
        "field_availability": selected.get("field_availability", {}),
    }


def _repair_rows(combined_rows: list[dict[str, Any]], source_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    source_by_launch: dict[str, dict[str, Any]] = {}
    duplicate_conflicts = 0
    duplicate_keys = Counter(str(row.get("launch_id")) for row in source_rows if _clean(row.get("launch_id")))
    for row in source_rows:
        launch_id = _clean(row.get("launch_id"))
        if not launch_id:
            continue
        if duplicate_keys[launch_id] > 1:
            duplicate_conflicts += 1
            continue
        source_by_launch[launch_id] = row
    duplicate_conflicts = len([key for key, count in duplicate_keys.items() if count > 1])

    repaired = []
    unmatched = []
    matched = 0
    for row in combined_rows:
        launch_id = _clean(row.get("launch_id"))
        source = source_by_launch.get(launch_id or "")
        out = dict(row)
        if source:
            matched += 1
            for field in FDV_FIELDS:
                value = _repair_value(field, source)
                if value is not None:
                    out[field] = value
        else:
            unmatched.append({"launch_id": row.get("launch_id"), "mint": row.get("mint"), "unmatched_reason": "no_launch_id_match"})
        repaired.append(out)

    complete = sum(1 for row in repaired if all(_has_value(row.get(field)) for field in REQUIRED_FP001_FIELDS))
    hidden_intact = sum(1 for row in repaired if all(_has_value(row.get(field)) for field in HIDDEN_FIELDS))
    join_audit = {
        "combined_rows_before_repair": len(combined_rows),
        "rows_matched_on_launch_id": matched,
        "rows_matched_on_fallback_key": 0,
        "unmatched_rows": len(unmatched),
        "duplicate_conflicts": duplicate_conflicts,
        "rows_with_repaired_fdv_efficiency_fields": sum(
            1
            for row in repaired
            if all(
                _has_value(row.get(field))
                for field in ["fdv_per_event_at_20k", "fdv_per_buy_at_20k", "fdv_per_active_wallet_at_20k"]
            )
        ),
        "rows_with_all_fp001_fields_after_repair": complete,
        "hidden_structure_rows_intact": hidden_intact,
        "fp001_field_coverage_pct": _pct(complete, len(repaired)),
    }
    return repaired, join_audit, unmatched


def _repair_value(field: str, source: dict[str, Any]) -> Any:
    if field == "fdv_per_active_wallet_at_20k":
        direct = _number(source.get(field))
        if direct is not None:
            return direct
        fdv = _number(source.get("trigger_fdv_proxy"))
        active = _number(source.get("active_wallets_at_20k"))
        if fdv is not None and active not in {None, 0}:
            return fdv / active
        return None
    return source.get(field)


def _field_availability(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    output = {}
    for field in FDV_FIELDS:
        available = field in rows[0] if rows else False
        non_null = sum(1 for row in rows if _has_value(row.get(field))) if available else 0
        derivable = False
        if field == "fdv_per_active_wallet_at_20k":
            derivable = any(_number(row.get("trigger_fdv_proxy")) is not None and _number(row.get("active_wallets_at_20k")) not in {None, 0} for row in rows)
        output[field] = {"available": available, "non_null_count": non_null, "derivable": derivable}
    return output


def _repair_readiness(join_audit: dict[str, Any]) -> str:
    total = join_audit.get("combined_rows_before_repair", 0)
    complete = join_audit.get("rows_with_all_fp001_fields_after_repair", 0)
    if total == 0 or join_audit.get("duplicate_conflicts", 0) > 0:
        return "fdv_repair_blocked"
    if _pct(complete, total) >= 80 and join_audit.get("hidden_structure_rows_intact", 0) == total:
        return "fdv_repair_ready_for_FP001_rerun"
    if complete:
        return "fdv_repair_partial_needs_review"
    return "fdv_repair_blocked"


def _next_recommendation(readiness: str, fp001_rerun: dict[str, Any]) -> str:
    if readiness != "fdv_repair_ready_for_FP001_rerun":
        return "repair_source_join_blocker_before_fp001_rerun"
    classification = fp001_rerun.get("classification")
    if classification in {"descriptive_signal_present", "weak_signal"}:
        return "review_repaired_fp001_descriptive_result_before_any_validation"
    if classification == "data_limited":
        return "inspect_repaired_fp001_coverage_and_support_rows"
    return "review_repaired_fp001_report"


def _write_outputs(report: dict[str, Any], unmatched_rows: list[dict[str, Any]], output_dir: Path, status_path: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary_json_path": output_dir / "FP001_fdv_field_repair_summary.json",
        "summary_md_path": output_dir / "FP001_fdv_field_repair_summary.md",
        "unmatched_rows_path": output_dir / "FP001_fdv_unmatched_rows.csv",
        "status_path": status_path,
    }
    paths["summary_json_path"].write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    paths["summary_md_path"].write_text(_markdown(report), encoding="utf-8")
    _write_csv(unmatched_rows, paths["unmatched_rows_path"])
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(_status_markdown(report), encoding="utf-8")
    return paths


def _markdown(report: dict[str, Any]) -> str:
    audit = report["join_audit"]
    return "\n".join(
        [
            "# FP001 FDV Field Repair",
            "",
            f"- Readiness: `{report['repair_readiness']}`",
            f"- Source file: `{report['source_paths']['selected_source_path']}`",
            f"- Combined rows before repair: `{audit['combined_rows_before_repair']}`",
            f"- Rows matched on launch_id: `{audit['rows_matched_on_launch_id']}`",
            f"- Rows with all FP001 fields after repair: `{audit['rows_with_all_fp001_fields_after_repair']}`",
            f"- FP001 rerun executed: `{report['fp001_rerun']['rerun_executed']}`",
            "",
            "Offline local repair only. No validation, backtest, network call, or trading workflow was run.",
        ]
    ) + "\n"


def _status_markdown(report: dict[str, Any]) -> str:
    audit = report["join_audit"]
    return "\n".join(
        [
            "# FP001 FDV Field Repair Status",
            "",
            "## Repair Summary",
            f"- Readiness: `{report['repair_readiness']}`",
            f"- FDV source: `{report['source_paths']['selected_source_path']}`",
            f"- Combined rows before repair: `{audit['combined_rows_before_repair']}`",
            f"- Rows matched on launch_id: `{audit['rows_matched_on_launch_id']}`",
            f"- Rows with all FP001 fields after repair: `{audit['rows_with_all_fp001_fields_after_repair']}`",
            f"- Duplicate conflicts: `{audit['duplicate_conflicts']}`",
            "",
            "## FP001 Rerun",
            f"- Executed: `{report['fp001_rerun']['rerun_executed']}`",
            f"- Classification: `{report['fp001_rerun']['classification']}`",
            "",
            "## Guardrails",
            "No Helius/API calls, validation, backtest, paper/live trading, threshold search, or strategy generation was run.",
            "",
            "## Next Recommendation",
            report["next_recommendation"],
        ]
    ) + "\n"


def _read_records(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    if path.suffix == ".parquet":
        import pandas as pd

        return pd.read_parquet(path).to_dict("records")
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if path.suffix == ".csv":
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    if path.suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []
    return []


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, default=str))
            handle.write("\n")


def _write_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    import pandas as pd

    pd.DataFrame(rows).to_parquet(path, index=False)


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        if not rows:
            return
        writer = csv.DictWriter(handle, fieldnames=sorted({key for row in rows for key in row}))
        writer.writeheader()
        writer.writerows(rows)


def _assert_guardrails(report: dict[str, Any]) -> None:
    text = json.dumps(report, sort_keys=True, default=str).lower()
    for term in UNSUPPORTED_TERMS:
        if term in text:
            raise ValueError(f"Unsupported label found in report: {term}")


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    return text


def _has_value(value: Any) -> bool:
    return _clean(value) is not None


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def _pct(num: int, den: int) -> float:
    return round(num / den * 100, 4) if den else 0.0
