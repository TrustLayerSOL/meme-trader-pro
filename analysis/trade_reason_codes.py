# Verbatim taxonomy per research/BUILD_PLAN.md Phase A (labels are stable identifiers).

POSTMORTEM_CLASSIFICATION_TAGS = (
    "winner",
    "loser",
    "rug event",
    "momentum fade",
    "weak cluster",
    "late signal",
    "liquidity collapse",
    "holder concentration issue",
    "delayed execution issue",
    "stop-loss exit",
    "take-profit exit",
    "trailing-stop exit",
    "social hype failure",
    "volume exhaustion",
    "fake breakout",
)

TRACKED_FIELDS = (
    "entry reason",
    "exit reason",
    "wallet cluster composition",
    "wallet quality score",
    "token age",
    "liquidity at entry",
    "holder concentration",
    "social signal tags if available",
    "market regime",
    "entry delay estimate",
    "slippage estimate",
)


EXIT_ATTRIBUTION = (
    "fixed TP",
    "trailing stop",
    "emergency exit",
    "momentum continuation",
    "timeout exit",
)


REJECTION_REASON_EXAMPLES = (
    "liquidity too low",
    "wallet quality below threshold",
    "cluster too slow",
    "holder concentration too high",
    "token too old",
    "weak momentum",
    "social mismatch",
)
