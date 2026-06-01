from pathlib import Path


GUARDED_PATHS = [
    Path("research/mtp_research/ingestion/pumpfun_creation_census.py"),
    Path("research/mtp_research/ingestion/run_pumpfun_creation_census.py"),
    Path("research/mtp_research/validation/pumpfun_precision_audit.py"),
    Path("research/mtp_research/validation/run_pumpfun_precision_sample.py"),
    Path("research/mtp_research/validation/run_pumpfun_precision_import.py"),
    Path("research/mtp_research/launch_regime/launch_state_labels.py"),
    Path("research/mtp_research/features/launch_state_feature_stubs.py"),
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
        text = path.read_text(encoding="utf-8").lower()
        for pattern in FORBIDDEN_RUNTIME_PATTERNS:
            assert pattern not in text, f"{pattern} found in {path}"
