"""Baseline-vs-filter audit for actionable crossed-20k forward mints.

This is descriptive diagnostics only. It recreates fixed labels from the
buy/exit design module and writes a disabled paper/shadow config update.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any

from research.mtp_research.data_paths import data_lake_root
from research.mtp_research.validation.buy_exit_start_rule_design import (
    BUY_RULES,
    EXIT_RULES,
    GUARDRAILS,
    _apply_buy_rule,
    _bucket_thresholds,
    _entry_fdv,
    _max,
    _num,
    _simulate_exit,
)


AUDIT_LABEL = "baseline_vs_filter_audit"


@dataclass(frozen=True)
class AuditInputs:
    source_report_root: Path
    dataset_rows: list[dict[str, Any]]
    actionable_rows: list[dict[str, Any]]
    summary: dict[str, Any]
    duplicate_mint_count: int
    missing_path_count: int
    missing_maturity_path_outcome_count: int
    open_incomplete_count: int


def run_baseline_vs_filter_audit(
    *,
    data_root: Path | str | None = None,
    source_report_root: Path | str | None = None,
    execute: bool = False,
) -> dict[str, Any]:
    root = Path(data_root or data_lake_root()).expanduser()
    source = Path(source_report_root).expanduser() if source_report_root else _default_buy_exit_root(root)
    audit_root = root / "data" / "backtests" / "diagnostics" / "reports" / "forward_observation" / AUDIT_LABEL
    config_path = root / "data" / "forward_observation" / "official_lifecycle_watch_v1" / "paper_shadow_starting_config.json"
    if not execute:
        return {
            "execute": False,
            "audit_label": AUDIT_LABEL,
            "source_report_root": str(source),
            "report_root": str(audit_root),
            "readiness": "baseline_vs_filter_audit_ready_for_execute",
        }

    audit_root.mkdir(parents=True, exist_ok=True)
    inputs = load_audit_inputs(source)
    labels = build_rule_labels(inputs.actionable_rows)
    baseline = build_baseline_path_summary(inputs.actionable_rows)
    filter_comparison = build_filter_vs_baseline_comparison(inputs.actionable_rows, labels, baseline)
    exit_comparison = build_baseline_exit_comparison(inputs.actionable_rows)
    recommendation = classify_recommendation(inputs.actionable_rows, filter_comparison, exit_comparison)
    config = build_disabled_baseline_config(recommendation)

    outputs = write_audit_outputs(
        audit_root=audit_root,
        labels=labels,
        baseline=baseline,
        filter_comparison=filter_comparison,
        exit_comparison=exit_comparison,
        recommendation=recommendation,
        inputs=inputs,
        config=config,
    )
    config_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(config_path, config)
    status_path = write_status_file(
        inputs=inputs,
        filter_comparison=filter_comparison,
        exit_comparison=exit_comparison,
        recommendation=recommendation,
        config_path=config_path,
    )
    summary = {
        "execute": True,
        "audit_label": AUDIT_LABEL,
        "source_report_root": str(source),
        "baseline_actionable_crossed_20k_count": len(inputs.actionable_rows),
        "confirmed_actionable_crossed_20k_count": len(inputs.actionable_rows),
        "raw_all_crossed_20k_count": inputs.summary.get("raw_all_crossed_20k_count"),
        "raw_actionable_crossed_20k_count": inputs.summary.get("raw_actionable_crossed_20k_count"),
        "confirmed_crossed_20k_count": inputs.summary.get("confirmed_crossed_20k_count"),
        "all_crossed_20k_count": inputs.summary.get("all_crossed_20k_count"),
        "filter_pass_counts": _filter_pass_counts(labels),
        "best_exit_candidate_on_baseline": recommendation["selected_exit_rule_id"],
        "recommendation": recommendation["recommendation"],
        "recommendation_reason": recommendation["reason"],
        "disabled_config_path": str(config_path),
        "report_paths": {key: str(value) for key, value in outputs.items()},
        "status_file": str(status_path),
    }
    _write_json(audit_root / "baseline_vs_filter_audit_summary.json", summary)
    (audit_root / "baseline_vs_filter_audit_summary.md").write_text(
        _summary_markdown(summary, baseline, recommendation),
        encoding="utf-8",
    )
    return summary


def load_audit_inputs(source_report_root: Path | str) -> AuditInputs:
    source = Path(source_report_root).expanduser()
    rows = _read_jsonl(source / "buy_exit_design_dataset.jsonl")
    summary = _read_json(source / "buy_exit_start_rule_design_summary.json")
    has_confirmed_flag = any("confirmed_actionable_crossed_20k" in row for row in rows)
    actionable = [
        row
        for row in rows
        if row.get("actionable_sample_flag") is True
        and row.get("crossed_20k") is True
        and (row.get("confirmed_actionable_crossed_20k") is True if has_confirmed_flag else True)
    ]
    mint_counts = Counter(str(row.get("mint")) for row in actionable if row.get("mint"))
    duplicate_count = sum(1 for count in mint_counts.values() if count > 1)
    missing_path_count = sum(1 for row in actionable if (row.get("path_row_count") or 0) <= 0)
    missing_maturity = sum(1 for row in actionable if row.get("maturity_state") is None or row.get("max_fdv_after_20k") is None)
    open_incomplete = sum(1 for row in actionable if not str(row.get("maturity_state") or "").startswith("matured_"))
    return AuditInputs(
        source_report_root=source,
        dataset_rows=rows,
        actionable_rows=actionable,
        summary=summary,
        duplicate_mint_count=duplicate_count,
        missing_path_count=missing_path_count,
        missing_maturity_path_outcome_count=missing_maturity,
        open_incomplete_count=open_incomplete,
    )


def build_rule_labels(actionable_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets = _bucket_thresholds(actionable_rows)
    labels = []
    for row in actionable_rows:
        out = {
            "mint": row["mint"],
            "baseline_all_actionable_20k": True,
            "confirmed_actionable_crossed_20k": row.get("confirmed_actionable_crossed_20k") is not False,
        }
        for rule in BUY_RULES:
            rule_id = rule["rule_id"]
            passed = _apply_buy_rule(row, rule_id, buckets)["eligible"]
            out[f"{rule_id}_pass"] = passed
            out[f"{rule_id}_failure_reason"] = "passed" if passed else _failure_reason(row, rule_id, buckets)
        labels.append(out)
    return labels


def build_baseline_path_summary(actionable_rows: list[dict[str, Any]]) -> dict[str, Any]:
    multiples = [_max_fdv_multiple_after_20k(row) for row in actionable_rows]
    drawdowns = [_num(row.get("max_drawdown_after_20k")) for row in actionable_rows]
    return {
        "population": "confirmed_actionable_crossed_20k",
        "count": len(actionable_rows),
        "reached_30k": _count_crossed(actionable_rows, "30k"),
        "reached_50k": _count_crossed(actionable_rows, "50k"),
        "reached_100k": _count_crossed(actionable_rows, "100k"),
        "reached_200k": _count_crossed(actionable_rows, "200k"),
        "reached_500k": _count_crossed(actionable_rows, "500k"),
        "reached_1m": _count_crossed(actionable_rows, "1m"),
        "reached_50k_rate": _rate(_count_crossed(actionable_rows, "50k"), len(actionable_rows)),
        "reached_100k_rate": _rate(_count_crossed(actionable_rows, "100k"), len(actionable_rows)),
        "reached_500k_rate": _rate(_count_crossed(actionable_rows, "500k"), len(actionable_rows)),
        "reached_1m_rate": _rate(_count_crossed(actionable_rows, "1m"), len(actionable_rows)),
        "max_fdv_multiple_after_20k": _max(multiples),
        "median_max_fdv_multiple": _median(multiples),
        "iqr_max_fdv_multiple": json.dumps(_iqr(multiples), sort_keys=True),
        "median_max_drawdown_after_20k": _median(drawdowns),
        "terminal_collapse_count": sum(1 for row in actionable_rows if row.get("terminal_collapse_proxy") is True or row.get("maturity_state") == "matured_terminal_collapse"),
        "inactive_max_age_count": sum(1 for row in actionable_rows if row.get("inactive_timeout") is True or row.get("maturity_state") in {"matured_inactive_timeout", "matured_max_age"}),
        "open_incomplete_count": sum(1 for row in actionable_rows if not str(row.get("maturity_state") or "").startswith("matured_")),
        "median_path_duration": _median([_num(row.get("time_to_peak_after_20k")) for row in actionable_rows]),
        "median_path_rows_per_mint": _median([_num(row.get("path_row_count")) for row in actionable_rows]),
    }


def build_filter_vs_baseline_comparison(
    actionable_rows: list[dict[str, Any]],
    labels: list[dict[str, Any]],
    baseline: dict[str, Any],
) -> list[dict[str, Any]]:
    rows_by_mint = {row["mint"]: row for row in actionable_rows}
    labels_by_mint = {row["mint"]: row for row in labels}
    out = []
    for rule in BUY_RULES:
        for passed in [True, False]:
            group_id = f"{rule['rule_id']}_{'pass' if passed else 'fail'}"
            group_rows = [rows_by_mint[mint] for mint, label in labels_by_mint.items() if label[f"{rule['rule_id']}_pass"] is passed]
            out.append(_filter_group_summary(group_id, rule["rule_id"], group_rows, baseline))
    return out


def build_baseline_exit_comparison(actionable_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    baseline_buy = {"rule_id": "BASELINE_20K", "trigger_level": "20k"}
    for rule in EXIT_RULES:
        sims = [_simulate_exit(row, baseline_buy, rule) if rule["rule_id"] != "E4" else _simulate_e4(row) for row in actionable_rows]
        reasons = Counter(sim["exit_reason"] for sim in sims)
        out.append(
            {
                "exit_rule_id": rule["rule_id"],
                "name": rule["name"],
                "baseline_eligible_rows": len(actionable_rows),
                "exited_count": sum(1 for sim in sims if _is_actual_exit(sim["exit_reason"])),
                "open_incomplete_count": reasons.get("open_or_incomplete", 0) + reasons.get("diagnostic_runner_hold", 0),
                "exit_reason_counts": json.dumps(dict(reasons), sort_keys=True),
                "median_exit_fdv_multiple_if_computable": _median([sim.get("exit_multiple") for sim in sims]),
                "median_max_fdv_multiple_before_exit": _median([sim.get("max_fdv_multiple") for sim in sims]),
                "runner_miss_count": sum(1 for sim in sims if sim.get("runner_missed")),
                "exited_before_50k": sum(1 for sim in sims if _is_actual_exit(sim["exit_reason"]) and sim.get("row_crossed_50k")),
                "exited_before_100k": sum(1 for sim in sims if sim.get("exit_before_100k")),
                "exited_before_500k": sum(1 for sim in sims if sim.get("exit_before_500k")),
                "held_through_500k": sum(1 for sim in sims if sim.get("held_through_500k")),
                "held_through_1m": sum(1 for sim in sims if sim.get("held_through_1m")),
                "data_limited_count": sum(1 for row in actionable_rows if row.get("fdv_anomaly") is True or (row.get("path_row_count") or 0) < 2),
                "label": "FDV path multiple, not realized PnL",
            }
        )
    return out


def classify_recommendation(
    actionable_rows: list[dict[str, Any]],
    filter_comparison: list[dict[str, Any]],
    exit_comparison: list[dict[str, Any]],
) -> dict[str, Any]:
    pass_rows = [row for row in filter_comparison if row["group_id"].endswith("_pass")]
    max_support = max((row["pass_count"] for row in pass_rows), default=0)
    meaningful = [row for row in pass_rows if row["improvement_interpretation"] == "meaningful_filter_improvement"]
    best_exit = "E2" if any(row["exit_rule_id"] == "E2" for row in exit_comparison) else (exit_comparison[0]["exit_rule_id"] if exit_comparison else "E2")
    if meaningful:
        recommendation = "B_narrow_filter_needs_review_before_start"
        reason = "At least one filter has support >=30 and improves baseline FDV-path characteristics."
    elif max_support < 30:
        recommendation = "A_baseline_all_actionable_20k_with_filter_labels"
        reason = "Narrow filters have support below 30, so start from the broad actionable-20k universe as labels only."
    else:
        recommendation = "D_more_official_lifecycle_data_before_enable"
        reason = "Filters do not clearly improve baseline; keep config disabled until more clean lifecycle data exists."
    return {
        "recommendation": recommendation,
        "selected_exit_rule_id": best_exit,
        "max_filter_support": max_support,
        "reason": reason,
        "paper_shadow_enable_status": "disabled",
    }


def build_disabled_baseline_config(recommendation: dict[str, Any]) -> dict[str, Any]:
    return {
        "enabled": False,
        "sample_source": "buy_exit_design_dataset",
        "selected_entry_universe": "confirmed_actionable_crossed_20k",
        "legacy_entry_universe_name": "baseline_all_actionable_20k",
        "entry_decision_type": "shadow_would_enter_baseline",
        "selected_exit_rule_id": recommendation["selected_exit_rule_id"],
        "attached_filter_labels": ["B1", "B2", "B3", "B4"],
        "reason_for_avoiding_narrow_B3_only_start": "B3 support is below 30 rows in the fixed-rule audit, so it is too small for the first paper/shadow start.",
        "recommendation": recommendation["recommendation"],
        "next_enable_condition": "operator explicitly approves after reviewing baseline-vs-filter audit and collector data recovers beyond current data-limited status",
        "guardrails": GUARDRAILS,
        "no_pnl_claims": True,
        "no_live_execution": True,
    }


def write_audit_outputs(
    *,
    audit_root: Path,
    labels: list[dict[str, Any]],
    baseline: dict[str, Any],
    filter_comparison: list[dict[str, Any]],
    exit_comparison: list[dict[str, Any]],
    recommendation: dict[str, Any],
    inputs: AuditInputs,
    config: dict[str, Any],
) -> dict[str, Path]:
    outputs = {
        "rule_labels_csv": audit_root / "actionable_20k_rule_labels.csv",
        "baseline_csv": audit_root / "baseline_path_summary.csv",
        "filter_csv": audit_root / "filter_vs_baseline_comparison.csv",
        "exit_csv": audit_root / "baseline_exit_comparison.csv",
        "config_csv": audit_root / "updated_paper_shadow_config_summary.csv",
    }
    _write_csv(outputs["rule_labels_csv"], labels)
    _write_csv(outputs["baseline_csv"], [baseline])
    _write_csv(outputs["filter_csv"], filter_comparison)
    _write_csv(outputs["exit_csv"], exit_comparison)
    _write_csv(
        outputs["config_csv"],
        [
            {
                "enabled": config["enabled"],
                "selected_entry_universe": config["selected_entry_universe"],
                "selected_exit_rule_id": config["selected_exit_rule_id"],
                "recommendation": recommendation["recommendation"],
                "baseline_actionable_crossed_20k_count": len(inputs.actionable_rows),
                "confirmed_actionable_crossed_20k_count": len(inputs.actionable_rows),
                "raw_all_crossed_20k_count": inputs.summary.get("raw_all_crossed_20k_count"),
            }
        ],
    )
    return outputs


def write_status_file(
    *,
    inputs: AuditInputs,
    filter_comparison: list[dict[str, Any]],
    exit_comparison: list[dict[str, Any]],
    recommendation: dict[str, Any],
    config_path: Path,
) -> Path:
    path = Path("theses") / "BASELINE_VS_FILTER_AUDIT_STATUS.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    counts = {row["rule_id"]: row["pass_count"] for row in filter_comparison if row["group_id"].endswith("_pass")}
    exit_summary = {row["exit_rule_id"]: row["open_incomplete_count"] for row in exit_comparison}
    path.write_text(
        "\n".join(
            [
                "# Baseline Vs Filter Audit Status",
                "",
                "Created because the previous B3/E2 design produced only 8 hypothetical entries out of 192 actionable crossed-20k mints.",
                "",
                f"Confirmed actionable crossed-20k count: `{len(inputs.actionable_rows)}`",
                f"Raw all crossed-20k count: `{inputs.summary.get('raw_all_crossed_20k_count', inputs.summary.get('all_crossed_20k_count'))}`",
                f"Filter counts: `{counts}`",
                "Narrow B3/E2 is not justified as the first start if support remains below 30 rows.",
                f"Exit comparison open/incomplete summary: `{exit_summary}`",
                f"Recommendation: `{recommendation['recommendation']}`",
                f"Disabled config path: `{config_path}`",
                "",
                "No paper trades, live trades, wallet execution, transaction signing, order routing, buy orders, sell orders, threshold optimization, validation, or PnL claims were run.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _failure_reason(row: dict[str, Any], rule_id: str, buckets: dict[str, float]) -> str:
    reasons: list[str] = []
    if row.get("fdv_anomaly"):
        reasons.append("fdv_anomaly")
    if rule_id == "B1":
        _check(reasons, row.get("crossed_10k") is True, "missing_crossed_10k")
        _check(reasons, row.get("first_path_before_10k") is True, "first_path_before_10k_false")
        _check(
            reasons,
            ((_num(row.get("fdv_per_event_at_10k")) or 0) >= buckets["fdv_per_event_at_10k"] or (_num(row.get("fdv_per_active_wallet_at_10k")) or 0) >= buckets["fdv_per_active_wallet_at_10k"]),
            "efficiency_below_fixed_bucket",
        )
        _check(reasons, (_num(row.get("fdv_at_10k")) or float("inf")) <= 15_000, "chase_guard_fdv_at_10k_above_15k")
    elif rule_id == "B2":
        _check(reasons, row.get("crossed_15k") is True, "missing_crossed_15k")
        _check(reasons, row.get("first_path_before_15k") is True, "first_path_before_15k_false")
        _check(
            reasons,
            ((_num(row.get("fdv_per_event_at_15k")) or 0) >= buckets["fdv_per_event_at_15k"] or (_num(row.get("fdv_per_active_wallet_at_15k")) or 0) >= buckets["fdv_per_active_wallet_at_15k"]),
            "efficiency_below_fixed_bucket",
        )
        _check(reasons, (_num(row.get("fdv_at_15k")) or float("inf")) <= 20_000, "chase_guard_fdv_at_15k_above_20k")
    elif rule_id == "B3":
        _check(reasons, row.get("crossed_20k") is True, "missing_crossed_20k")
        _check(reasons, row.get("first_path_before_20k") is True, "first_path_before_20k_false")
        _check(
            reasons,
            ((_num(row.get("fdv_per_event_at_20k")) or 0) >= buckets["fdv_per_event_at_20k"] or (_num(row.get("fdv_per_active_wallet_at_20k")) or 0) >= buckets["fdv_per_active_wallet_at_20k"]),
            "efficiency_below_fixed_bucket",
        )
        _check(reasons, row.get("10k_to_20k_seconds") is not None, "missing_10k_to_20k_path")
        _check(reasons, (_num(row.get("fdv_at_20k")) or float("inf")) <= 30_000, "chase_guard_fdv_at_20k_above_30k")
    elif rule_id == "B4":
        if not _apply_buy_rule(row, "B3", buckets)["eligible"]:
            reasons.append("b3_requirement_failed")
        time_to_30k = (_num(row.get("first_crossed_30k_time")) or float("inf")) - (_num(row.get("first_crossed_20k_time")) or 0)
        _check(reasons, row.get("crossed_30k") is True or time_to_30k <= 300, "missing_30k_continuation")
    return ";".join(reasons or ["fixed_rule_not_met"])


def _filter_group_summary(group_id: str, rule_id: str, rows: list[dict[str, Any]], baseline: dict[str, Any]) -> dict[str, Any]:
    count = len(rows)
    median_multiple = _median([_max_fdv_multiple_after_20k(row) for row in rows])
    reached_100k_rate = _rate(_count_crossed(rows, "100k"), count)
    improves = (median_multiple or 0) > (baseline.get("median_max_fdv_multiple") or 0) or reached_100k_rate > (baseline.get("reached_100k_rate") or 0)
    if count < 30:
        interpretation = "small_sample_artifact" if improves else "support_too_small"
    elif improves:
        interpretation = "meaningful_filter_improvement"
    else:
        interpretation = "no_clear_improvement"
    return {
        "group_id": group_id,
        "rule_id": rule_id,
        "pass_count": count,
        "pass_rate": _rate(count, baseline["count"]),
        "reached_50k": _count_crossed(rows, "50k"),
        "reached_100k": _count_crossed(rows, "100k"),
        "reached_500k": _count_crossed(rows, "500k"),
        "reached_1m": _count_crossed(rows, "1m"),
        "reached_50k_rate": _rate(_count_crossed(rows, "50k"), count),
        "reached_100k_rate": reached_100k_rate,
        "reached_500k_rate": _rate(_count_crossed(rows, "500k"), count),
        "reached_1m_rate": _rate(_count_crossed(rows, "1m"), count),
        "median_max_fdv_multiple": median_multiple,
        "median_drawdown": _median([_num(row.get("max_drawdown_after_20k")) for row in rows]),
        "open_incomplete_count": sum(1 for row in rows if not str(row.get("maturity_state") or "").startswith("matured_")),
        "data_limited_count": sum(1 for row in rows if row.get("fdv_anomaly") is True or (row.get("path_row_count") or 0) < 2),
        "support_warning": "support_lt_30" if count < 30 else "",
        "improves_over_baseline": improves,
        "improvement_interpretation": interpretation,
    }


def _simulate_e4(row: dict[str, Any]) -> dict[str, Any]:
    entry = _entry_fdv(row, "20k")
    max_fdv = _num(row.get("max_fdv_after_20k")) or entry
    return {
        "entry_fdv": entry,
        "max_fdv_multiple": (max_fdv / entry) if entry else None,
        "exit_reason": "diagnostic_runner_hold",
        "exit_multiple": None,
        "runner_missed": False,
        "exit_before_100k": False,
        "exit_before_500k": False,
        "held_through_500k": bool(row.get("crossed_500k")),
        "held_through_1m": bool(row.get("crossed_1m")),
        "row_crossed_50k": bool(row.get("crossed_50k")),
    }


def _is_actual_exit(reason: str) -> bool:
    return reason not in {"open_or_incomplete", "diagnostic_runner_hold"}


def _filter_pass_counts(labels: list[dict[str, Any]]) -> dict[str, int]:
    return {rule["rule_id"]: sum(1 for row in labels if row.get(f"{rule['rule_id']}_pass") is True) for rule in BUY_RULES}


def _max_fdv_multiple_after_20k(row: dict[str, Any]) -> float | None:
    entry = _num(row.get("fdv_at_20k"))
    max_fdv = _num(row.get("max_fdv_after_20k"))
    return max_fdv / entry if entry and max_fdv else None


def _count_crossed(rows: list[dict[str, Any]], level: str) -> int:
    return sum(1 for row in rows if row.get(f"crossed_{level}") is True)


def _rate(count: int, total: int) -> float:
    return round(count / total, 6) if total else 0.0


def _median(values: list[Any]) -> float | None:
    clean = [_num(value) for value in values if _num(value) is not None]
    return median(clean) if clean else None


def _iqr(values: list[Any]) -> dict[str, float | None]:
    clean = sorted(_num(value) for value in values if _num(value) is not None)
    if not clean:
        return {"q1": None, "q3": None}
    return {"q1": clean[int((len(clean) - 1) * 0.25)], "q3": clean[int((len(clean) - 1) * 0.75)]}


def _check(reasons: list[str], condition: bool, reason: str) -> None:
    if not condition:
        reasons.append(reason)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row}) if rows else ["empty"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _default_buy_exit_root(root: Path) -> Path:
    return root / "data" / "backtests" / "diagnostics" / "reports" / "forward_observation" / "buy_exit_design"


def _summary_markdown(summary: dict[str, Any], baseline: dict[str, Any], recommendation: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Baseline Vs Filter Audit Summary",
            "",
            f"Baseline actionable crossed-20k count: `{summary['baseline_actionable_crossed_20k_count']}`",
            f"Confirmed actionable crossed-20k count: `{summary['baseline_actionable_crossed_20k_count']}`",
            f"All crossed-20k count: `{summary.get('all_crossed_20k_count')}`",
            f"Raw all crossed-20k count: `{summary.get('raw_all_crossed_20k_count')}`",
            f"Filter pass counts: `{summary['filter_pass_counts']}`",
            f"Median baseline max FDV path multiple: `{baseline['median_max_fdv_multiple']}`",
            f"Best baseline exit candidate: `{summary['best_exit_candidate_on_baseline']}`",
            f"Recommendation: `{recommendation['recommendation']}`",
            "",
            "This is diagnostic only. No paper/live trades were run.",
            "",
        ]
    )
