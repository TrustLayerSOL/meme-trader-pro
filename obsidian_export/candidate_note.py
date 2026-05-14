from __future__ import annotations

from typing import Any

from obsidian_export.markdown import (
    GENERATED_MARKER,
    as_dict,
    bullet_list,
    compact_number,
    short_id,
    slugify,
    table,
    wikilink,
    yaml_frontmatter,
)
from obsidian_export.wallet_note import wallet_stem


def wallet_candidate_stem(row: dict[str, Any]) -> str:
    wallet = str(row.get("wallet") or row.get("wallet_address") or "unknown")
    action = str(row.get("recommendation_action") or "REVIEW")
    return f"WREV-{slugify(action, max_length=60)}-{slugify(wallet, max_length=160)}"


def wallet_candidate_filename(row: dict[str, Any]) -> str:
    return f"{wallet_candidate_stem(row)}.md"


def render_wallet_candidate_note(row: dict[str, Any]) -> str:
    wallet = str(row.get("wallet") or row.get("wallet_address") or "unknown")
    evidence = as_dict(row.get("evidence"))
    gates = as_dict(row.get("evidence_gates"))
    action = str(row.get("recommendation_action") or "UNKNOWN")
    frontmatter = {
        "type": "wallet_candidate_review",
        "source": "memetraderpro",
        "wallet_address": wallet,
        "recommendation_action": action,
        "audit_status": row.get("audit_status"),
        "comparison_status": row.get("comparison_status"),
        "review_only": bool(row.get("review_only", True)),
        "wallet_list_apply_allowed": bool(row.get("wallet_list_apply_allowed", False)),
        "known_outcomes": int(evidence.get("known_outcomes") or 0),
        "total_signals": int(evidence.get("total_signals") or 0),
        "runner_participation": int(evidence.get("runner_participation") or 0),
        "rug_participation": int(evidence.get("rug_participation") or 0),
        "source_coverage": compact_number(gates.get("source_coverage"), 4),
        "promotion_score": compact_number(evidence.get("promotion_score"), 4),
        "demotion_score": compact_number(evidence.get("demotion_score"), 4),
        "generated_by": "memetraderpro",
    }
    body = f"""# Wallet Candidate Review {short_id(wallet)}

{GENERATED_MARKER}

## Review Summary

- Wallet: {wikilink(wallet_stem(wallet), wallet)}
- Recommendation: {action}
- Audit status: {row.get("audit_status") or "unknown"}
- Comparison status: {row.get("comparison_status") or "unknown"}
- Review only: {frontmatter["review_only"]}
- Wallet-list apply allowed: {frontmatter["wallet_list_apply_allowed"]}

## Evidence Gates

{_gate_table(gates)}

## Outcome Evidence

{_evidence_table(evidence)}

## Recommendation Reasons

{bullet_list(list(evidence.get("recommendation_reasons") or []), empty="No recommendation reasons recorded.")}

## Audit Notes

{bullet_list(list(row.get("audit_notes") or []), empty="No audit notes recorded.")}

## Operator Review

Manual decision should be recorded through the wallet review flow. Do not edit generated evidence below the marker.
"""
    return f"{yaml_frontmatter(frontmatter)}\n\n{body.rstrip()}\n"


def _gate_table(gates: dict[str, Any]) -> str:
    return table(
        ["Gate", "Value"],
        [
            ["Known outcome sample passed", gates.get("known_outcome_sample_passed")],
            ["Minimum known outcomes", gates.get("minimum_known_outcomes")],
            ["Source coverage", compact_number(gates.get("source_coverage"), 4)],
            ["Recommendation is review-only", gates.get("recommendation_is_review_only")],
        ],
    )


def _evidence_table(evidence: dict[str, Any]) -> str:
    return table(
        ["Metric", "Value"],
        [
            ["Total signals", evidence.get("total_signals")],
            ["Accepted signals", evidence.get("accepted_signals")],
            ["Rejected / observed signals", evidence.get("rejected_or_observed_signals")],
            ["Known outcomes", evidence.get("known_outcomes")],
            ["Runner participation", evidence.get("runner_participation")],
            ["Rug participation", evidence.get("rug_participation")],
            ["Dead participation", evidence.get("dead_participation")],
            ["Runner participation rate", compact_number(evidence.get("runner_participation_rate"), 4)],
            ["Rug participation rate", compact_number(evidence.get("rug_participation_rate"), 4)],
            ["Average PnL after signal", compact_number(evidence.get("average_pnl_after_signal"), 6)],
            ["Promotion score", compact_number(evidence.get("promotion_score"), 4)],
            ["Demotion score", compact_number(evidence.get("demotion_score"), 4)],
        ],
    )
