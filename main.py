import asyncio

import argparse
import json
import os
import sys
from pathlib import Path

from infra.rpc_client import SolanaRPC
from paper_trader import PaperTrader
from infra.market_checker import MarketChecker
from execution.jupiter_quote import JupiterQuoteEngine
from core.market_radar import run_market_radar_loop
from core.open_position_monitor import run_open_position_monitor
from core.runtime_status import update_component
from core.settings_manager import load_settings


ROOT = Path(__file__).resolve().parent
MANUAL_RESEARCH_DIR = ROOT / "data" / "manual_research"
SCORE_READY_REPORT = ROOT / "data" / "reports" / "historical_backfill" / "score_ready_market_context_report.json"
RECOVERY_PLAN = ROOT / "data" / "reports" / "historical_backfill" / "archival_supply_recovery_plan.json"
STAGE8_REPORT = ROOT / "data" / "reports" / "replay_validation" / "stage8_validation_readiness_report.json"


def runtime_interval(name, default, minimum=0.2):
    try:
        value = float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default
    return max(minimum, value)


def configure_event_loop():
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        print("⚡ uvloop enabled")
    except ImportError:
        print("⚠️ uvloop not installed, using default asyncio")


def load_wallets():
    with open("data/tracked_wallets.json", "r") as f:
        data = json.load(f)
        return [w["trackedWalletAddress"] for w in data]


