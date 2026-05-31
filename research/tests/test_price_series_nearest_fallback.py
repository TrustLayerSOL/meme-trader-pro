from research.mtp_research.validation.outcome_models import TokenPricePoint
from research.mtp_research.validation.price_series_builder import TokenPriceSeriesBuilder


def test_nearest_price_fallback_is_opt_in_and_defaults_off() -> None:
    builder = TokenPriceSeriesBuilder()
    points = [TokenPricePoint("token-a", 110, 1.0)]

    assert builder.get_entry_price(points, snapshot_ts=100, max_staleness_sec=5) is None
    assert builder.get_nearest_price(points, snapshot_ts=100, max_staleness_sec=20) == points[0]


def test_nearest_price_fallback_prefers_prior_on_equal_distance() -> None:
    builder = TokenPriceSeriesBuilder()
    prior = TokenPricePoint("token-a", 90, 1.0)
    after = TokenPricePoint("token-a", 110, 2.0)

    assert builder.get_nearest_price([after, prior], snapshot_ts=100, max_staleness_sec=20) == prior
    assert builder.get_nearest_price([after], snapshot_ts=100, max_staleness_sec=5) is None
