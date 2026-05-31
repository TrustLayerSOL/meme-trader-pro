from research.mtp_research.backtest.rule_library import default_rule_library


def test_default_rule_library_returns_non_empty_rules() -> None:
    assert default_rule_library()


def test_rule_ids_are_unique() -> None:
    rules = default_rule_library()
    assert len({rule.rule_id for rule in rules}) == len(rules)


def test_every_rule_has_at_least_one_condition() -> None:
    assert all(rule.conditions for rule in default_rule_library())


def test_every_rule_description_mentions_exploratory_or_not_live_trading() -> None:
    for rule in default_rule_library():
        description = rule.description.lower()
        assert "exploratory" in description or "not a live trading rule" in description
