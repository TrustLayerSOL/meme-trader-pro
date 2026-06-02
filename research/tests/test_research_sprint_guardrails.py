from pathlib import Path


GUARDED_PATHS = [
    Path("research/mtp_research/ingestion/pumpfun_creation_census.py"),
    Path("research/mtp_research/ingestion/run_pumpfun_creation_census.py"),
    Path("research/mtp_research/validation/pumpfun_precision_audit.py"),
    Path("research/mtp_research/validation/run_pumpfun_precision_sample.py"),
    Path("research/mtp_research/validation/run_pumpfun_precision_import.py"),
    Path("research/mtp_research/launch_regime/launch_state_labels.py"),
    Path("research/mtp_research/features/launch_state_feature_stubs.py"),
    Path("research/mtp_research/validation/early_ownership_concentration_thesis.py"),
    Path("research/mtp_research/validation/run_early_ownership_concentration_thesis.py"),
    Path("research/mtp_research/validation/holder_growth_tempo_thesis.py"),
    Path("research/mtp_research/validation/run_holder_growth_tempo_thesis.py"),
    Path("research/mtp_research/validation/creator_archetype_history_thesis.py"),
    Path("research/mtp_research/validation/run_creator_archetype_history_thesis.py"),
    Path("research/mtp_research/validation/liquidity_persistence_thesis.py"),
    Path("research/mtp_research/validation/run_liquidity_persistence_thesis.py"),
    Path("research/mtp_research/validation/buy_sell_flow_baseline_thesis.py"),
    Path("research/mtp_research/validation/run_buy_sell_flow_baseline_thesis.py"),
]


FORBIDDEN_RUNTIME_PATTERNS = [
    "place_order",
    "submit_order",
    "send_transaction",
    "private_key",
    "secret_key",
    "auto_buy",
    "auto_sell",
    "grid_search",
    "threshold_optimization",
    "sklearn",
    "xgboost",
]


def test_creation_census_sprint_does_not_add_trading_or_private_key_logic() -> None:
    for path in GUARDED_PATHS:
        if not path.exists():
            continue
        text = _strip_allowed_negative_guardrail_labels(path.read_text(encoding="utf-8").lower())
        for pattern in FORBIDDEN_RUNTIME_PATTERNS:
            assert pattern not in text, f"{pattern} found in {path}"


def _strip_allowed_negative_guardrail_labels(text: str) -> str:
    return (
        text
        .replace("no_threshold_optimization", "")
        .replace("no_grid_search", "")
        .replace("no_ml_black_boxes", "")
    )
