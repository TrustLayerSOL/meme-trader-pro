import time


PROMOTION_DECISIONS = {"approve_promotion", "promote", "promote_to_tracked"}
DEMOTION_DECISIONS = {"approve_demotion", "demote", "demote_off_watch"}
PROMOTION_LIFECYCLE_ACTIONS = {"PROMOTE_TO_TRUSTED_REVIEW", "PROMOTION_REVIEW", "PAPER_WATCH"}


def wallet_address(row):
    if isinstance(row, dict):
        return row.get("trackedWalletAddress") or row.get("wallet") or row.get("address")
    return row


def normalize_review_decisions(review_decisions):
    data = review_decisions if isinstance(review_decisions, dict) else {}
    rows = data.get("decisions") if isinstance(data.get("decisions"), list) else []
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        wallet = wallet_address(row)
        decision = str(row.get("decision") or row.get("action") or "").strip().lower()
        approved = bool(row.get("approved"))
        if not wallet or not approved:
            continue
        if decision not in PROMOTION_DECISIONS | DEMOTION_DECISIONS:
            continue
        result[str(wallet)] = {
            "wallet": str(wallet),
            "decision": "approve_promotion" if decision in PROMOTION_DECISIONS else "approve_demotion",
            "note": row.get("note") or row.get("reason") or "",
            "approved_by": row.get("approved_by") or "operator",
            "approved_at": row.get("approved_at"),
        }
    return result


def build_tracked_wallet_row(wallet, source="wallet_lifecycle", name=None, base=None):
    row = dict(base or {})
    row["trackedWalletAddress"] = wallet
    row.setdefault("name", name or f"MTP {short_wallet(wallet)}")
    row.setdefault("alertsOnToast", True)
    row.setdefault("alertsOnBubble", True)
    row.setdefault("alertsOnFeed", True)
    groups = row.get("groups") if isinstance(row.get("groups"), list) else []
    for group in ["MemeTraderPro", "Promoted"]:
        if group not in groups:
            groups.append(group)
    row["groups"] = groups
    row.setdefault("sound", "default")
    row["source"] = source
    row["promoted_by"] = "wallet_lifecycle"
    return row


def short_wallet(wallet):
    wallet = str(wallet or "")
    if len(wallet) <= 8:
        return wallet
    return f"{wallet[:4]}...{wallet[-4:]}"


def lifecycle_by_wallet(lifecycle_report):
    rows = lifecycle_report.get("wallets") if isinstance(lifecycle_report, dict) else []
    result = {}
    for row in rows or []:
        wallet = wallet_address(row)
        if wallet:
            result[str(wallet)] = row
    return result


def paper_watch_by_wallet(paper_watch_wallets):
    rows = paper_watch_wallets.get("wallets") if isinstance(paper_watch_wallets, dict) else []
    result = {}
    for row in rows or []:
        wallet = wallet_address(row)
        if wallet:
            result[str(wallet)] = row
    return result


def apply_wallet_review_decisions(
    tracked_wallets,
    paper_watch_wallets,
    bad_wallets,
    review_decisions,
    lifecycle_report,
    applied_at=None,
    dry_run=True,
):
    applied_at = applied_at or time.time()
    tracked_wallets = list(tracked_wallets or [])
    paper_watch_wallets = paper_watch_wallets if isinstance(paper_watch_wallets, dict) else {"wallets": []}
    bad_wallets = list(bad_wallets or [])
    decisions = normalize_review_decisions(review_decisions)
    lifecycle = lifecycle_by_wallet(lifecycle_report or {})
    paper_watch = paper_watch_by_wallet(paper_watch_wallets)
    tracked_by_wallet = {wallet_address(row): row for row in tracked_wallets if wallet_address(row)}
    bad_by_wallet = {wallet_address(row): row for row in bad_wallets if wallet_address(row)}

    changes = []
    promoted = []
    demoted = []
    skipped = []

    for wallet, decision in decisions.items():
        lifecycle_row = lifecycle.get(wallet, {})
        lifecycle_action = (lifecycle_row.get("lifecycle") or {}).get("action")
        if decision["decision"] == "approve_promotion":
            if wallet in tracked_by_wallet:
                skipped.append({"wallet": wallet, "reason": "already tracked"})
                continue
            base = paper_watch.get(wallet, {})
            if not base or lifecycle_action not in PROMOTION_LIFECYCLE_ACTIONS:
                skipped.append({"wallet": wallet, "reason": "missing promotion evidence"})
                continue
            promoted.append(build_tracked_wallet_row(wallet, source=base.get("source") or "paper_watch", name=base.get("name")))
            changes.append({
                "wallet": wallet,
                "action": "promoted_to_tracked",
                "decision": decision,
                "lifecycle_action": lifecycle_action,
                "metrics": (lifecycle_row.get("lifecycle") or {}).get("metrics", {}),
            })
        elif decision["decision"] == "approve_demotion":
            if wallet not in tracked_by_wallet:
                skipped.append({"wallet": wallet, "reason": "not currently tracked"})
                continue
            demoted.append(wallet)
            changes.append({
                "wallet": wallet,
                "action": "demoted_from_tracked",
                "decision": decision,
                "lifecycle_action": lifecycle_action,
                "metrics": (lifecycle_row.get("lifecycle") or {}).get("metrics", {}),
            })

    if dry_run:
        return build_apply_result(
            tracked_wallets=tracked_wallets,
            paper_watch_wallets=paper_watch_wallets,
            bad_wallets=bad_wallets,
            changes=changes,
            promoted=promoted,
            demoted=demoted,
            skipped=skipped,
            applied_at=applied_at,
            dry_run=True,
        )

    demoted_set = set(demoted)
    next_tracked = [row for row in tracked_wallets if wallet_address(row) not in demoted_set]
    next_tracked.extend(promoted)

    promoted_set = {wallet_address(row) for row in promoted}
    next_paper_rows = []
    for row in paper_watch_wallets.get("wallets", []) or []:
        wallet = wallet_address(row)
        next_row = dict(row)
        if wallet in promoted_set:
            next_row["status"] = "promoted_to_tracked"
            next_row["promoted_at"] = applied_at
        next_paper_rows.append(next_row)
    next_paper_watch = dict(paper_watch_wallets)
    next_paper_watch["wallets"] = next_paper_rows

    next_bad = list(bad_wallets)
    for wallet in demoted:
        if wallet in bad_by_wallet:
            continue
        next_bad.append(wallet)

    return build_apply_result(
        tracked_wallets=next_tracked,
        paper_watch_wallets=next_paper_watch,
        bad_wallets=next_bad,
        changes=changes,
        promoted=promoted,
        demoted=demoted,
        skipped=skipped,
        applied_at=applied_at,
        dry_run=False,
    )


def build_apply_result(tracked_wallets, paper_watch_wallets, bad_wallets, changes, promoted, demoted, skipped, applied_at, dry_run):
    return {
        "applied_at": applied_at,
        "dry_run": dry_run,
        "summary": {
            "approved_decisions": len(changes) + len(skipped),
            "promoted": len(promoted),
            "demoted": len(demoted),
            "skipped": len(skipped),
            "tracked_wallets_after": len(tracked_wallets),
            "bad_wallets_after": len(bad_wallets),
        },
        "tracked_wallets": tracked_wallets,
        "paper_watch_wallets": paper_watch_wallets,
        "bad_wallets": bad_wallets,
        "audit": {
            "applied_at": applied_at,
            "dry_run": dry_run,
            "changes": changes,
            "skipped": skipped,
        },
    }
