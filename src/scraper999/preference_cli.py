"""Commands for recording and exporting local listing preferences."""

import argparse
import json
from pathlib import Path

from .preferences import PreferenceStore


def main():
    parser = argparse.ArgumentParser(
        description="Record listing choices and export preference data for local model training"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    record = commands.add_parser("record", help="Record which of two listings you prefer")
    record.add_argument("--chosen", required=True, help="URL of the listing you prefer")
    record.add_argument("--rejected", required=True, help="URL of the listing you prefer less")
    record.add_argument("--criteria", default="smartphone-criteria.json", help="Preset criteria JSON")
    record.add_argument("--reason", default="", help="Optional short explanation for your choice")
    record.add_argument("--db", default="scraper.db", help="Scraper SQLite database")

    export = commands.add_parser("export", help="Export preference pairs as DPO JSONL")
    export.add_argument("--output", default="preferences.jsonl", help="Output JSONL path")
    export.add_argument("--db", default="scraper.db", help="Scraper SQLite database")

    args = parser.parse_args()
    store = PreferenceStore(args.db)
    try:
        if args.command == "record":
            criteria_path = Path(args.criteria)
            try:
                criteria = json.loads(criteria_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise SystemExit(f"Could not read criteria file {criteria_path}: {error}") from error
            store.record(args.chosen, args.rejected, criteria, args.reason)
            print("Preference saved.")
        else:
            count = store.export_dpo(args.output)
            print(f"Exported {count} preference pairs to {args.output}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
