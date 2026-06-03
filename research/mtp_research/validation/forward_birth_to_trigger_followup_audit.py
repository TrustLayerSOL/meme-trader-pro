"""Audit birth-watch candidates for later FDV/trigger follow-up evidence.

This module is read-only. It inspects already-written forward observation
artifacts and does not collect candidates, call Helius, or create trading
signals.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from typing import Any


REPORT_ID = "forward_birth_to_trigger_followup_audit_v0"
TRIGGER_LEVELS = {
    "10k": 10_000.0,
    "15k": 15_000.0,
    "20k": 20_000.0,
    "30k": 30_000.0,
    "50k": 50_000.0,
    "100k": 100_000.0,
    "200k": 200_000.0,
    "500k": 500_000.0,
    "1m": 1_000_000.0,
}
OUTPUT_NAMES = {
    "per_mint_csv": "birth_to_trigger_followup_audit.csv",
    "summary_json": "birth_to_trigger_followup_audit.json",
    "summary_md": "birth_to_trigger_followup_audit.md",
}
GUARDRAILS = [
    "audit_only",
    "no_network_calls",
    "no_helius_calls",
    "no_paper_trading",
    "no_live_trading",
    "no_wallet_execution",
    "no_order_routing",
    "no_backtest",
    "no_validation",
    "no_strategy_generation",
]


@dataclass(frozen=True)
class LoadedJsonl:
    rows: list[dict[str, Any]]
    malformed_rows: int
    missing: bool


def build_birth_to_trigger_followup_audit(
    data_root: Path | str = "/Volumes/ORICO/MemeTraderPro",
    *,
    output_dir: Path | str | None = None,
    write_outputs: bool = True,
) -> tuple[dict[str, Any], dict[str, Path]]:
    data_root = Path(data_root).expanduser()
    observation_root = data_root / "data" / "forward_observation" / "efficient_movers"
    report_root = (
        Path(output_dir).expanduser()
        if output_dir
        else data_root / "data" / "backtests" / "diagnostics" / "reports" / "forward_observation" / "efficient_movers"
    )
    candidates = _load_jsonl(observation_root / "candidates.jsonl")
    paths = _load_jsonl(observation_root / "candidate_paths.jsonl")
    events = _load_jsonl(observation_root / "candidate_events.jsonl")

    birth_candidates = [_candidate for _candidate in candidates.rows if _is_birth_watch_candidate(_candidate)]
    paths_by_mint = _group_by_mint(paths.rows)
    events_by_mint = _group_by_mint(events.rows)
    per_mint = [
        _birth_followup_row(candidate, paths_by_mint.get(_mint(candidate), []), events_by_mint.get(_mint(candidate), []))
        for candidate in birth_candidates
        if _mint(candidate)
    ]
    per_mint.sort(key=lambda row: (row["birth_observed_at"] if row["birth_observed_at"] is not None else float("inf"), row["mint"]))

    trigger_counts = {
        level: sum(1 for row in per_mint if row.get(f"first_crossed_{level}_time") is not None)
        for level in TRIGGER_LEVELS
    }
    conversion_funnel = _conversion_funnel(per_mint, trigger_counts)
    followup_status_counts = Counter(row["followup_status"] for row in per_mint)
    summary = {
        "report_id": REPORT_ID,
        "data_root": str(data_root),
        "observation_root": str(observation_root),
        "report_root": str(report_root),
        "total_birth_watch_candidates": len(birth_candidates),
        "unique_birth_watch_mints": len({row["mint"] for row in per_mint}),
        "birth_mints_with_followup_fdv": sum(1 for row in per_mint if row["followup_fdv_path_rows"] > 0),
        "birth_mints_with_any_trigger_cross": sum(1 for row in per_mint if row["first_trigger_level"] is not None),
        "trigger_cross_counts": trigger_counts,
        "conversion_funnel": conversion_funnel,
        "followup_status_counts": dict(followup_status_counts),
        "file_row_counts": {
            "candidates": len(candidates.rows),
            "candidate_paths": len(paths.rows),
            "candidate_events": len(events.rows),
        },
        "malformed_row_counts": {
            "candidates": candidates.malformed_rows,
            "candidate_paths": paths.malformed_rows,
            "candidate_events": events.malformed_rows,
        },
        "missing_files": [
            name
            for name, loaded in {"candidates": candidates, "candidate_paths": paths, "candidate_events": events}.items()
            if loaded.missing
        ],
        "per_mint": per_mint,
        "readiness_classification": _classify_readiness(per_mint),
        "recommendation": _recommendation(per_mint),
        "guardrails": GUARDRAILS,
        "network_calls_made": 0,
    }
    paths_out: dict[str, Path] = {}
    if write_outputs:
        report_root.mkdir(parents=True, exist_ok=True)
        paths_out = {
            "per_mint_csv": _write_csv(report_root / OUTPUT_NAMES["per_mint_csv"], per_mint),
            "summary_json": _write_json(report_root / OUTPUT_NAMES["summary_json"], summary),
            "summary_markdown": _write_markdown(report_root / OUTPUT_NAMES["summary_md"], summary),
        }
    return summary, paths_out


def _birth_followup_row(
    candidate: dict[str, Any],
    mint_paths: list[dict[str, Any]],
    mint_events: list[dict[str, Any]],
) -> dict[str, Any]:
    birth_observation_id = str(candidate.get("observation_id") or "")
    followup_paths = [row for row in mint_paths if _is_followup_path(row, birth_observation_id)]
    fdv_paths = [row for row in followup_paths if _num(row.get("fdv_proxy")) is not None]
    fdv_paths.sort(key=lambda row: (_num(row.get("timestamp") or row.get("observed_at")) or float("inf")))
    fdv_values = [_num(row.get("fdv_proxy")) for row in fdv_paths]
    fdv_values = [value for value in fdv_values if value is not None]
    first_fdv_row = fdv_paths[0] if fdv_paths else {}
    first_cross = {level: _first_cross_time(fdv_paths, threshold) for level, threshold in TRIGGER_LEVELS.items()}
    first_trigger_level = next((level for level in TRIGGER_LEVELS if first_cross[level] is not None), None)
    birth_observed_at = _num(candidate.get("observed_at") or candidate.get("first_seen_time"))
    first_followup_time = _num(first_fdv_row.get("timestamp") or first_fdv_row.get("observed_at")) if first_fdv_row else None
    return {
        "observation_id": birth_observation_id,
        "mint": _mint(candidate),
        "creator": candidate.get("creator"),
        "source": candidate.get("source"),
        "birth_observed_at": birth_observed_at,
        "launch_time": _num(candidate.get("launch_time")),
        "birth_event_type": candidate.get("event_type"),
        "followup_path_rows": len(followup_paths),
        "followup_fdv_path_rows": len(fdv_paths),
        "followup_event_rows": sum(1 for row in mint_events if not _is_create_event(row)),
        "first_followup_fdv_time": first_followup_time,
        "seconds_from_birth_to_first_fdv": _delta(birth_observed_at, first_followup_time),
        "first_fdv_proxy": _num(first_fdv_row.get("fdv_proxy")) if first_fdv_row else None,
        "max_fdv_proxy": max(fdv_values) if fdv_values else None,
        "first_trigger_level": first_trigger_level,
        **{f"first_crossed_{level}_time": value for level, value in first_cross.items()},
        "followup_status": _followup_status(fdv_paths, first_trigger_level),
    }


def _is_birth_watch_candidate(row: dict[str, Any]) -> bool:
    if row.get("freshness_lane") == "birth_watch":
        return True
    if row.get("candidate_classification") == "pumpfun_birth_candidate_observed":
        return True
    source = str(row.get("source") or "").lower()
    return row.get("event_type") == "pumpfun_create" and "create_scanner" in source


def _is_followup_path(row: dict[str, Any], birth_observation_id: str) -> bool:
    if _is_create_event(row):
        return False
    return True


def _is_create_event(row: dict[str, Any]) -> bool:
    return row.get("event_type") == "pumpfun_create"


def _group_by_mint(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        mint = _mint(row)
        if mint:
            grouped[mint].append(row)
    return grouped


def _mint(row: dict[str, Any]) -> str:
    return str(row.get("mint") or row.get("token_mint") or "")


def _first_cross_time(paths: list[dict[str, Any]], threshold: float) -> float | None:
    times = [
        _num(row.get("timestamp") or row.get("observed_at"))
        for row in paths
        if (_num(row.get("fdv_proxy")) is not None and _num(row.get("fdv_proxy")) >= threshold)
    ]
    times = [value for value in times if value is not None]
    return min(times) if times else None


def _followup_status(fdv_paths: list[dict[str, Any]], first_trigger_level: str | None) -> str:
    if first_trigger_level:
        return "trigger_followup_observed"
    if fdv_paths:
        return "fdv_followup_below_trigger"
    return "needs_followup_collection"


def _classify_readiness(per_mint: list[dict[str, Any]]) -> str:
    if not per_mint:
        return "birth_to_trigger_no_birth_candidates"
    if any(row["first_trigger_level"] for row in per_mint):
        return "birth_to_trigger_followup_observed"
    if any(row["followup_fdv_path_rows"] > 0 for row in per_mint):
        return "birth_to_trigger_fdv_followup_below_trigger"
    return "birth_to_trigger_needs_followup_collection"


def _recommendation(per_mint: list[dict[str, Any]]) -> str:
    readiness = _classify_readiness(per_mint)
    if readiness == "birth_to_trigger_followup_observed":
        return "Review triggered birth-watch mints and continue bounded follow-up collection."
    if readiness == "birth_to_trigger_fdv_followup_below_trigger":
        return "Continue bounded follow-up; FDV is appearing but no trigger crossing has been observed yet."
    if readiness == "birth_to_trigger_needs_followup_collection":
        return "Run bounded birth-watch follow-up collection for the current birth-watch mints before judging trigger quality."
    return "Run the birth-watch scanner before follow-up auditing."


def _conversion_funnel(
    per_mint: list[dict[str, Any]],
    trigger_counts: dict[str, int],
    *,
    target_trigger_qualified_sample: int = 300,
) -> dict[str, Any]:
    births = len(per_mint)
    fdv_followup = sum(1 for row in per_mint if row["followup_fdv_path_rows"] > 0)
    crossed_10k = int(trigger_counts.get("10k", 0))
    crossed_15k = int(trigger_counts.get("15k", 0))
    crossed_20k = int(trigger_counts.get("20k", 0))
    crossed_30k = int(trigger_counts.get("30k", 0))
    crossed_50k = int(trigger_counts.get("50k", 0))
    crossed_100k = int(trigger_counts.get("100k", 0))
    crossed_500k = int(trigger_counts.get("500k", 0))
    crossed_1m = int(trigger_counts.get("1m", 0))
    return {
        "birth_watch_mints": births,
        "births_with_fdv_followup": fdv_followup,
        "crossed_10k": crossed_10k,
        "crossed_15k": crossed_15k,
        "crossed_20k": crossed_20k,
        "crossed_30k": crossed_30k,
        "crossed_50k": crossed_50k,
        "crossed_100k": crossed_100k,
        "crossed_500k": crossed_500k,
        "crossed_1m": crossed_1m,
        "fdv_followup_rate": _rate(fdv_followup, births),
        "birth_to_10k_conversion_rate": _rate(crossed_10k, births),
        "birth_to_15k_conversion_rate": _rate(crossed_15k, births),
        "birth_to_20k_conversion_rate": _rate(crossed_20k, births),
        "birth_to_30k_conversion_rate": _rate(crossed_30k, births),
        "birth_to_50k_conversion_rate": _rate(crossed_50k, births),
        "birth_to_100k_conversion_rate": _rate(crossed_100k, births),
        "birth_to_500k_conversion_rate": _rate(crossed_500k, births),
        "birth_to_1m_conversion_rate": _rate(crossed_1m, births),
        "10k_to_20k_conversion_rate": _rate(crossed_20k, crossed_10k),
        "20k_to_100k_conversion_rate": _rate(crossed_100k, crossed_20k),
        "target_trigger_qualified_sample": target_trigger_qualified_sample,
        "target_trigger_qualified_progress_10k": f"{crossed_10k}/{target_trigger_qualified_sample}",
        "target_trigger_qualified_progress_20k": f"{crossed_20k}/{target_trigger_qualified_sample}",
        "estimated_births_needed_for_300_crossed_10k": _estimated_births_needed(target_trigger_qualified_sample, crossed_10k, births),
        "estimated_births_needed_for_300_crossed_20k": _estimated_births_needed(target_trigger_qualified_sample, crossed_20k, births),
    }


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 6)


def _estimated_births_needed(target: int, crossed: int, births: int) -> int | None:
    if crossed <= 0 or births <= 0:
        return None
    return int(ceil(target / (crossed / births)))


def _load_jsonl(path: Path) -> LoadedJsonl:
    if not path.exists():
        return LoadedJsonl(rows=[], malformed_rows=0, missing=True)
    rows: list[dict[str, Any]] = []
    malformed = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if isinstance(value, dict):
                rows.append(value)
            else:
                malformed += 1
    return LoadedJsonl(rows=rows, malformed_rows=malformed, missing=False)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_markdown(path: Path, summary: dict[str, Any]) -> Path:
    lines = [
        "# Birth-to-Trigger Follow-up Audit",
        "",
        "- Guardrail: audit-only; no collection, Helius calls, trading, backtest, validation, or strategy work.",
        f"- Birth-watch candidates: `{summary['total_birth_watch_candidates']}`",
        f"- Unique birth-watch mints: `{summary['unique_birth_watch_mints']}`",
        f"- Mints with later FDV evidence: `{summary['birth_mints_with_followup_fdv']}`",
        f"- Mints with any trigger crossing: `{summary['birth_mints_with_any_trigger_cross']}`",
        f"- Trigger cross counts: `{summary['trigger_cross_counts']}`",
        f"- Conversion funnel: `{summary['conversion_funnel']}`",
        f"- Follow-up statuses: `{summary['followup_status_counts']}`",
        f"- Readiness classification: `{summary['readiness_classification']}`",
        f"- Recommendation: `{summary['recommendation']}`",
        "",
        "## Per-mint Status",
        "",
    ]
    for row in summary["per_mint"]:
        lines.append(
            "- "
            f"`{row['mint']}`: status=`{row['followup_status']}`, "
            f"first_fdv=`{row['first_fdv_proxy']}`, max_fdv=`{row['max_fdv_proxy']}`, "
            f"first_trigger=`{row['first_trigger_level']}`"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _delta(start: float | None, end: float | None) -> float | None:
    if start is None or end is None:
        return None
    return end - start
