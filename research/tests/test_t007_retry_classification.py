from research.mtp_research.validation.t007_retry_classification import classify_curve_probe


def test_account_not_found_is_retry_before_budget_exhausted():
    result = classify_curve_probe({"account_found": False})
    assert result.event_type == "curve_account_not_found_retry"
    assert result.final is False


def test_account_not_found_final_after_budget_exhausted():
    result = classify_curve_probe({"account_found": False, "retry_budget_exhausted": True})
    assert result.event_type == "curve_account_not_found_final"
    assert result.final is True


def test_unsupported_layout_is_not_generic_decode_failed():
    result = classify_curve_probe({"decode_status": "unsupported_layout"})
    assert result.event_type == "curve_state_decode_failed"
    assert result.status == "unsupported_layout"
