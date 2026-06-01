from research.mtp_research.features.launch_state_feature_stubs import (
    DeployerHistoryEvent,
    build_feature_family_stubs,
    compute_deployer_history_features,
)
from research.mtp_research.launch_regime.launch_state_labels import FirstTwoHourLifecycleLabel


def test_first_two_hour_lifecycle_label_has_required_stub_fields() -> None:
    label = FirstTwoHourLifecycleLabel(token_mint="mint-1", launch_signature="sig-1", launch_ts=1_780_000_000)

    assert label.created_no_trade is None
    assert label.traded_on_curve_no_graduation is None
    assert label.graduated is None
    assert label.survived_30m is None
    assert label.survived_2h is None
    assert label.liquidity_disappeared is None
    assert label.holder_count_collapsed is None
    assert label.max_2h_runup is None
    assert label.max_2h_drawdown is None
    assert label.return_2h is None
    assert label.price_quality_flags == []


def test_feature_family_stubs_name_current_research_families() -> None:
    families = build_feature_family_stubs()

    assert families.ownership_concentration == "stub_pending_census_precision"
    assert families.launch_tempo_hazard == "stub_pending_census_precision"
    assert families.creator_deployer_archetype == "stub_pending_census_precision"
    assert families.manipulation_filters == "stub_pending_census_precision"
    assert families.regime_interactions == "stub_pending_census_precision"


def test_deployer_history_features_do_not_use_future_events() -> None:
    features = compute_deployer_history_features(
        [
            DeployerHistoryEvent(deployer="creator-1", block_time=99, outcome="graduated"),
            DeployerHistoryEvent(deployer="creator-1", block_time=100, outcome="created_no_trade"),
            DeployerHistoryEvent(deployer="creator-1", block_time=101, outcome="graduated"),
            DeployerHistoryEvent(deployer="creator-2", block_time=50, outcome="graduated"),
        ],
        deployer="creator-1",
        as_of_ts=100,
    )

    assert features.prior_launch_count == 1
    assert features.prior_graduated_count == 1
    assert features.future_events_excluded is True
