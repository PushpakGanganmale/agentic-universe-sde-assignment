"""Command-line interface for Assignment A."""

import argparse
import json

from .database import DB_PATH
from .events import ingest_events
from .ingestion import ingest_leads
from .reporting import generate_reports


def build_parser():
    parser = argparse.ArgumentParser(
        description="Ingest interaction ledger data and generate reports."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser(
        "ingest",
        help="Ingest lead CSVs and event JSONL files from one drop directory.",
    )
    ingest_parser.add_argument("drop_dir", help="Path to data/drop_N")
    ingest_parser.add_argument(
        "--db",
        default=str(DB_PATH),
        help=f"SQLite database path (default: {DB_PATH})",
    )

    report_parser = subparsers.add_parser(
        "report",
        help="Generate all five report files.",
    )
    report_parser.add_argument(
        "--out",
        default="reports",
        help="Report output directory (default: reports)",
    )
    report_parser.add_argument(
        "--db",
        default=str(DB_PATH),
        help=f"SQLite database path (default: {DB_PATH})",
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "ingest":
        lead_results = ingest_leads(args.drop_dir, args.db)
        event_results = ingest_events(args.drop_dir, args.db)

        print(json.dumps({
            "drop": args.drop_dir,
            "lead_files": lead_results,
            "event_files": event_results,
        }, indent=2, default=str))
        return

    if args.command == "report":
        result = generate_reports(args.out, args.db)
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
