from __future__ import annotations

from typing import Any

from obsidian_export.candidate_note import wallet_candidate_stem
from obsidian_export.markdown import GENERATED_MARKER, as_dict, iso_from_ts, table, wikilink, yaml_frontmatter
from obsidian_export.wallet_note import wallet_stem


def render_wallet_review_decisions_note(
    decisions_data: dict[str, Any],
    *,
    candidate_audit: dict[str, Any] | None = None,
) -> str:
    decisions = decisions_data.get("decisions") if isinstance(decisions_data.get("decisions"), list) else []
    candidate_index = _candidate_index(candidate_audit or {})
    approved = [row for row in decisions if isinstance(row, dict) and row.get("approved")]
    frontmatter = {
        "type": "wallet_review_decisions",
        "source": "memetraderpro",
        "decision_count": len(decisions),
        "approved_decisions": len(approved),
        "approve_promotion": len([row for row in approved if row.get("decision") == "approve_promotion"]),
        "approve_demotion": len([row for row in approved if row.get("decision") == "approve_demotion"]),
        "generated_by": "memetraderpro",
    }
    body = f"""# Wallet Review Decisions

{GENERATED_MARKER}

## Summary

- Saved decisions: {frontmatter["decision_count"]}
- Approved decisions: {frontmatter["approved_decisions"]}
- Approved promotions: {frontmatter["approve_promotion"]}
- Approved demotions: {frontmatter["approve_demotion"]}

## Saved Decisions

{_decisions_table(decisions, candidate_index)}

## Source Of Truth

- Review candidates: `data/wallet_candidate_audit.json`
- Saved human decisions: `data/wallet_review_decisions.json`
- Wallet-list apply remains separate and gated.
"""
    return f"{yaml_frontmatter(frontmatter)}\n\n{body.rstrip()}\n"


def _candidate_index(candidate_audit: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = candidate_audit.get("candidates") if isinstance(candidate_audit.get("candidates"), list) else []
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict) and row.get("wallet"):
            index[str(row["wallet"])] = row
    return index


def _decisions_table(decisions: list[Any], candidate_index: dict[str, dict[str, Any]]) -> str:
    rows = [row for row in decisions if isinstance(row, dict)]
    if not rows:
        return "No saved wallet review decisions yet."
    return table(
        ["Wallet", "Decision", "Approved", "Candidate", "Candidate Status", "Updated", "Note"],
        [_decision_row(row, candidate_index) for row in rows[:200]],
    )


def _decision_row(row: dict[str, Any], candidate_index: dict[str, dict[str, Any]]) -> list[Any]:
    wallet = str(row.get("wallet") or "unknown")
    candidate = as_dict(candidate_index.get(wallet))
    candidate_status = candidate.get("audit_status") or "not_in_current_candidate_audit"
    candidate_link = "not_in_current_candidate_audit"
    if candidate:
        candidate_link = wikilink(wallet_candidate_stem(candidate), "candidate review")
    return [
        wikilink(wallet_stem(wallet), wallet),
        row.get("decision"),
        bool(row.get("approved")),
        candidate_link,
        candidate_status,
        iso_from_ts(row.get("updated_at") or row.get("approved_at")),
        _clean_note(row.get("note")),
    ]


def _clean_note(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "/").replace("\n", " ").strip()
