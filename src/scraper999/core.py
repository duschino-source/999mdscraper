import asyncio
import random
import logging
import os
import subprocess
import sqlite3
import re
from datetime import datetime
from playwright.async_api import async_playwright
from playwright._impl._driver import compute_driver_executable

# Force Playwright to use the global local appdata folder for browsers
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "ms-playwright")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class Scraper999:
    def __init__(self, db_path="scraper.db"):
        self.db_path = db_path
        self._ensure_chromium_installed()
        self._init_db()

    def _ensure_chromium_installed(self):
        try:
            node_exe, cli_js = compute_driver_executable()
            subprocess.run([node_exe, cli_js, "install", "chromium"], capture_output=True)
        except Exception as e:
            logging.warning(f"Could not auto-install chromium: {e}")

    def _init_db(self):
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        cursor = self.conn.cursor()
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
        self.conn.commit()

    def _parse_price(self, price_str):
        if not price_str or price_str == "N/A":
            return None, None
            
        price_str_lower = price_str.lower()
        currency = "Unknown"
        if "lei" in price_str_lower or "mdl" in price_str_lower:
            currency = "MDL"
        elif "€" in price_str_lower or "eur" in price_str_lower:
            currency = "EUR"
        elif "$" in price_str_lower or "usd" in price_str_lower:
            currency = "USD"
            
        digits = re.sub(r'[^\d]', '', price_str)
        price_val = int(digits) if digits else None
        
        return price_val, currency

    async def _scrape_page(self, context, base_url, page_num):
        url = f"{base_url}?page={page_num}"
        page = await context.new_page()
        found_on_page = 0
        inserted_items = []
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            
            items = await page.locator('a[href*="/ro/"]:has(div), a[href*="/ro/"]:has(span), li a[href*="/ro/"]').all()
            
            extracted_items = []
            for item in items:
                href = await item.get_attribute("href")
                if not href or any(x in href for x in ['/category/', '/list/', 'page=', '/info/', '/sitemap', '/blog', 'clickToken=']):
                    continue
                
                full_link = f"https://999.md{href}" if href.startswith('/') else href
                text_content = (await item.inner_text()).strip()
                lines = [line.strip() for line in text_content.split('\n') if line.strip()]
                
                if len(lines) >= 1:
                    title = lines[0]
                    raw_price = "N/A"
                    description = "N/A"
                    
                    skip_keywords = [
                        "laptop", "reparați", "reparati", "epson", "cartuș", "cartus", 
                        "auto", "instalare", "windows", "macbook", "ps plus", 
                        "eurogsm", "tablete", "ecrane", "birotică", "birotica",
                        "ea play", "playstation", "xbox", "gamepad", "joystick",
                        "aparat", "imprimant", "tv", "televizor", "servicii",
                        "telefoane", "iphone", "samsung", "xiaomi", "nintendo"
                    ]
                    if any(kw in title.lower() for kw in skip_keywords):
                        continue
                    
                    for line in lines[1:]:
                        if "MDL" in line or "€" in line or "$" in line or "lei" in line.lower():
                            raw_price = line
                        elif len(line) > 15 and line != raw_price:
                            description = line
                    
                    price_val, currency = self._parse_price(raw_price)
                    
                    extracted_items.append({
                        "title": title,
                        "price_val": price_val,
                        "currency": currency,
                        "description": description,
                        "url": full_link
                    })
            
            unique_items = {item["url"]: item for item in extracted_items}.values()
            
            if not unique_items:
                await page.close()
                return 0, []
                
            cursor = self.conn.cursor()
            now_str = datetime.now().isoformat()
            
            for item in unique_items:
                cursor.execute("SELECT price FROM items WHERE url = ?", (item['url'],))
                row = cursor.fetchone()
                
                price_dropped = 0
                if row and row[0] is not None and item['price_val'] is not None:
                    old_price = row[0]
                    if item['price_val'] < old_price:
                        price_dropped = 1
                elif row:
                    cursor.execute("SELECT price_dropped FROM items WHERE url = ?", (item['url'],))
                    price_dropped = cursor.fetchone()[0]

                if not row:
                    cursor.execute('''
                        INSERT INTO items (url, title, price, currency, description, date_added, last_seen, price_dropped)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (item['url'], item['title'], item['price_val'], item['currency'], item['description'], now_str, now_str, price_dropped))
                else:
                    cursor.execute('''
                        UPDATE items 
                        SET title = ?, price = ?, currency = ?, description = ?, last_seen = ?, price_dropped = ?
                        WHERE url = ?
                    ''', (item['title'], item['price_val'], item['currency'], item['description'], now_str, price_dropped, item['url']))
                    
                found_on_page += 1
                item['price_dropped'] = price_dropped
                inserted_items.append(item)
                
            self.conn.commit()
            
        except Exception as e:
            logging.error(f"Error scraping page {page_num}: {e}")
            
        await page.close()
        return found_on_page, inserted_items

    async def run_scraper(self, base_url, max_pages=999, concurrency=5):
        all_results = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
            )
            
            semaphore = asyncio.Semaphore(concurrency)
            
            async def sem_scrape(page_num):
                async with semaphore:
                    await asyncio.sleep(random.uniform(0.5, 2.0))
                    return await self._scrape_page(context, base_url, page_num)

            current_page = 1
            while current_page <= max_pages:
                chunk_end = min(current_page + concurrency, max_pages + 1)
                tasks = [sem_scrape(p) for p in range(current_page, chunk_end)]
                
                results = await asyncio.gather(*tasks)
                
                for count, items in results:
                    all_results.extend(items)
                
                if any(count == 0 for count, _ in results):
                    logging.info("Hit an empty page. Stopping pagination early.")
                    break
                    
                current_page = chunk_end

            await browser.close()
        return all_results

    def close(self):
        self.conn.close()
