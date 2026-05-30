from __future__ import annotations

from typing import Any

from obsidian_export.markdown import (
    GENERATED_MARKER,
    as_dict,
    compact_number,
    short_datetime,
    short_id,
    table,
    wikilink,
    yaml_frontmatter,
)
from obsidian_export.signal_note import paper_trade_stem, rejected_signal_stem
from obsidian_export.wallet_note import wallet_stem


def render_summary_index_notes(snapshot: dict[str, Any]) -> dict[str, str]:
    wallets = [row for row in snapshot.get("wallet_rows") or [] if isinstance(row, dict)]
    rejections = [row for row in snapshot.get("rejections") or [] if isinstance(row, dict)]
    paper_trades = [row for row in snapshot.get("paper_trades") or [] if isinstance(row, dict)]

    return {
        "Dashboards/Top Wallets.md": _note(
            "wallet_index",
            "Top Wallets",
            "Highest-confidence wallets by current score, ROI, and runner/rug balance.",
            _wallet_table(_top_wallets(wallets)),
        ),
        "Dashboards/Wallets Pending Review.md": _note(
            "wallet_review_queue",
            "Wallets Pending Review",
            "Promotion and demotion review wallets that deserve operator attention.",
            _wallet_table(_pending_review_wallets(wallets)),
        ),
        "Dashboards/Rug Association Watchlist.md": _note(
            "rug_watchlist",
            "Rug Association Watchlist",
            "Wallets with elevated rug association or demotion pressure.",
            _wallet_table(_rug_watchlist(wallets)),
        ),
        "Dashboards/Rejected Signal Winners.md": _note(
            "rejected_signal_winner_index",
            "Rejected Signal Winners",
            "Rejected signals whose later outcome suggests the filter may have blocked a winner.",
            _rejected_winner_table(_rejected_winners(rejections)),
        ),
        "Dashboards/Recent Paper Trade Outcomes.md": _note(
            "paper_trade_outcome_index",
            "Recent Paper Trade Outcomes",
            "Recent paper trades by lane, status, and realized outcome.",
            _paper_trade_table(paper_trades),
        ),
    }


def _note(note_type: str, title: str, description: str, body: str) -> str:
    frontmatter = {
        "type": note_type,
        "source": "memetraderpro",
        "generated_by": "memetraderpro",
    }
    content = f"""# {title}

{GENERATED_MARKER}

## What This Dashboard Does

{description}

{body}
"""
    return f"{yaml_frontmatter(frontmatter)}\n\n{content.rstrip()}\n"


def _top_wallets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: (_score(row), _wallet_roi(row), _runner_count(row)), reverse=True)[:50]


def _pending_review_wallets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = [
        row
        for row in rows
        if as_dict(row.get("recommendation")).get("action") in {"PROMOTION_REVIEW", "DEMOTION_REVIEW"}
    ]
    return sorted(selected, key=lambda row: (str(as_dict(row.get("recommendation")).get("action")), _score(row)), reverse=True)[:50]


def _rug_watchlist(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = [
        row
        for row in rows
        if _rug_count(row) > 0
        or as_dict(row.get("recommendation")).get("action") == "DEMOTION_REVIEW"
        or _wallet_roi(row) < 0
    ]
    return sorted(selected, key=lambda row: (_rug_count(row), -_wallet_roi(row), _score(row)), reverse=True)[:50]


def _rejected_winners(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    winners = []
    for row in rows:
        outcome = as_dict(row.get("what would have happened afterward if traded"))
        status = str(outcome.get("status") or "").lower()
        if status in {"runner", "winner", "would_have_won", "missed_winner"}:
            winners.append(row)
    return winners[:50]


def _wallet_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No wallet rows currently match this queue."
    return table(
        ["Wallet", "Action", "Score", "ROI", "Win Rate", "Runners", "Rugs", "Last Seen", "Reason"],
        [
            [
                wikilink(wallet_stem(str(row.get("wallet"))), short_id(row.get("wallet"))),
                as_dict(row.get("recommendation")).get("action") or row.get("status") or row.get("tier"),
                compact_number(_score(row), 1),
                compact_number(_wallet_roi(row), 2),
                compact_number(row.get("paper_watch_win_rate"), 1),
                _runner_count(row),
                _rug_count(row),
                short_datetime(row.get("last_seen")),
                "; ".join(as_dict(row.get("recommendation")).get("reasons") or []),
            ]
            for row in rows[:10]
        ],
    )


def _rejected_winner_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No rejected-signal winners in the current export window."
    return table(
        ["Rejected Signal", "Mint", "Lane", "Reason", "Outcome", "Max Gain", "Recorded"],
        [
            [
                wikilink(rejected_signal_stem(row), short_id(row.get("mint") or as_dict(row.get("signal context")).get("mint"))),
                short_id(row.get("mint") or as_dict(row.get("signal context")).get("mint")),
                row.get("lane"),
                row.get("rejection reason"),
                as_dict(row.get("what would have happened afterward if traded")).get("status"),
                compact_number(as_dict(row.get("what would have happened afterward if traded")).get("max_gain_pct"), 1),
                short_datetime(row.get("recorded_at")),
            ]
            for row in rows[:10]
        ],
    )


def _paper_trade_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No paper trades in the current export window."
    return table(
        ["Trade", "Mint", "Lane", "Status", "PnL", "PnL %", "Opened"],
        [
            [
                wikilink(paper_trade_stem(row), short_id(row.get("token_mint") or row.get("mint"))),
                short_id(row.get("token_mint") or row.get("mint")),
                row.get("paper_lane"),
                row.get("status"),
                compact_number(row.get("total_pnl") or row.get("pnl"), 2),
                compact_number(row.get("total_pnl_pct") or row.get("pnl_pct"), 1),
                short_datetime(row.get("entry_time_iso") or row.get("entry_time") or row.get("time")),
            ]
            for row in rows[:10]
        ],
    )


def _score(row: dict[str, Any]) -> float:
    for value in (
        as_dict(row.get("behavior_score")).get("score"),
        as_dict(row.get("confidence")).get("score"),
        row.get("score"),
    ):
        try:
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _wallet_roi(row: dict[str, Any]) -> float:
    for value in (
        as_dict(row.get("behavior_profile")).get("wallet_roi"),
        row.get("paper_watch_expectancy"),
        row.get("average_pnl_after_signal"),
    ):
        try:
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _runner_count(row: dict[str, Any]) -> int:
    try:
        return int(row.get("runner_participation") or row.get("runner_count") or 0)
    except (TypeError, ValueError):
        return 0


def _rug_count(row: dict[str, Any]) -> int:
    try:
        return int(row.get("rug_participation") or row.get("rug_count") or 0)
    except (TypeError, ValueError):
        return 0
