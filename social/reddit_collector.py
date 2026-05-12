import os
import time
import json
from urllib.request import Request, urlopen
from urllib.parse import urljoin

from core.json_store import locked_update_json
from core.runtime_status import update_component
from social.social_signal import SOCIAL_STATE_FILE, SocialSignalEngine


REDDIT_COLLECTOR = "reddit"
DEFAULT_SUBREDDITS = [
    "SolanaMemeCoins",
    "CryptoMoonShots",
    "memecoins",
    "solana",
]
DEFAULT_USER_AGENT = "MemeTraderPro local social research/0.1"
REDDIT_BASE_URL = "https://www.reddit.com"
NOISY_AUTHORS = {"automoderator", "mod", "moderator"}
NOISY_TITLE_TERMS = {"daily discussion", "general discussion", "what are you buying", "weekly thread"}


def reddit_listing_url(subreddit, limit=25, sort="new"):
    subreddit = str(subreddit or "").strip().strip("/")
    sort = str(sort or "new").strip().lower() or "new"
    limit = max(1, min(int(limit or 25), 100))
    return f"{REDDIT_BASE_URL}/r/{subreddit}/{sort}.json?limit={limit}"


def reddit_post_url(permalink):
    permalink = str(permalink or "").strip()
    if permalink.startswith("http://") or permalink.startswith("https://"):
        return permalink
    return urljoin(REDDIT_BASE_URL, permalink)


def reddit_post_text(post):
    title = str(post.get("title") or "").strip()
    body = str(post.get("selftext") or "").strip()
    if title and body:
        return f"{title}\n{body}"
    return title or body


def normalize_reddit_text(text):
    return " ".join(str(text or "").lower().split())


def classify_reddit_post(post, subreddit=None, engine=None):
    engine = engine or SocialSignalEngine()
    post = post if isinstance(post, dict) else {}
    text = reddit_post_text(post)
    post_id = str(post.get("id") or "").strip()
    permalink = reddit_post_url(post.get("permalink"))
    content_hash = engine.social_event_id("reddit_content", text, 0).split(":")[-1]
    author = str(post.get("author") or "").strip().lower()
    title = normalize_reddit_text(post.get("title"))
    noise_flags = []
    drop_reason = None

    if author in NOISY_AUTHORS:
        noise_flags.append("noisy_author")
        drop_reason = "noisy_author"
    if any(term in title for term in NOISY_TITLE_TERMS):
        noise_flags.append("generic_thread")
        drop_reason = drop_reason or "generic_thread"

    signal = reddit_post_to_signal(post, subreddit=subreddit or post.get("subreddit"), engine=engine)
    has_strong_reference = bool(signal.get("mints") or signal.get("tickers"))
    if not has_strong_reference:
        noise_flags.append("generic_keyword_only")
        drop_reason = drop_reason or "generic_keyword_only"

    if post_id:
        dedupe_key = f"reddit:{post_id}"
    elif post.get("crosspost_parent"):
        dedupe_key = f"reddit:{post.get('crosspost_parent')}"
    elif permalink:
        dedupe_key = f"reddit_url:{permalink.rstrip('/')}"
    else:
        dedupe_key = f"reddit_content:{content_hash}"

    return {
        "source_id": post_id,
        "source_url": permalink,
        "dedupe_key": dedupe_key,
        "content_hash": content_hash,
        "noise_flags": noise_flags,
        "drop_reason": drop_reason,
        "match_quality": "strong_reference" if has_strong_reference else "generic",
        "allowed_for_bonus": has_strong_reference and drop_reason is None,
        "signal": signal,
    }


def reddit_post_to_signal(post, subreddit, engine=None):
    engine = engine or SocialSignalEngine()
    post = post if isinstance(post, dict) else {}
    author = str(post.get("author") or "unknown").lower()
    subreddit = str(subreddit or post.get("subreddit") or "reddit").strip()
    account = f"reddit_{subreddit.lower()}_{author}".replace(" ", "_")
    text = reddit_post_text(post)
    timestamp = post.get("created_utc") or time.time()
    return engine.build_signal(
        account=account,
        text=text,
        url=reddit_post_url(post.get("permalink")),
        source_platform="reddit",
        timestamp=timestamp,
        engagement={
            "score": post.get("score"),
            "num_comments": post.get("num_comments"),
            "upvote_ratio": post.get("upvote_ratio"),
        },
        raw={
            "reddit_id": post.get("id"),
            "subreddit": subreddit,
            "author": post.get("author"),
            "source_url": reddit_post_url(post.get("permalink")),
        },
        expires_hours=8,
    )


def parse_reddit_listing(payload, subreddit):
    payload = payload if isinstance(payload, dict) else {}
    children = ((payload.get("data") or {}).get("children") or [])
    posts = []
    for child in children:
        post = (child or {}).get("data") if isinstance(child, dict) else None
        if not isinstance(post, dict):
            continue
        if post.get("removed_by_category") or post.get("banned_by"):
            continue
        text = reddit_post_text(post)
        if not text:
            continue
        post = dict(post)
        post.setdefault("subreddit", subreddit)
        posts.append(post)
    return posts


