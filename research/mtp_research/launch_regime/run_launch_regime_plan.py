"""Plan launch-regime early lifecycle collection."""

from __future__ import annotations

import argparse
from collections import Counter

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore
from research.mtp_research.launch_regime.builder import LaunchRegimeBuilder, SNAPSHOT_AGES


def main() -> int:
    args = parse_args()
    candidates = CandidateRegistry(args.registry_path).load_all() if args.registry_path else CandidateRegistry().load_all()
    builder = LaunchRegimeBuilder()
    launches = builder.build_launches(
        [
            candidate for candidate in candidates
            if not candidate.metadata_json.get("is_mock") and candidate.token_mint
        ]
    )
    if args.include_event_inferred:
        events = NormalizedEventStore(args.events_path).load_all()
        by_token = {launch.token_mint: launch for launch in builder.build_event_inferred_launches(events)}
        by_token.update({launch.token_mint: launch for launch in launches})
        launches = sorted(by_token.values(), key=lambda item: (item.launch_ts, item.token_mint))
    selected = launches[: args.target_launches]
    regime_counts = Counter(launch.launch_regime for launch in selected)
    targets_with_pool = sum(1 for launch in selected if launch.pool_address)
    estimated_signature_requests = targets_with_pool * args.max_signatures_per_target
    estimated_transaction_requests = targets_with_pool * args.max_transactions_per_target
    expected_research_rows = len(selected) * len(SNAPSHOT_AGES)
    print(f"candidate_registry_count={len(candidates)}")
    print(f"estimated_launches={len(selected)}")
    print(f"target_launches={args.target_launches}")
    print(f"targets_with_pool={targets_with_pool}")
    print(f"estimated_signature_requests={estimated_signature_requests}")
    print(f"estimated_transaction_requests={estimated_transaction_requests}")
    print(f"expected_raw_transactions_up_to={estimated_transaction_requests}")
    print(f"expected_research_rows={expected_research_rows}")
    print(f"launch_regime_counts={dict(sorted(regime_counts.items()))}")
    print("network_calls=0")
    if len(selected) < args.min_reasonable_launches:
        print("plan_reasonable=False")
        print("warning_flags=['insufficient_launch_candidates_for_target']")
    else:
        print("plan_reasonable=True")
        print("warning_flags=[]")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan launch-regime lifecycle collection.")
    parser.add_argument("--registry-path")
    parser.add_argument("--events-path", default="data/normalized/events.jsonl")
    parser.add_argument("--target-launches", type=int, default=2500)
    parser.add_argument("--include-event-inferred", action="store_true")
    parser.add_argument("--min-reasonable-launches", type=int, default=50)
    parser.add_argument("--max-signatures-per-target", type=int, default=250)
    parser.add_argument("--max-transactions-per-target", type=int, default=250)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
