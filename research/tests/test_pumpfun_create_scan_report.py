import json

from research.mtp_research.ingestion.pumpfun_create_scan_report import write_pumpfun_create_scan_report
from research.mtp_research.ingestion.pumpfun_create_scanner_models import (
    PumpFunCreateCandidate,
    PumpFunCreateScanReport,
)


def test_report_writer_creates_markdown_and_json(tmp_path) -> None:
    report = PumpFunCreateScanReport(
        report_id="pumpfun_create_scan_test",
        created_at="2026-06-01T00:00:00+00:00",
        program_id="program-1",
        executed=True,
        max_batches=1,
        signatures_per_batch=5,
        hydrate_limit_per_batch=5,
        create_candidate_count=1,
        candidates=[
            PumpFunCreateCandidate(
                signature="sig-1",
                block_time=1_780_000_000,
                token_mint="mint-1",
                bonding_curve="bonding-1",
                associated_bonding_curve="assoc-1",
                creator_wallet="creator-1",
                account_count=14,
                extraction_confidence="medium",
                warning_flags=["heuristic_create_detection"],
            )
        ],
        viability="maybe_viable",
        recommended_next_action="improve parser using saved examples",
    )

    paths = write_pumpfun_create_scan_report(report, tmp_path)

    assert paths["json"].exists()
    assert paths["markdown"].exists()
    assert json.loads(paths["json"].read_text(encoding="utf-8"))["create_candidate_count"] == 1
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "This is a bounded discovery probe, not a launch dataset." in markdown
    assert "mint-1" in markdown
