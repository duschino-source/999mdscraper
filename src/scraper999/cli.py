"""Command-line interface for scraper999."""

import argparse
import asyncio
import csv
import json
import logging
from pathlib import Path

from .core import Scraper999


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape 999.md listings into SQLite and a file")
    parser.add_argument(
        "--url",
        default="https://999.md/ro/list/computers-and-office-equipment/video",
        help="999.md category or search URL",
    )
    parser.add_argument(
        "--pages", type=int, default=999,
        help="Maximum number of category pages (default: 999; stops after two empty pages)",
    )
    parser.add_argument("--concurrency", type=int, default=3, help="Pages to fetch concurrently (default: 3)")
    parser.add_argument("--db", default="scraper.db", help="SQLite database path")
    parser.add_argument("--output", default="listings.csv", help="Output path (.csv or .json)")
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    return parser


def main():
    args = _parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    output = Path(args.output)
    if output.suffix.lower() not in {".csv", ".json"}:
        raise SystemExit("--output must end with .csv or .json")

    scraper = Scraper999(db_path=args.db)
    try:
        listings = asyncio.run(
            scraper.run_scraper(args.url, max_pages=args.pages, concurrency=args.concurrency)
        )
    finally:
        scraper.close()

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() == ".json":
        output.write_text(json.dumps(listings, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        columns = ("title", "price", "currency", "description", "url", "price_dropped")
        with output.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=columns)
            writer.writeheader()
            writer.writerows({key: item.get(key) for key in columns} for item in listings)
    logging.info("Scraped %d listings; database: %s; export: %s", len(listings), args.db, output)


if __name__ == "__main__":
    main()