def load_paper_watch_wallets():
    try:
        with open("data/paper_watch_wallets.json", "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    except Exception:
        return []

    rows = data.get("wallets") if isinstance(data, dict) else data
    wallets = []
    for row in rows or []:
        if isinstance(row, dict):
            wallet = row.get("wallet") or row.get("address") or row.get("trackedWalletAddress")
            if wallet and row.get("status", "paper_watch") != "demote_review":
                wallets.append(wallet)
        elif row:
            wallets.append(str(row))
    return list(dict.fromkeys(wallets))


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def print_manual_research_instructions():
    from research.manual_gold_set import MANUAL_RESEARCH_TEXT

    print("\n" + "=" * 72)
    print(MANUAL_RESEARCH_TEXT)
    print("=" * 72)


def run_proof_candidates(args):
    from research.manual_gold_set import rank_proof_candidates

    candidates = rank_proof_candidates(
        read_json(SCORE_READY_REPORT, {"records": []}),
        read_json(RECOVERY_PLAN, {"candidate_rows": []}),
        limit=args.limit,
    )
    print(json.dumps({"candidates": candidates, "count": len(candidates)}, indent=2, sort_keys=True))
    print_manual_research_instructions()
    return 0


def run_proof_candidate_groups(args):
    from research.manual_gold_set import rank_proof_candidate_groups

    groups = rank_proof_candidate_groups(
        read_json(SCORE_READY_REPORT, {"records": []}),
        read_json(RECOVERY_PLAN, {"candidate_rows": []}),
        limit=args.limit,
    )
    print(json.dumps({"groups": groups, "count": len(groups)}, indent=2, sort_keys=True))
    print(
        "\nGrouped rows collapse repeated exact mint/timestamp checks. "
        "Verify the representative row only when the source clearly shows decision-time-safe evidence."
    )
    print_manual_research_instructions()
    return 0


def run_export_manual_research(args):
    from research.manual_gold_set import build_manual_research_packet

    packet = build_manual_research_packet(
        read_json(SCORE_READY_REPORT, {"records": []}),
        read_json(RECOVERY_PLAN, {"candidate_rows": []}),
        output_dir=MANUAL_RESEARCH_DIR,
        limit=args.limit,
    )
    print(json.dumps(packet["summary"], indent=2, sort_keys=True))
    print(f"CSV: {packet['output_paths']['csv']}")
    print(f"JSON: {packet['output_paths']['json']}")
    print(f"Template: {packet['output_paths']['manual_evidence_template']}")
    print_manual_research_instructions()
    return 0


def run_export_manual_research_groups(args):
    from research.manual_gold_set import build_manual_research_group_packet

    packet = build_manual_research_group_packet(
        read_json(SCORE_READY_REPORT, {"records": []}),
        read_json(RECOVERY_PLAN, {"candidate_rows": []}),
        output_dir=MANUAL_RESEARCH_DIR,
        limit=args.limit,
    )
    print(json.dumps(packet["summary"], indent=2, sort_keys=True))
    print(f"CSV: {packet['output_paths']['csv']}")
    print(f"JSON: {packet['output_paths']['json']}")
    print(f"Template: {packet['output_paths']['manual_evidence_template']}")
    print(
        "\nUse the group packet first. One Tier A historical market-cap check can cover "
        "the exact mint/timestamp group; do not reuse it across different timestamps."
    )
    print_manual_research_instructions()
    return 0


def run_export_manual_entry_sheet(args):
    from research.manual_gold_set import build_manual_market_cap_entry_page

    page = build_manual_market_cap_entry_page(
        read_json(SCORE_READY_REPORT, {"records": []}),
        read_json(RECOVERY_PLAN, {"candidate_rows": []}),
        output_dir=MANUAL_RESEARCH_DIR,
        limit=args.limit,
    )
    print(json.dumps(page["summary"], indent=2, sort_keys=True))
    print(f"HTML entry sheet: {page['output_paths']['html']}")
    print(
        "\nOpen the HTML sheet, type only raw market-cap numbers, then click Export CSV. "
        "Import the downloaded CSV with `python main.py import-manual-evidence <csv>`."
    )
    return 0


def run_import_manual_evidence(args):
    from research.manual_gold_set import import_manual_evidence

    report = import_manual_evidence(
        args.csv_path,
        score_ready_report=read_json(SCORE_READY_REPORT, {"records": []}),
        recovery_plan=read_json(RECOVERY_PLAN, {"candidate_rows": []}),
        output_dir=MANUAL_RESEARCH_DIR,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(f"Imported evidence: {report['output_paths']['manual_evidence_imported']}")
    print(f"Tier A supply records: {report['output_paths']['manual_supply_evidence_records']}")
    print(f"Rejected rows: {report['output_paths']['manual_evidence_rejected']}")
    print("\nNext: run `python main.py proof-readiness` to see manual-adjusted readiness.")
    return 0


def run_import_solscan_evidence(args):
    from research.manual_gold_set import import_solscan_historical_evidence

    report = import_solscan_historical_evidence(
        args.csv_path,
        candidate_id=args.candidate_id,
        source_url=args.source_url,
        score_ready_report=read_json(SCORE_READY_REPORT, {"records": []}),
        recovery_plan=read_json(RECOVERY_PLAN, {"candidate_rows": []}),
        output_dir=MANUAL_RESEARCH_DIR,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    output_paths = report.get("output_paths", {})
    if output_paths:
        print(f"Imported Solscan evidence: {output_paths.get('solscan_historical_evidence_imported')}")
        print(f"Rejected rows: {output_paths.get('solscan_historical_evidence_rejected')}")
        print(f"Report: {output_paths.get('report')}")
    print(
        "\nNote: Solscan historical activity evidence is partial review evidence. "
        "It does not unlock proof readiness without separate Tier A decision-time supply evidence."
    )
    return 0


def run_proof_readiness(args):
    from research.manual_gold_set import build_proof_readiness_report, read_jsonl

    manual_rows = read_jsonl(MANUAL_RESEARCH_DIR / "manual_evidence_imported.jsonl")
    report = build_proof_readiness_report(
        score_ready_report=read_json(SCORE_READY_REPORT, {"summary": {}}),
        stage8_report=read_json(STAGE8_REPORT, {"summary": {}}),
        manual_evidence_rows=manual_rows,
    )
    out = MANUAL_RESEARCH_DIR / "manual_proof_readiness_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(f"Report: {out}")
    return 0


def run_provider_response_workflow(args):
    from utils.build_provider_response_workflow import write_provider_response_workflow_report

    report = write_provider_response_workflow_report()
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(f"\nNext action: {report['next_action']['code']}")
    print(report["next_action"]["detail"])
    print(f"\nReport: {report['output_paths']['report']}")
    print("\nFocused workflow commands:")
    for command in report["operator_commands"]:
        print(f"- {command}")
    return 0


def run_export_focused_supply_research(args):
    from utils.build_focused_manual_supply_research import write_focused_manual_supply_packet

    report = write_focused_manual_supply_packet(limit=args.limit)
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(f"Packet CSV: {report['output_paths']['packet_csv']}")
    print(f"Template CSV: {report['output_paths']['manual_supply_template']}")
    print(
        "\nUse Tier A only when the source proves supply and decimals at or before "
        "max_acceptable_snapshot_slot. Do not guess."
    )
    return 0


def run_import_focused_supply_evidence(args):
    from utils.build_focused_manual_supply_research import import_focused_manual_supply_template

    report = import_focused_manual_supply_template(csv_path=args.csv_path)
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(f"Manual snapshots: {report['output_paths']['manual_supply_snapshots']}")
    print(f"Report: {report['output_paths']['report']}")
    print("\nNext: run `python3 utils/build_archival_supply_evidence.py` and rebuild proof-readiness.")
    return 0


def cli_main(argv=None):
    parser = argparse.ArgumentParser(description="MemeTraderPro Quant Wallet Tracker V2")
    subparsers = parser.add_subparsers(dest="command")

    proof_candidates = subparsers.add_parser(
        "proof-candidates",
        help="List top blocked proof rows for manual Gold Set research.",
    )
    proof_candidates.add_argument("--limit", type=int, default=25)
    proof_candidates.set_defaults(func=run_proof_candidates)

    proof_candidate_groups = subparsers.add_parser(
        "proof-candidate-groups",
        help="List grouped blocked proof rows for manual Gold Set research.",
    )
    proof_candidate_groups.add_argument("--limit", type=int, default=25)
    proof_candidate_groups.set_defaults(func=run_proof_candidate_groups)

    export_manual = subparsers.add_parser(
        "export-manual-research",
        help="Export manual research packet and evidence template.",
    )
    export_manual.add_argument("--limit", type=int, default=25)
    export_manual.set_defaults(func=run_export_manual_research)

    export_manual_groups = subparsers.add_parser(
        "export-manual-research-groups",
        help="Export grouped manual research packet and evidence template.",
    )
    export_manual_groups.add_argument("--limit", type=int, default=25)
    export_manual_groups.set_defaults(func=run_export_manual_research_groups)

    export_manual_entry = subparsers.add_parser(
        "export-manual-entry-sheet",
        help="Export a simple browser entry sheet for Dexscreener market-cap evidence.",
    )
    export_manual_entry.add_argument("--limit", type=int, default=25)
    export_manual_entry.set_defaults(func=run_export_manual_entry_sheet)

    import_manual = subparsers.add_parser(
        "import-manual-evidence",
        help="Import manually researched Gold Set evidence.",
    )
    import_manual.add_argument("csv_path", type=Path)
    import_manual.set_defaults(func=run_import_manual_evidence)

    import_solscan = subparsers.add_parser(
        "import-solscan-evidence",
        help="Import a Solscan historical activity CSV as partial review evidence.",
    )
    import_solscan.add_argument("csv_path", type=Path)
    import_solscan.add_argument("--candidate-id", required=True)
    import_solscan.add_argument("--source-url", required=True)
    import_solscan.set_defaults(func=run_import_solscan_evidence)

    proof_readiness = subparsers.add_parser(
        "proof-readiness",
        help="Report current and manual-adjusted proof readiness.",
    )
    proof_readiness.set_defaults(func=run_proof_readiness)

    provider_workflow = subparsers.add_parser(
        "provider-response-workflow",
        help="Inspect the focused archival response handoff and show the next safe operator action.",
    )
    provider_workflow.set_defaults(func=run_provider_response_workflow)

    focused_supply_export = subparsers.add_parser(
        "export-focused-supply-research",
        help="Export focused manual supply research packet/template for provider-recommended rows.",
    )
    focused_supply_export.add_argument("--limit", type=int, default=None)
    focused_supply_export.set_defaults(func=run_export_focused_supply_research)

    focused_supply_import = subparsers.add_parser(
        "import-focused-supply-evidence",
        help="Import focused manual supply evidence and emit Tier A replay-safe snapshots.",
    )
    focused_supply_import.add_argument("csv_path", type=Path)
    focused_supply_import.set_defaults(func=run_import_focused_supply_evidence)

    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        return None
    return args.func(args)


async def heartbeat(paper_trader, interval=30):
    while True:
        try:
            state = paper_trader.get_state()

            open_count = len(state.get("open_trades", []))
            closed_count = len(state.get("closed_trades", []))
            failed_count = len(state.get("failed_trades", []))

            print(
                f"💓 Bot alive | open: {open_count} | closed: {closed_count} | failed: {failed_count}"
            )

            update_component(
                "bot",
                status="alive",
                last_error=None,
                open_trades=open_count,
                closed_trades=closed_count,
                failed_trades=failed_count,
                heartbeat_interval=interval,
            )

            await asyncio.sleep(interval)

        except Exception as e:
            print("❌ Heartbeat error:", e)
            update_component("bot", status="heartbeat_error", last_error=str(e))
            await asyncio.sleep(interval)


async def main():
    price_interval = runtime_interval("MEMETRADER_PRICE_INTERVAL_SECONDS", 1.0)
    settings = load_settings()
    market_radar_interval = runtime_interval(
        "MEMETRADER_MARKET_RADAR_INTERVAL_SECONDS",
        settings.get("market_radar_interval_seconds", 120),
        minimum=30,
    )
    tracked_wallets = load_wallets()
    paper_watch_wallets = load_paper_watch_wallets()
    print(f"✅ Loaded {len(tracked_wallets)} tracked wallets")
    print(f"🧪 Loaded {len(paper_watch_wallets)} paper-watch wallets")
    update_component(
        "bot",
        status="starting",
        tracked_wallets=len(tracked_wallets),
        paper_watch_wallets=len(paper_watch_wallets),
    )

    paper_trader = PaperTrader()
    market_checker = MarketChecker()
    jupiter_quote = JupiterQuoteEngine()
    rpc = SolanaRPC(
        tracked_wallets,
        paper_watch_wallets=paper_watch_wallets,
        paper_watch_loader=load_paper_watch_wallets,
    )

    rpc.scanner.paper_trader = paper_trader
    rpc.market_checker = market_checker
    rpc.jupiter_quote = jupiter_quote

    try:
        await asyncio.gather(
            rpc.connect(),
            run_open_position_monitor(
                paper_trader=paper_trader,
                market_checker=market_checker,
                interval=price_interval,
            ),
            run_market_radar_loop(
                market_checker=market_checker,
                paper_trader=paper_trader,
                jupiter_quote=jupiter_quote,
                interval=market_radar_interval,
                rpc=rpc,
            ),
            heartbeat(paper_trader, interval=30),
        )

    finally:
        update_component("bot", status="stopping")

        if rpc.session:
            await rpc.session.close()

        if market_checker.session:
            await market_checker.session.close()

        await jupiter_quote.close()


if __name__ == "__main__":
    cli_result = cli_main(sys.argv[1:])
    if cli_result is not None:
        raise SystemExit(cli_result)
    try:
        configure_event_loop()
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped cleanly.")
