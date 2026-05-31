"""Smoke runner for diagnostic validation review."""

from __future__ import annotations

from research.mtp_research.validation.run_diagnostic_validation_review import (
    _parse_args,
    run_diagnostic_validation_review,
)


def main() -> int:
    args = _parse_args()
    args.min_train_rows = 5
    args.min_test_rows = 3
    result = run_diagnostic_validation_review(args)
    review = result["review"]
    print(f"clean_row_count={review.clean_dataset.row_count}")
    print(f"diagnostic_row_count={review.diagnostic_dataset.row_count}")
    print(f"nearest_fallback_row_count={review.nearest_fallback_row_count}")
    print(f"recommended_next_action={review.recommended_next_action}")
    print(f"review_markdown_path={result['review_markdown_path']}")
    print(f"review_json_path={result['review_json_path']}")
    print("network_calls=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
