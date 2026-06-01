"""Build launch-relative lifecycle snapshots and outcomes."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore
from research.mtp_research.launch_regime.builder import LaunchRegimeBuilder
from research.mtp_research.launch_regime.models import LaunchRegimeCandidate
from research.mtp_research.launch_regime.store import JsonlArtifactStore


def main() -> int:
    args = parse_args()
    candidates = CandidateRegistry(args.registry_path).load_all() if args.registry_path else CandidateRegistry().load_all()
    events = NormalizedEventStore(args.events_path).load_all()
    builder = LaunchRegimeBuilder()
    launches = builder.build_launches(
        [
            candidate for candidate in candidates
            if not candidate.metadata_json.get("is_mock") and candidate.token_mint
        ]
    )
    if args.include_event_inferred:
        by_token = {launch.token_mint: launch for launch in builder.build_event_inferred_launches(events)}
        by_token.update({launch.token_mint: launch for launch in launches})
        launches = sorted(by_token.values(), key=lambda item: (item.launch_ts, item.token_mint))
    launches = launches[: args.target_launches]
    snapshots = builder.build_snapshots(launches, events)
    outcomes = builder.build_outcomes(launches, events)

    launch_path = Path(args.output_dir) / "launch_regime_candidates.jsonl"
    snapshot_path = Path(args.output_dir) / "launch_lifecycle_snapshots.jsonl"
    outcome_path = Path(args.output_dir) / "launch_lifecycle_outcomes.jsonl"
    JsonlArtifactStore(launch_path).write_all(launches, sort_key=lambda row: (row.launch_ts, row.token_mint))
    JsonlArtifactStore(snapshot_path).write_all(snapshots, sort_key=lambda row: (row.launch_ts, row.token_mint, row.launch_age_seconds))
    JsonlArtifactStore(outcome_path).write_all(outcomes, sort_key=lambda row: (row.launch_ts, row.token_mint))

    regime_counts = Counter(launch.launch_regime for launch in launches)
    warnings = []
    if len(launches) < args.target_launches:
        warnings.append("launch_target_not_reached_from_current_candidate_sources")
    if not launches:
        warnings.append("no_launches_matched_regime")

    print(f"launches_collected={len(launches)}")
    print(f"snapshot_rows_created={len(snapshots)}")
    print(f"outcome_rows_created={len(outcomes)}")
    print(f"launch_regime_coverage={dict(sorted(regime_counts.items()))}")
    print(f"launch_time_span_seconds={_time_span(launches)}")
    print(f"launch_candidates_path={launch_path}")
    print(f"snapshot_path={snapshot_path}")
    print(f"outcome_path={outcome_path}")
    print(f"warning_flags={warnings}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build launch-relative lifecycle artifacts.")
    parser.add_argument("--registry-path")
    parser.add_argument("--events-path", default="data/normalized/events.jsonl")
    parser.add_argument("--output-dir", default="data/normalized/launch_regime")
    parser.add_argument("--target-launches", type=int, default=2500)
    parser.add_argument("--include-event-inferred", action="store_true")
    return parser.parse_args()


def _time_span(launches: list[LaunchRegimeCandidate]) -> int | None:
    if not launches:
        return None
    values = [launch.launch_ts for launch in launches]
    return max(values) - min(values)


if __name__ == "__main__":
    raise SystemExit(main())
