"""Dry-run P0 Helius enrichment planners for structural runner fingerprinting."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from research.mtp_research.data_paths import data_lake_path


MASTER_PLAN_PATH = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "structural_enrichment_master_plan", "structural_enrichment_master_plan_summary.json"
)
MASTER_PRIORITY_PATH = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "structural_enrichment_master_plan", "structural_enrichment_priority_rank.csv"
)
MASTER_BUDGET_PATH = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "structural_enrichment_master_plan", "helius_enrichment_budget_plan.csv"
)
REPEATED_BUYER_REPORT_PATH = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "repeated_buyer_runner_participation",
    "repeated_buyer_runner_participation_summary.json",
)
FUNDING_LINK_PATH = data_lake_path("data", "backtests", "funding_link", "funding_link_pilot.jsonl")
DEFAULT_OUTPUT_DIR = data_lake_path("data", "backtests", "diagnostics", "reports", "p0_helius_planners")
DEFAULT_STATUS_PATH = Path("theses/P0_HELIUS_ENRICHMENT_PLANNERS_STATUS.md")

PILOT_ALIASES = {
    "top-holder": "top_holder_milestone_snapshot_pilot",
    "early-buyer-history": "early_buyer_wallet_history_pilot",
    "creator-funder-graph": "creator_funder_transfer_graph_pilot",
}
PILOT_ORDER = [
    "top_holder_milestone_snapshot_pilot",
    "early_buyer_wallet_history_pilot",
    "creator_funder_transfer_graph_pilot",
]
MILESTONE_FIELDS = {
    "20k": "crossing_20k_age",
    "50k": "crossing_50k_age",
    "100k": "crossing_100k_age",
    "500k": "crossing_500k_age",
    "1m": "crossing_1m_age",
}
WINNER_TIERS = {
    "reached_100k_but_never_200k",
    "reached_200k_but_never_500k",
    "reached_500k_but_never_1m",
    "reached_1m_plus",
}
FAILURE_TIERS = {"reached_20k_but_never_50k", "never_reached_20k"}


class ExecuteRejectedError(RuntimeError):
    """Raised when a caller requests execution in this dry-run-only sprint."""


def build_p0_helius_enrichment_plans(
    *,
    master_plan_path: Path | str = MASTER_PLAN_PATH,
    master_priority_path: Path | str = MASTER_PRIORITY_PATH,
    master_budget_path: Path | str = MASTER_BUDGET_PATH,
    repeated_buyer_report_path: Path | str = REPEATED_BUYER_REPORT_PATH,
    event_paths: list[Path | str] | None = None,
    funding_link_path: Path | str | None = FUNDING_LINK_PATH,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    status_path: Path | str = DEFAULT_STATUS_PATH,
    pilot: str = "all",
    credit_cap_per_pilot: int = 25_000,
    total_credit_cap: int = 70_000,
    max_launches: int | None = 250,
    max_wallets: int | None = 1_000,
    max_creators: int | None = 250,
    max_mints: int | None = 250,
    dry_run: bool = True,
    execute: bool = False,
) -> tuple[dict[str, Any], dict[str, Path]]:
    if execute:
        raise ExecuteRejectedError("--execute is rejected in this sprint; planners are dry-run only and make no Helius calls.")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    selected_pilots = _selected_pilots(pilot)
    master_plan = _read_json(master_plan_path)
    priority_rows = _read_csv(master_priority_path)
    budget_rows = _read_csv(master_budget_path)
    _verify_master_plan(master_plan, priority_rows, budget_rows)
    repeated_report = _read_json(repeated_buyer_report_path)
    launch_rows = _normalize_launch_rows(repeated_report.get("launch_feature_rows") or [])
    resolved_event_paths = event_paths if event_paths is not None else [Path(path) for path in (repeated_report.get("dataset") or {}).get("event_paths", [])]
    funding_rows = _read_jsonl(funding_link_path)

    top_holder_targets = _select_top_holder_targets(launch_rows, max_mints=max_mints, max_launches=max_launches)
    early_buyer_targets = _select_early_buyer_targets(
        launch_rows,
        event_paths=resolved_event_paths,
        max_wallets=max_wallets,
        max_launches=max_launches,
    )
    creator_funder_targets = _select_creator_funder_targets(
        launch_rows,
        funding_rows=funding_rows,
        max_creators=max_creators,
        max_launches=max_launches,
    )
    targets_by_pilot = {
        "top_holder_milestone_snapshot_pilot": top_holder_targets,
        "early_buyer_wallet_history_pilot": early_buyer_targets,
        "creator_funder_transfer_graph_pilot": creator_funder_targets,
    }
    plan_budget = _budget_by_pilot(master_plan, budget_rows)
    pilot_plans = [
        _pilot_plan(
            pilot_id=pilot_id,
            targets=targets_by_pilot[pilot_id],
            projected_credits=plan_budget[pilot_id],
            credit_cap_per_pilot=credit_cap_per_pilot,
            output_dir=output,
        )
        for pilot_id in selected_pilots
    ]
    combined_projected = sum(int(row["projected_credits"]) for row in pilot_plans)
    overall = _overall_classification(pilot_plans, combined_projected, total_credit_cap)
    report = {
        "report_id": "p0_helius_enrichment_planners_v0",
        "report_type": "dry_run_p0_helius_enrichment_planners",
        "overall_classification": overall,
        "methodology_flags": [
            "research_only",
            "dry_run_only",
            "no_network_calls",
            "no_helius_calls",
            "no_live_trading",
            "no_paper_trading",
            "no_auto_buy_sell",
            "no_private_key_logic",
            "no_wallet_execution",
            "no_order_routing",
            "no_alerts",
            "no_trading_logic",
            "no_profitability_claims",
            "no_strategy_generation",
            "no_validation_run",
            "no_backtest",
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml_black_boxes",
            "wallet_structure_proxy",
            "funder_link_proxy",
            "top_holder_behavior_proxy",
            "repeated_buyer_proxy",
            "fdv_proxy_not_true_market_cap",
        ],
        "dry_run": dry_run,
        "execute_requested": execute,
        "network_calls_made": 0,
        "selected_pilots": selected_pilots,
        "pilot_plans": pilot_plans,
        "combined_projected_credits": combined_projected,
        "credit_cap_per_pilot": credit_cap_per_pilot,
        "total_credit_cap": total_credit_cap,
        "master_plan_verification": {
            "p0_fields_present": True,
            "recommended_pilots_present": all(pilot_id in plan_budget for pilot_id in PILOT_ORDER),
            "budget_caps_respected_in_master_plan": all(plan_budget[pilot_id] <= 25_000 for pilot_id in PILOT_ORDER),
        },
        "next_recommended_action": "Review dry-run target previews, then approve exactly one capped pilot if the target set is acceptable.",
        "explicit_warning": "No Helius calls were made. These planners only prepare target previews and budget projections.",
    }
    paths = write_p0_helius_enrichment_planner_outputs(
        report,
        top_holder_targets=top_holder_targets,
        early_buyer_targets=early_buyer_targets,
        creator_funder_targets=creator_funder_targets,
        output_dir=output,
        status_path=status_path,
    )
    return report, paths


def write_p0_helius_enrichment_planner_outputs(
    report: dict[str, Any],
    *,
    top_holder_targets: list[dict[str, Any]],
    early_buyer_targets: list[dict[str, Any]],
    creator_funder_targets: list[dict[str, Any]],
    output_dir: Path,
    status_path: Path | str,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_json = output_dir / "p0_helius_planner_summary.json"
    summary_md = output_dir / "p0_helius_planner_summary.md"
    budget_csv = output_dir / "p0_helius_budget_projection.csv"
    top_holder_csv = output_dir / "top_holder_snapshot_targets.csv"
    early_buyer_csv = output_dir / "early_buyer_wallet_history_targets.csv"
    creator_funder_csv = output_dir / "creator_funder_transfer_graph_targets.csv"
    status = Path(status_path)
    summary_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    summary_md.write_text(_markdown(report), encoding="utf-8")
    _write_csv(report["pilot_plans"], budget_csv)
    _write_csv(top_holder_targets, top_holder_csv)
    _write_csv(early_buyer_targets, early_buyer_csv)
    _write_csv(creator_funder_targets, creator_funder_csv)
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(_status_markdown(report, summary_json, summary_md, budget_csv, top_holder_csv, early_buyer_csv, creator_funder_csv), encoding="utf-8")
    return {
        "summary_json_path": summary_json,
        "summary_markdown_path": summary_md,
        "budget_projection_path": budget_csv,
        "top_holder_targets_path": top_holder_csv,
        "early_buyer_targets_path": early_buyer_csv,
        "creator_funder_targets_path": creator_funder_csv,
        "status_path": status,
    }


def _selected_pilots(pilot: str) -> list[str]:
    if pilot == "all":
        return list(PILOT_ORDER)
    if pilot not in PILOT_ALIASES:
        raise ValueError(f"Unknown pilot: {pilot}")
    return [PILOT_ALIASES[pilot]]


def _verify_master_plan(master_plan: dict[str, Any], priority_rows: list[dict[str, str]], budget_rows: list[dict[str, str]]) -> None:
    p0_present = any(row.get("priority") == "P0" for row in priority_rows) or any(
        row.get("priority") == "P0" for row in master_plan.get("priority_rank", [])
    )
    budget_ids = {row.get("plan_id") for row in budget_rows} | {row.get("plan_id") for row in master_plan.get("helius_budget_plan", [])}
    missing = [pilot_id for pilot_id in PILOT_ORDER if pilot_id not in budget_ids]
    if not p0_present:
        raise ValueError("Structural enrichment master plan does not contain P0 priorities.")
    if missing:
        raise ValueError(f"Structural enrichment master plan missing pilots: {missing}")


def _budget_by_pilot(master_plan: dict[str, Any], budget_rows: list[dict[str, str]]) -> dict[str, int]:
    rows = list(master_plan.get("helius_budget_plan", [])) + budget_rows
    output: dict[str, int] = {}
    for pilot_id in PILOT_ORDER:
        values = [
            _int_or_none(row.get("estimated_credits"))
            for row in rows
            if row.get("plan_id") == pilot_id and _int_or_none(row.get("estimated_credits")) is not None
        ]
        output[pilot_id] = values[0] if values else 25_000
    return output


def _normalize_launch_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        mint = row.get("mint") or row.get("token_mint")
        if not mint:
            continue
        normalized.append(
            {
                "launch_id": row.get("launch_id") or f"launch-{mint}",
                "mint": str(mint),
                "creator": row.get("creator") or "",
                "launch_ts": _int_or_none(row.get("launch_ts")),
                "launch_date": row.get("launch_date") or "",
                "milestone_tier": row.get("milestone_tier") or "never_reached_20k",
                **{field: _int_or_none(row.get(field)) for field in MILESTONE_FIELDS.values()},
            }
        )
    return normalized


def _select_top_holder_targets(
    launch_rows: list[dict[str, Any]],
    *,
    max_mints: int | None,
    max_launches: int | None,
) -> list[dict[str, Any]]:
    selected_launches = _balanced_launch_selection(
        [row for row in launch_rows if row.get("crossing_20k_age") is not None],
        max_launches=max_launches,
        max_mints=max_mints,
    )
    targets = []
    for row in selected_launches:
        for milestone, field in MILESTONE_FIELDS.items():
            age = row.get(field)
            if age is None:
                continue
            targets.append(
                {
                    "launch_id": row["launch_id"],
                    "mint": row["mint"],
                    "creator": row["creator"],
                    "milestone": milestone,
                    "milestone_time": (row.get("launch_ts") or 0) + age if row.get("launch_ts") else "",
                    "milestone_age_seconds": age,
                    "milestone_tier": row["milestone_tier"],
                    "reason_selected": _reason_for_launch(row),
                }
            )
    return targets


def _select_early_buyer_targets(
    launch_rows: list[dict[str, Any]],
    *,
    event_paths: list[Path | str],
    max_wallets: int | None,
    max_launches: int | None,
) -> list[dict[str, Any]]:
    selected_launches = _balanced_launch_selection(
        [row for row in launch_rows if row.get("crossing_20k_age") is not None],
        max_launches=max_launches,
        max_mints=None,
    )
    launch_by_mint = {row["mint"]: row for row in selected_launches}
    rows_by_wallet: dict[str, dict[str, Any]] = {}
    for event in _iter_jsonl(event_paths):
        mint = event.get("token_mint") or event.get("mint")
        actor = event.get("actor")
        if not mint or mint not in launch_by_mint or not actor or not _is_buy_event(event):
            continue
        launch = launch_by_mint[str(mint)]
        age = _event_age(event, launch.get("launch_ts"))
        if age is None or age < 0 or age > (launch.get("crossing_20k_age") or 0):
            continue
        wallet = str(actor)
        if wallet in rows_by_wallet:
            continue
        rows_by_wallet[wallet] = {
            "wallet": wallet,
            "current_launch_id": launch["launch_id"],
            "current_mint": launch["mint"],
            "current_milestone_tier": launch["milestone_tier"],
            "first_seen_in_launch_time": event.get("block_time") or "",
            "launch_age_seconds": age,
            "reason_selected": "early_buyer_before_20k_trigger",
        }
        if max_wallets and len(rows_by_wallet) >= max_wallets:
            break
    return sorted(rows_by_wallet.values(), key=lambda row: (row["current_launch_id"], row["wallet"]))


def _select_creator_funder_targets(
    launch_rows: list[dict[str, Any]],
    *,
    funding_rows: list[dict[str, Any]],
    max_creators: int | None,
    max_launches: int | None,
) -> list[dict[str, Any]]:
    launch_by_mint = {row["mint"]: row for row in launch_rows}
    launch_by_id = {row["launch_id"]: row for row in launch_rows}
    candidate_rows = []
    for funding in funding_rows:
        mint = str(funding.get("mint") or funding.get("token_mint") or "")
        launch_id = str(funding.get("launch_id") or "")
        launch = launch_by_mint.get(mint) or launch_by_id.get(launch_id)
        if not launch:
            continue
        candidate_rows.append((launch, funding))

    candidate_rows.sort(
        key=lambda item: (
            0 if item[1].get("candidate_funding_wallet") else 1,
            _launch_sort_key(item[0]),
            str(item[1].get("creator") or ""),
            str(item[1].get("candidate_funding_wallet") or ""),
        )
    )
    rows = []
    creators_seen: set[str] = set()
    for launch, funding in candidate_rows:
        creator = str(funding.get("creator") or launch.get("creator") or "")
        if not creator:
            continue
        if max_creators and creator not in creators_seen and len(creators_seen) >= max_creators:
            continue
        creators_seen.add(creator)
        rows.append(
            {
                "launch_id": launch["launch_id"],
                "mint": launch["mint"],
                "creator": creator,
                "milestone_tier": launch["milestone_tier"],
                "candidate_funder": funding.get("candidate_funding_wallet") or "",
                "funding_signature": funding.get("candidate_funding_signature") or "",
                "common_funder_candidate_id": funding.get("common_funder_candidate_id") or "",
                "reason_selected": "creator_with_candidate_funder_from_pilot"
                if funding.get("candidate_funding_wallet")
                else "creator_without_prior_funding_trace_contrast",
            }
        )
        if max_launches and len(rows) >= max_launches:
            break
    return rows


def _balanced_launch_selection(
    rows: list[dict[str, Any]],
    *,
    max_launches: int | None,
    max_mints: int | None,
) -> list[dict[str, Any]]:
    tier_order = [
        "reached_1m_plus",
        "reached_500k_but_never_1m",
        "reached_100k_but_never_200k",
        "reached_200k_but_never_500k",
        "reached_20k_but_never_50k",
        "reached_50k_but_never_100k",
        "never_reached_20k",
    ]
    grouped = {tier: sorted([row for row in rows if row["milestone_tier"] == tier], key=_launch_sort_key) for tier in tier_order}
    selected: list[dict[str, Any]] = []
    seen_mints: set[str] = set()
    while True:
        progressed = False
        for tier in tier_order:
            group = grouped[tier]
            if not group:
                continue
            candidate = group.pop(0)
            if candidate["mint"] in seen_mints:
                continue
            selected.append(candidate)
            seen_mints.add(candidate["mint"])
            progressed = True
            if max_launches and len(selected) >= max_launches:
                return selected
            if max_mints and len(seen_mints) >= max_mints:
                return selected
        if not progressed:
            break
    return selected


def _pilot_plan(
    *,
    pilot_id: str,
    targets: list[dict[str, Any]],
    projected_credits: int,
    credit_cap_per_pilot: int,
    output_dir: Path,
) -> dict[str, Any]:
    target_counts = _target_counts(pilot_id, targets)
    projected_calls = _projected_calls(pilot_id, targets)
    has_winner = any(row.get("milestone_tier") in WINNER_TIERS or row.get("current_milestone_tier") in WINNER_TIERS for row in targets)
    has_failure = any(row.get("milestone_tier") in FAILURE_TIERS or row.get("current_milestone_tier") in FAILURE_TIERS for row in targets)
    if not targets:
        readiness = "planner_blocked_missing_targets"
    elif projected_credits > credit_cap_per_pilot:
        readiness = "planner_blocked_budget"
    elif pilot_id == "early_buyer_wallet_history_pilot":
        readiness = "planner_ready_for_review"
    elif pilot_id == "creator_funder_transfer_graph_pilot" and target_counts.get("candidate_funders_selected", 0) > 0:
        readiness = "planner_ready_for_review"
    elif not (has_winner and has_failure):
        readiness = "planner_needs_target_adjustment"
    else:
        readiness = "planner_ready_for_review"
    return {
        "pilot_id": pilot_id,
        "readiness_classification": readiness,
        "projected_calls": projected_calls,
        "projected_credits": projected_credits,
        "credit_cap": credit_cap_per_pilot,
        "target_counts": target_counts,
        "raw_response_storage_path": str(data_lake_path("data", "raw", "structural_enrichment", pilot_id)),
        "parsed_output_storage_path": str(data_lake_path("data", "backtests", "structural_enrichment", f"{pilot_id}.jsonl")),
        "checkpoint_path": str(data_lake_path("data", "backtests", "structural_enrichment", "checkpoints", f"{pilot_id}.json")),
        "stop_conditions": "auth_error;rate_limit;projected_budget_exceeded;actual_budget_exceeded;low_field_yield",
        "no_network_calls_made": True,
    }


def _target_counts(pilot_id: str, targets: list[dict[str, Any]]) -> dict[str, int]:
    if pilot_id == "top_holder_milestone_snapshot_pilot":
        return {
            "mints_selected": len({row["mint"] for row in targets}),
            "milestone_snapshots_selected": len(targets),
        }
    if pilot_id == "early_buyer_wallet_history_pilot":
        return {
            "wallets_selected": len({row["wallet"] for row in targets}),
            "launches_covered": len({row["current_launch_id"] for row in targets}),
        }
    return {
        "creators_selected": len({row["creator"] for row in targets if row.get("creator")}),
        "candidate_funders_selected": len({row["candidate_funder"] for row in targets if row.get("candidate_funder")}),
        "launches_covered": len({row["launch_id"] for row in targets}),
    }


def _projected_calls(pilot_id: str, targets: list[dict[str, Any]]) -> int:
    if pilot_id == "top_holder_milestone_snapshot_pilot":
        return max(1, len(targets))
    if pilot_id == "early_buyer_wallet_history_pilot":
        return max(1, len({row["wallet"] for row in targets}) * 2)
    return max(1, len(targets) * 3)


def _overall_classification(pilot_plans: list[dict[str, Any]], combined_projected: int, total_credit_cap: int) -> str:
    if not pilot_plans or any(row["readiness_classification"].startswith("planner_blocked") for row in pilot_plans):
        return "p0_helius_planners_blocked"
    if combined_projected > total_credit_cap:
        return "p0_helius_planners_need_adjustment"
    if all(row["readiness_classification"] == "planner_ready_for_review" for row in pilot_plans):
        return "p0_helius_planners_ready_for_user_review"
    return "p0_helius_planners_need_adjustment"


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# P0 Helius Enrichment Planners",
        "",
        f"Overall classification: `{report['overall_classification']}`",
        "",
        "Dry-run only. No Helius calls, network calls, trading logic, or execution logic were run.",
        "",
        "## Pilot Plans",
    ]
    for row in report["pilot_plans"]:
        lines.append(
            f"- {row['pilot_id']}: {row['readiness_classification']}, "
            f"credits={row['projected_credits']}, calls={row['projected_calls']}"
        )
    lines.extend(
        [
            "",
            f"Combined projected credits: {report['combined_projected_credits']}",
            "",
            f"Next recommended action: {report['next_recommended_action']}",
        ]
    )
    return "\n".join(lines) + "\n"


def _status_markdown(
    report: dict[str, Any],
    summary_json: Path,
    summary_md: Path,
    budget_csv: Path,
    top_holder_csv: Path,
    early_buyer_csv: Path,
    creator_funder_csv: Path,
) -> str:
    lines = [
        "# P0 Helius Enrichment Planners Status",
        "",
        "## Why These Planners Were Created",
        "The structural enrichment master plan requires capped dry-run planners before any Helius collection for top-holder, early-buyer wallet history, and creator/funder transfer graph fields.",
        "",
        f"Overall classification: `{report['overall_classification']}`",
        "",
        "## Pilots Included",
    ]
    for row in report["pilot_plans"]:
        lines.append(
            f"- {row['pilot_id']}: targets={row['target_counts']}, "
            f"projected_credits={row['projected_credits']}, readiness={row['readiness_classification']}"
        )
    lines.extend(
        [
            "",
            f"Combined projected credits: {report['combined_projected_credits']}",
            "",
            "## Warning",
            "No Helius calls were made. This sprint produced dry-run target previews only.",
            "",
            "## Next Recommended Action",
            report["next_recommended_action"],
            "",
            "## Artifacts",
            f"- Summary JSON: {summary_json}",
            f"- Summary Markdown: {summary_md}",
            f"- Budget Projection: {budget_csv}",
            f"- Top Holder Targets: {top_holder_csv}",
            f"- Early Buyer Targets: {early_buyer_csv}",
            f"- Creator/Funder Targets: {creator_funder_csv}",
            "",
        ]
    )
    return "\n".join(lines)


def _read_json(path: Path | str) -> dict[str, Any]:
    value = Path(path)
    if not value.exists():
        return {}
    return json.loads(value.read_text(encoding="utf-8"))


def _read_jsonl(path: Path | str | None) -> list[dict[str, Any]]:
    if not path:
        return []
    value = Path(path)
    if not value.exists():
        return []
    rows = []
    with value.open("r", encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    return rows


def _read_csv(path: Path | str) -> list[dict[str, str]]:
    value = Path(path)
    if not value.exists():
        return []
    with value.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = sorted({key for row in rows for key in row}) or ["empty"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def _iter_jsonl(paths: list[Path | str]) -> Any:
    for path in paths:
        value = Path(path)
        if not value.exists():
            continue
        with value.open("r", encoding="utf-8") as f:
            for line in f:
                text = line.strip()
                if text:
                    yield json.loads(text)


def _is_buy_event(event: dict[str, Any]) -> bool:
    side = str(event.get("side") or "").lower()
    event_type = str(event.get("event_type") or "").lower()
    return side in {"buy", "accumulate"} or event_type == "token_accumulation"


def _event_age(event: dict[str, Any], launch_ts: int | None) -> int | None:
    block_time = _int_or_none(event.get("block_time"))
    if block_time is None or launch_ts is None:
        return None
    return block_time - launch_ts


def _reason_for_launch(row: dict[str, Any]) -> str:
    tier = row.get("milestone_tier")
    if tier == "reached_1m_plus":
        return "1m_plus_runner"
    if tier == "reached_500k_but_never_1m":
        return "500k_plus_runner"
    if tier in WINNER_TIERS:
        return "100k_plus_runner"
    if tier == "reached_20k_but_never_50k":
        return "failed_20k_trigger_contrast"
    if tier == "never_reached_20k":
        return "never_20k_contrast"
    return "milestone_trigger_launch"


def _launch_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (row.get("launch_date") or "", row.get("creator") or "", row.get("mint") or "")


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
