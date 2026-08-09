import argparse
import asyncio
import logging
from .core import Scraper999

def main():
    parser = argparse.ArgumentParser(description="Advanced 999.md Web Scraper CLI")
    parser.add_argument("--url", type=str, default="https://999.md/ro/list/computers-and-office-equipment/video", 
                        help="The base URL of the category to scrape.")
    parser.add_argument("--pages", type=int, default=999, 
                        help="Maximum number of pages to scrape.")
    parser.add_argument("--concurrency", type=int, default=5, 
                        help="Number of pages to scrape simultaneously (async).")
    parser.add_argument("--db", type=str, default="scraper.db", 
                        help="Path to the SQLite database.")
    args = parser.parse_args()
    
    logging.info(f"Starting scraper for URL: {args.url}")
    logging.info(f"Max Pages: {args.pages} | Concurrency: {args.concurrency}")
    
    scraper = Scraper999(db_path=args.db)
    
    try:
        results = asyncio.run(scraper.run_scraper(args.url, args.pages, args.concurrency))
        logging.info(f"Scraping complete! Extracted {len(results)} total items. Data saved to {args.db}")
    finally:
        scraper.close()

if __name__ == "__main__":
    main()