def default_fetcher(url, timeout, headers):
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def store_social_signals(signals, state_file=SOCIAL_STATE_FILE):
    engine = SocialSignalEngine(state_file=state_file)
    signals = [signal for signal in signals if isinstance(signal, dict)]

    def updater(state):
        if not isinstance(state, dict):
            state = {"events": []}
        existing = state.get("events")
        if not isinstance(existing, list):
            existing = state.get("signals") if isinstance(state.get("signals"), list) else []
        state["events"] = engine.dedupe_signals(signals + existing)[:500]
        state.pop("signals", None)
        state["last_updated"] = time.time()
        state["mode"] = "SOCIAL_AUTOMATED_RESEARCH"
        return state

    return locked_update_json(state_file, {"events": []}, updater)


def update_reddit_collector_status(summary):
    status = {
        "collector": REDDIT_COLLECTOR,
        "label": "Reddit Collector",
        "type": "automation",
        "enabled": True,
        "event_count": summary.get("stored_count", 0),
        "events_seen": summary.get("fetched_count", 0),
        "last_success_at": summary.get("completed_at") if not summary.get("errors") else None,
        "last_event_at": summary.get("latest_event_at"),
        "last_error": "; ".join(summary.get("errors", [])[:3]) or None,
        "fresh_seconds": 1800,
        "duplicate_count": summary.get("duplicate_count", 0),
        "rejected_count": summary.get("rejected_count", 0),
        "noise_dropped_count": summary.get("noise_dropped_count", 0),
        "error_count": summary.get("error_count", 0),
    }
    update_component("social_collectors", reddit=status)
    return status


def collect_reddit_social(
    subreddits=None,
    limit=25,
    state_file=SOCIAL_STATE_FILE,
    fetcher=None,
    timeout=10,
):
    fetcher = fetcher or default_fetcher
    subreddits = list(subreddits or DEFAULT_SUBREDDITS)
    headers = {
        "User-Agent": os.getenv("REDDIT_USER_AGENT", DEFAULT_USER_AGENT),
    }
    started_at = time.time()
    engine = SocialSignalEngine(state_file=state_file)
    signals = []
    errors = []
    fetched_count = 0
    duplicate_count = 0
    rejected_count = 0
    rejection_reasons = {}
    seen_keys = set()

    for subreddit in subreddits:
        try:
            payload = fetcher(
                reddit_listing_url(subreddit, limit=limit),
                timeout=timeout,
                headers=headers,
            )
            posts = parse_reddit_listing(payload, subreddit)
            fetched_count += len(posts)
            for post in posts:
                classification = classify_reddit_post(post, subreddit=subreddit, engine=engine)
                key = classification.get("dedupe_key")
                if key in seen_keys:
                    duplicate_count += 1
                    continue
                seen_keys.add(key)
                if classification.get("drop_reason"):
                    rejected_count += 1
                    reason = classification.get("drop_reason")
                    rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
                    continue
                signal = classification.get("signal") or {}
                signal["collector"] = REDDIT_COLLECTOR
                signal["match_quality"] = classification.get("match_quality")
                signal["allowed_for_bonus"] = classification.get("allowed_for_bonus")
                signal["noise_flags"] = classification.get("noise_flags") or []
                signal.setdefault("raw", {})
                signal["raw"].update({
                    "dedupe_key": key,
                    "content_hash": classification.get("content_hash"),
                    "source_id": classification.get("source_id"),
                    "source_url": classification.get("source_url"),
                })
                if signal.get("tickers") or signal.get("mints"):
                    signals.append(signal)
        except Exception as exc:
            errors.append(f"{subreddit}: {str(exc)[:160]}")

    state = store_social_signals(signals, state_file=state_file) if signals else engine.state
    latest_event_at = None
    for signal in signals:
        timestamp = signal.get("timestamp")
        if timestamp is not None:
            latest_event_at = max(latest_event_at or 0, float(timestamp))

    summary = {
        "collector": REDDIT_COLLECTOR,
        "started_at": started_at,
        "completed_at": time.time(),
        "subreddits": subreddits,
        "fetched_count": fetched_count,
        "stored_count": len(signals),
        "new_count": len(signals),
        "duplicate_count": duplicate_count,
        "deduped_count": duplicate_count,
        "rejected_count": rejected_count,
        "noise_dropped_count": rejected_count,
        "rejection_reasons": rejection_reasons,
        "state_signal_count": len(SocialSignalEngine(state_file=state_file).signal_rows()) if isinstance(state, dict) else 0,
        "latest_event_at": latest_event_at,
        "errors": errors,
        "error_count": len(errors),
        "trade_triggered": False,
        "broader_source_expansion": {
            "allowed": False,
            "reason": "requires labeled decision analytics before adding broader sources",
        },
        "detail": "Reddit social evidence imported for local signal matching only.",
    }
    summary["status"] = update_reddit_collector_status(summary)
    return summary


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Collect Reddit posts into local social signal state.")
    parser.add_argument("--subreddit", action="append", dest="subreddits", help="Subreddit to collect. May be repeated.")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--state-file", default=SOCIAL_STATE_FILE)
    args = parser.parse_args()

    print(json.dumps(
        collect_reddit_social(
            subreddits=args.subreddits,
            limit=args.limit,
            state_file=args.state_file,
        ),
        indent=2,
        sort_keys=True,
    ))
