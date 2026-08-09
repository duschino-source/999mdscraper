import asyncio
import random
import logging
import os
import sys
import subprocess
import argparse
import sqlite3
import re
from datetime import datetime
from playwright.async_api import async_playwright
from playwright._impl._driver import compute_driver_executable

# Force Playwright to use the global local appdata folder for browsers
# instead of the temporary _MEI PyInstaller folder where it looks by default.
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "ms-playwright")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def ensure_chromium_installed():
    try:
        node_exe, cli_js = compute_driver_executable()
        logging.info("Ensuring Chromium browser is installed (this may take a minute on first run)...")
        subprocess.run([node_exe, cli_js, "install", "chromium"], capture_output=True)
    except Exception as e:
        logging.warning(f"Could not auto-install chromium: {e}")

def init_db(db_path="scraper.db"):
    """Initialize the SQLite database and return the connection."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            url TEXT PRIMARY KEY,
            title TEXT,
            price INTEGER,
            currency TEXT,
            description TEXT,
            date_added TEXT,
            last_seen TEXT,
            price_dropped INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    return conn

def parse_price(price_str):
    """
    Extracts raw integer price and currency from a string.
    Returns (price_int, currency_str)
    e.g. "2 000 lei" -> (2000, "MDL")
         "300 €" -> (300, "EUR")
    """
    if not price_str or price_str == "N/A":
        return None, None
        
    price_str_lower = price_str.lower()
    
    # Determine currency
    currency = "Unknown"
    if "lei" in price_str_lower or "mdl" in price_str_lower:
        currency = "MDL"
    elif "€" in price_str_lower or "eur" in price_str_lower:
        currency = "EUR"
    elif "$" in price_str_lower or "usd" in price_str_lower:
        currency = "USD"
        
    # Extract all digits (removing spaces/commas used as thousands separators)
    digits = re.sub(r'[^\d]', '', price_str)
    price_val = int(digits) if digits else None
    
    return price_val, currency

async def scrape_page(context, base_url, page_num, db_conn):
    """Scrapes a single page and inserts results into SQLite."""
    logging.info(f"Scraping page {page_num}...")
    url = f"{base_url}?page={page_num}"
    
    page = await context.new_page()
    found_on_page = 0
    
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        # Wait for potential hydration and items to load
        await page.wait_for_timeout(3000)
        
        # Find all <a> tags that link to specific items (not categories)
        items = await page.locator('a[href*="/ro/"]:has(div), a[href*="/ro/"]:has(span), li a[href*="/ro/"]').all()
        
        extracted_items = []
        for item in items:
            href = await item.get_attribute("href")
            # Exclude pagination, categories, menus, footer links, and boosted ads
            if not href or any(x in href for x in ['/category/', '/list/', 'page=', '/info/', '/sitemap', '/blog', 'clickToken=']):
                continue
            
            full_link = f"https://999.md{href}" if href.startswith('/') else href
            text_content = (await item.inner_text()).strip()
            
            # Usually the text has newlines for different parts (Title\nPrice\netc.)
            lines = [line.strip() for line in text_content.split('\n') if line.strip()]
            
            if len(lines) >= 1:
                title = lines[0]
                raw_price = "N/A"
                description = "N/A"
                
                # Keyword filter to skip boosted/unrelated items
                skip_keywords = [
                    "laptop", "reparați", "reparati", "epson", "cartuș", "cartus", 
                    "auto", "instalare", "windows", "macbook", "ps plus", 
                    "eurogsm", "tablete", "ecrane", "birotică", "birotica",
                    "ea play", "playstation", "xbox", "gamepad", "joystick",
                    "aparat", "imprimant", "tv", "televizor", "servicii",
                    "telefoane", "iphone", "samsung", "xiaomi", "nintendo"
                ]
                title_lower = title.lower()
                if any(kw in title_lower for kw in skip_keywords):
                    continue
                
                # Attempt to find price and description based on typical patterns
                for line in lines[1:]:
                    if "MDL" in line or "€" in line or "$" in line or "lei" in line.lower():
                        raw_price = line
                    elif len(line) > 15 and line != raw_price:
                        description = line
                
                # Parse robust price
                price_val, currency = parse_price(raw_price)
                
                extracted_items.append({
                    "title": title,
                    "price_val": price_val,
                    "currency": currency,
                    "description": description,
                    "url": full_link
                })
        
        # Deduplicate on the current page before inserting
        unique_items = {item["url"]: item for item in extracted_items}.values()
        
        if not unique_items:
            await page.close()
            logging.warning(f"No valid items found on page {page_num}.")
            return 0
            
        cursor = db_conn.cursor()
        now_str = datetime.now().isoformat()
        
        for item in unique_items:
            # Check if it exists to detect price drops
            cursor.execute("SELECT price FROM items WHERE url = ?", (item['url'],))
            row = cursor.fetchone()
            
            price_dropped = 0
            if row and row[0] is not None and item['price_val'] is not None:
                old_price = row[0]
                if item['price_val'] < old_price:
                    price_dropped = 1
                    logging.info(f"PRICE DROP DETECTED! {item['title']} dropped from {old_price} to {item['price_val']} {item['currency']}")
            elif row:
                # Keep previous price_dropped status if it existed and didn't change
                cursor.execute("SELECT price_dropped FROM items WHERE url = ?", (item['url'],))
                price_dropped = cursor.fetchone()[0]

            if not row:
                # Insert new item
                cursor.execute('''
                    INSERT INTO items (url, title, price, currency, description, date_added, last_seen, price_dropped)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (item['url'], item['title'], item['price_val'], item['currency'], item['description'], now_str, now_str, price_dropped))
            else:
                # Update existing item
                cursor.execute('''
                    UPDATE items 
                    SET title = ?, price = ?, currency = ?, description = ?, last_seen = ?, price_dropped = ?
                    WHERE url = ?
                ''', (item['title'], item['price_val'], item['currency'], item['description'], now_str, price_dropped, item['url']))
                
            found_on_page += 1
            
        db_conn.commit()
        logging.info(f"Processed {found_on_page} items from page {page_num}.")
        
    except Exception as e:
        logging.error(f"Error scraping page {page_num}: {e}")
        
    await page.close()
    return found_on_page


async def scrape_999_md_async(base_url, max_pages=999, concurrency=5):
    ensure_chromium_installed()
    db_conn = init_db()
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        )
        
        semaphore = asyncio.Semaphore(concurrency)
        
        async def sem_scrape(page_num):
            async with semaphore:
                # Random delay to prevent hammering the server exactly at the same time
                await asyncio.sleep(random.uniform(0.5, 2.0))
                return await scrape_page(context, base_url, page_num, db_conn)

        current_page = 1
        while current_page <= max_pages:
            # We process pages in chunks matching our concurrency limit
            chunk_end = min(current_page + concurrency, max_pages + 1)
            tasks = [sem_scrape(p) for p in range(current_page, chunk_end)]
            
            results = await asyncio.gather(*tasks)
            
            # If any page in this chunk returned 0 items, we assume we've hit the end of pagination
            if 0 in results:
                logging.info("Hit an empty page. Stopping pagination early.")
                break
                
            current_page = chunk_end

        await browser.close()
    db_conn.close()

def main():
    parser = argparse.ArgumentParser(description="Advanced 999.md Web Scraper")
    parser.add_argument("--url", type=str, default="https://999.md/ro/list/computers-and-office-equipment/video", 
                        help="The base URL of the category to scrape.")
    parser.add_argument("--pages", type=int, default=999, 
                        help="Maximum number of pages to scrape.")
    parser.add_argument("--concurrency", type=int, default=5, 
                        help="Number of pages to scrape simultaneously (async).")
    args = parser.parse_args()
    
    logging.info(f"Starting scraper for URL: {args.url}")
    logging.info(f"Max Pages: {args.pages} | Concurrency: {args.concurrency}")
    
    asyncio.run(scrape_999_md_async(args.url, args.pages, args.concurrency))
    
    logging.info("Scraping complete! Data saved to scraper.db")

if __name__ == "__main__":
    main()
