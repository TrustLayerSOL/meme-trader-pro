"""Feature-family stubs for launch-state classification.

The functions here define auditable schema placeholders only. They avoid
future leakage and do not score, optimize, or trade.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


STUB_STATUS = "stub_pending_census_precision"


@dataclass(frozen=True)
class LaunchStateFeatureFamilies:
    ownership_concentration: str = STUB_STATUS
    launch_tempo_hazard: str = STUB_STATUS
    creator_deployer_archetype: str = STUB_STATUS
    manipulation_filters: str = STUB_STATUS
    regime_interactions: str = STUB_STATUS

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class DeployerHistoryEvent:
    deployer: str
    block_time: int
    outcome: str


@dataclass(frozen=True)
class DeployerHistoryFeatures:
    deployer: str
    as_of_ts: int
    prior_launch_count: int
    prior_graduated_count: int
    prior_created_no_trade_count: int
    future_events_excluded: bool = True

    def to_dict(self) -> dict[str, int | str | bool]:
        return asdict(self)


def build_feature_family_stubs() -> LaunchStateFeatureFamilies:
    return LaunchStateFeatureFamilies()


def compute_deployer_history_features(
    events: list[DeployerHistoryEvent],
    *,
    deployer: str,
    as_of_ts: int,
) -> DeployerHistoryFeatures:
    prior_events = [
        event for event in events
        if event.deployer == deployer and event.block_time < as_of_ts
    ]
    return DeployerHistoryFeatures(
        deployer=deployer,
        as_of_ts=as_of_ts,
        prior_launch_count=len(prior_events),
        prior_graduated_count=len([event for event in prior_events if event.outcome == "graduated"]),
        prior_created_no_trade_count=len([event for event in prior_events if event.outcome == "created_no_trade"]),
    )
