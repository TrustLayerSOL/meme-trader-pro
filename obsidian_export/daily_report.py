from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from obsidian_export.markdown import (
    GENERATED_MARKER,
    as_dict,
    compact_number,
    iso_from_ts,
    short_datetime,
    short_id,
    table,
    wikilink,
    yaml_frontmatter,
)
from obsidian_export.signal_note import paper_trade_stem, rejected_signal_stem, signal_stem
from obsidian_export.wallet_note import wallet_stem


def daily_report_filename(report_date: str | None = None) -> str:
    return f"Daily-{report_date or datetime.now(timezone.utc).date().isoformat()}.md"


def render_daily_report(snapshot: dict[str, Any], *, report_date: str | None = None) -> str:
    report_date = report_date or datetime.now(timezone.utc).date().isoformat()
    frontmatter = {
        "type": "daily_report",
        "source": "memetraderpro",
        "date": report_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "memetraderpro",
    }
    candidates = _top_candidates(snapshot)
    wallet_rows = snapshot.get("wallet_rows") if isinstance(snapshot.get("wallet_rows"), list) else []
    rejections = snapshot.get("rejections") if isinstance(snapshot.get("rejections"), list) else []
    paper_trades = snapshot.get("paper_trades") if isinstance(snapshot.get("paper_trades"), list) else []
    signals = snapshot.get("signals") if isinstance(snapshot.get("signals"), list) else []
    replay = as_dict(snapshot.get("replay_visibility"))

    body = f"""# MemeTraderPro Daily Report {report_date}

{GENERATED_MARKER}

## New Wallets Discovered

{_candidate_table(candidates)}

## Promoted Wallets

{_wallet_recommendation_table(wallet_rows, "PROMOTION_REVIEW")}

## Demoted Wallets

{_wallet_recommendation_table(wallet_rows, "DEMOTION_REVIEW")}

## Best Signals

{_signal_score_table(signals, reverse=True)}

## Worst Signals

{_signal_score_table(signals, reverse=False)}

## Rejected Signals Summary

{_rejection_table(rejections)}

## Paper Trades Opened / Closed

{_paper_trade_table(paper_trades)}

## Notable Replay Findings

- Replay report generated at: {iso_from_ts(replay.get("generated_at")) or "unknown"}
- Review mode: {replay.get("mode") or "unknown"}
- Records: {as_dict(replay.get("counts")).get("records") or "unknown"}
"""
    return f"{yaml_frontmatter(frontmatter)}\n\n{body.rstrip()}\n"


def _top_candidates(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    candidate_report = as_dict(snapshot.get("candidate_wallets"))
    rows = candidate_report.get("candidates") if isinstance(candidate_report.get("candidates"), list) else []
    return rows[:10]


def _candidate_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No candidate wallet report available."
    return table(
        ["Wallet", "Score", "Action", "Winner Mints", "Last Seen"],
        [
            [
                wikilink(wallet_stem(str(row.get("wallet"))), short_id(row.get("wallet"))),
                compact_number(row.get("score"), 1),
                as_dict(row.get("review")).get("action"),
                row.get("winner_mints"),
                short_datetime(row.get("last_seen")),
            ]
            for row in rows[:10]
        ],
    )


def _wallet_recommendation_table(rows: list[dict[str, Any]], action: str) -> str:
    selected = [row for row in rows if as_dict(row.get("recommendation")).get("action") == action]
    if not selected:
        return f"No {action} wallets in the latest export."
    return table(
        ["Wallet", "Confidence", "ROI", "Win Rate", "Reason"],
        [
            [
                wikilink(wallet_stem(str(row.get("wallet"))), short_id(row.get("wallet"))),
                compact_number(as_dict(row.get("behavior_score")).get("score"), 1),
                compact_number(as_dict(row.get("behavior_profile")).get("wallet_roi"), 2),
                compact_number(row.get("paper_watch_win_rate"), 1),
                "; ".join(as_dict(row.get("recommendation")).get("reasons") or []),
            ]
            for row in selected[:10]
        ],
    )


def _signal_score_table(rows: list[dict[str, Any]], *, reverse: bool) -> str:
    scored = []
    for row in rows:
        scoring = as_dict(row.get("scoring"))
        score = scoring.get("score") or row.get("total_score") or row.get("score")
        try:
            score_num = float(score)
        except (TypeError, ValueError):
            continue
        scored.append((score_num, row))
    scored.sort(key=lambda item: item[0], reverse=reverse)
    if not scored:
        return "No scored signal contexts available."
    return table(
        ["Signal", "Score", "Mint", "Decision"],
        [
            [
                wikilink(signal_stem(row), short_id(row.get("mint"))),
                compact_number(score, 1),
                short_id(row.get("mint")),
                row.get("skip_bucket") or row.get("final_action") or row.get("should_trade"),
            ]
            for score, row in scored[:10]
        ],
    )


def _rejection_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No rejected-signal rows available."
    return table(
        ["Rejected Signal", "Reason", "Lane", "Recorded"],
        [
            [
                wikilink(rejected_signal_stem(row), short_id(row.get("mint") or as_dict(row.get("signal context")).get("mint"))),
                row.get("rejection reason"),
                row.get("lane"),
                short_datetime(row.get("recorded_at")),
            ]
            for row in rows[:10]
        ],
    )


def _paper_trade_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No paper trades available."
    return table(
        ["Trade", "Status", "PnL", "Opened", "Closed"],
        [
            [
                wikilink(paper_trade_stem(row), short_id(row.get("mint") or row.get("token_mint"))),
                row.get("status"),
                compact_number(row.get("total_pnl") or row.get("pnl"), 2),
                short_datetime(row.get("entry_time_iso") or row.get("entry_time") or row.get("time")),
                short_datetime(row.get("close_time_iso") or row.get("close_time")),
            ]
            for row in rows[:10]
        ],
    )
