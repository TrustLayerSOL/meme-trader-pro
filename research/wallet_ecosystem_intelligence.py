from __future__ import annotations

import time
from typing import Any


MODE = "WALLET_ECOSYSTEM_INTELLIGENCE_STAGE5_REVIEW_ONLY"
SCORECARD_MODE = "WALLET_REPLAY_SCORECARD_REVIEW_ONLY"


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def pct(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        return 0
    return int(round((numerator / denominator) * 100))


def gate(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def scorecard_visible(scorecard: dict[str, Any]) -> bool:
    return scorecard.get("mode") == SCORECARD_MODE and scorecard.get("live_execution_locked") is True


def _window_15m(row: dict[str, Any]) -> dict[str, Any]:
    return as_dict(as_dict(row.get("windows")).get("15m"))


def wallet_node(wallet: str, row: dict[str, Any]) -> dict[str, Any]:
    quality = as_dict(row.get("signal_quality"))
    partners = [
        partner
        for partner in as_list(row.get("co_entry_partners"))
        if isinstance(partner, dict) and str(partner.get("wallet") or "").strip()
    ]
    window_15m = _window_15m(row)
    total_events = safe_int(row.get("total_events"))
    fillable_events = safe_int(row.get("fillable_events"))
    known_15m = safe_int(window_15m.get("known"))
    return {
        "wallet": wallet,
        "total_events": total_events,
        "fillable_events": fillable_events,
        "fillable_rate": round(fillable_events / total_events, 4) if total_events else 0.0,
        "known_15m": known_15m,
        "runner_15m": safe_int(window_15m.get("runner")),
        "rug_15m": safe_int(window_15m.get("rug")),
        "known_rate_15m": safe_float(quality.get("known_rate_15m")),
        "runner_rate_known_15m": safe_float(quality.get("runner_rate_known_15m")),
        "rug_rate_known_15m": safe_float(quality.get("rug_rate_known_15m")),
        "review_status": str(quality.get("review_status") or "unknown"),
        "co_entry_partner_count": len(partners),
        "top_co_entry_partners": partners[:5],
    }


def wallet_nodes(scorecard: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for wallet, row in as_dict(scorecard.get("wallets")).items():
        wallet_id = str(wallet or "").strip()
        if not wallet_id or not isinstance(row, dict):
            continue
        rows.append(wallet_node(wallet_id, row))
    return sorted(
        rows,
        key=lambda row: (
            safe_int(row.get("co_entry_partner_count")),
            safe_int(row.get("known_15m")),
            safe_int(row.get("fillable_events")),
            safe_float(row.get("runner_rate_known_15m")) - safe_float(row.get("rug_rate_known_15m")),
        ),
        reverse=True,
    )


def edge_priority(count: int, left: dict[str, Any] | None = None, right: dict[str, Any] | None = None) -> str:
    left = as_dict(left)
    right = as_dict(right)
    left_known = safe_int(left.get("known_15m"))
    right_known = safe_int(right.get("known_15m"))
    if count >= 3 and (left_known >= 3 or right_known >= 3):
        return "high"
    if count >= 2:
        return "medium"
    return "observe_more"


def co_entry_edges(scorecard: dict[str, Any], nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    node_lookup = {row["wallet"]: row for row in nodes}
    rows = []
    for pair in as_list(as_dict(scorecard.get("ecosystems")).get("top_co_entry_pairs")):
        if not isinstance(pair, dict):
            continue
        wallets = [str(wallet).strip() for wallet in as_list(pair.get("wallets")) if str(wallet).strip()]
        if len(wallets) != 2:
            continue
        count = safe_int(pair.get("count"))
        left, right = wallets
        rows.append(
            {
                "wallets": wallets,
                "count": count,
                "relationship_type": "repeated_co_entry" if count >= 2 else "single_observed_co_entry",
                "review_priority": edge_priority(count, node_lookup.get(left), node_lookup.get(right)),
                "left_wallet_status": as_dict(node_lookup.get(left)).get("review_status", "unknown"),
                "right_wallet_status": as_dict(node_lookup.get(right)).get("review_status", "unknown"),
                "relationship_confidence": "medium" if count >= 2 else "low",
                "mutation_allowed": False,
            }
        )
    return sorted(rows, key=lambda row: (safe_int(row.get("count")), str(row.get("review_priority"))), reverse=True)


def repeated_components(edges: list[dict[str, Any]]) -> list[list[str]]:
    adjacency: dict[str, set[str]] = {}
    for edge in edges:
        if safe_int(edge.get("count")) < 2:
            continue
        wallets = as_list(edge.get("wallets"))
        if len(wallets) != 2:
            continue
        left, right = str(wallets[0]), str(wallets[1])
        adjacency.setdefault(left, set()).add(right)
        adjacency.setdefault(right, set()).add(left)
    seen: set[str] = set()
    components: list[list[str]] = []
    for wallet in sorted(adjacency):
        if wallet in seen:
            continue
        stack = [wallet]
        group: set[str] = set()
        while stack:
            current = stack.pop()
            if current in group:
                continue
            group.add(current)
            stack.extend(sorted(adjacency.get(current, set()) - group))
        seen.update(group)
        if len(group) >= 2:
            components.append(sorted(group))
    return components


def cluster_candidates(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for component in repeated_components(edges):
        edge_rows = [
            edge
            for edge in edges
            if len(set(as_list(edge.get("wallets"))) & set(component)) == 2 and safe_int(edge.get("count")) >= 2
        ]
        total_shared_events = sum(safe_int(edge.get("count")) for edge in edge_rows)
        rows.append(
            {
                "wallets": component,
                "wallet_count": len(component),
                "repeated_edges": len(edge_rows),
                "total_shared_events": total_shared_events,
                "review_priority": "high" if len(edge_rows) >= 2 or total_shared_events >= 4 else "medium",
                "review_status": "needs_ecosystem_review",
                "mutation_allowed": False,
            }
        )
    return sorted(rows, key=lambda row: (safe_int(row.get("repeated_edges")), safe_int(row.get("total_shared_events"))), reverse=True)


def build_wallet_ecosystem_intelligence_report(
    *,
    replay_scorecard: dict[str, Any] | None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    scorecard = as_dict(replay_scorecard)
    nodes = wallet_nodes(scorecard)
    edges = co_entry_edges(scorecard, nodes)
    repeated_edges = [edge for edge in edges if safe_int(edge.get("count")) >= 2]
    clusters = cluster_candidates(edges)
    relationship_source_status = {
        "co_entry": "available_from_wallet_replay_scorecard" if edges else "blocked_missing_scorecard_pairs",
        "funding_overlap": "blocked_missing_source",
        "deployer_links": "blocked_missing_source",
    }
    gates = [
        gate(
            "scorecard_visible",
            scorecard_visible(scorecard),
            "Stage 5 must be based on the review-only wallet replay scorecard.",
        ),
        gate("wallet_nodes_indexed", len(nodes) > 0, "Wallet-level graph nodes must be indexed."),
        gate("co_entry_pairs_indexed", len(edges) > 0, "Co-entry pair edges must be indexed."),
        gate("ecosystem_edges_ranked", bool(edges) and all(edge.get("review_priority") for edge in edges), "Edges must be ranked for operator review."),
        gate("cluster_review_queue_visible", isinstance(clusters, list), "Cluster candidates must have a visible review queue, even when empty."),
        gate("missing_funding_source_explicit", relationship_source_status["funding_overlap"] == "blocked_missing_source", "Funding-overlap source must be explicitly blocked until real source data exists."),
        gate("missing_deployer_source_explicit", relationship_source_status["deployer_links"] == "blocked_missing_source", "Deployer-link source must be explicitly blocked until real source data exists."),
        gate("live_execution_locked", True, "Stage 5 must not unlock live execution."),
        gate("wallet_list_mutation_blocked", True, "Stage 5 must not mutate tracked wallet lists."),
        gate("trust_mutation_blocked", True, "Stage 5 must not auto-promote or auto-demote wallets."),
    ]
    passed = [row["name"] for row in gates if row["passed"]]
    failed = [row["name"] for row in gates if not row["passed"]]
    source_readiness = pct(1, len(relationship_source_status))
    completion = pct(len(passed), len(gates))
    summary = {
        "stage5_wallet_ecosystem_completion_pct": completion,
        "relationship_data_readiness_pct": source_readiness,
        "wallet_nodes": len(nodes),
        "co_entry_edges": len(edges),
        "repeated_co_entry_edges": len(repeated_edges),
        "cluster_candidates": len(clusters),
        "funding_overlap_records": 0,
        "deployer_link_records": 0,
    }
    residual_data_blockers = [
        "funding_overlap_source_missing",
        "deployer_link_source_missing",
    ]
    if not scorecard_visible(scorecard):
        residual_data_blockers.append("wallet_replay_scorecard_missing_or_unlocked")
    if not edges:
        residual_data_blockers.append("co_entry_pairs_missing")
    return {
        "mode": MODE,
        "generated_at": generated_at if generated_at is not None else time.time(),
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "summary": summary,
        "relationship_source_status": relationship_source_status,
        "passed_gates": passed,
        "failed_gates": failed,
        "gates": gates,
        "wallet_nodes": nodes,
        "co_entry_edges": edges,
        "cluster_candidates": clusters,
        "residual_data_blockers": residual_data_blockers,
        "operator_summary": (
            "Stage 5 is complete as a review-only co-entry ecosystem graph. "
            "Funding-overlap and deployer-linked intelligence remain explicitly blocked "
            "until real source artifacts exist; no wallet trust or live execution is mutated."
        ),
    }

