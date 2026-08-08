import csv
import time
import random
import logging
import os
import sys
import subprocess
from playwright.sync_api import sync_playwright
from playwright._impl._driver import compute_driver_executable

# Force Playwright to use the global local appdata folder for browsers
# instead of the temporary _MEI PyInstaller folder where it looks by default.
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "ms-playwright")

def ensure_chromium_installed():
    try:
        node_exe, cli_js = compute_driver_executable()
        logging.info("Ensuring Chromium browser is installed (this may take a minute on first run)...")
        subprocess.run([node_exe, cli_js, "install", "chromium"], capture_output=True)
    except Exception as e:
        logging.warning(f"Could not auto-install chromium: {e}")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def scrape_999_md(base_url, max_pages=999, output_file="video_cards.csv"):
    results = []
    ensure_chromium_installed()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Using a context with a standard user agent
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        for current_page in range(1, max_pages + 1):
            logging.info(f"Scraping page {current_page}...")
            url = f"{base_url}?page={current_page}"
            
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                # Wait for potential hydration and items to load
                page.wait_for_timeout(3000)
                
                # In 999.md's new Next.js layout, the entire ad is often an <a> wrapper or a list item <li> 
                # Let's find all <a> tags that link to specific items (not categories)
                items = page.locator('a[href*="/ro/"]:has(div), a[href*="/ro/"]:has(span), li a[href*="/ro/"]').all()
                
                found_on_page = 0
                for item in items:
                    href = item.get_attribute("href")
                    # Exclude pagination, categories, menus, footer links, and boosted ads
                    if not href or any(x in href for x in ['/category/', '/list/', 'page=', '/info/', '/sitemap', '/blog', 'clickToken=']):
                        continue
                    
                    full_link = f"https://999.md{href}" if href.startswith('/') else href
                    text_content = item.inner_text().strip()
                    
                    # Usually the text has newlines for different parts (Title\nPrice\netc.)
                    # Let's split by newline and extract
                    lines = [line.strip() for line in text_content.split('\n') if line.strip()]
                    
                    if len(lines) >= 1:
                        title = lines[0]
                        price = "N/A"
                        description = "N/A"
                        
                        # Keyword filter to skip boosted/unrelated items (like laptops, repairs, etc.)
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
                                price = line
                            elif len(line) > 15 and line != price:
                                description = line
                        
                        # To avoid duplicate extraction of same items (often there are multiple <a> pointing to same ad)
                        if not any(r['Link'] == full_link for r in results):
                            results.append({
                                "Title": title,
                                "Price": price,
                                "Description": description,
                                "Link": full_link
                            })
                            found_on_page += 1

                logging.info(f"Found {found_on_page} items on page {current_page}.")
                
                if found_on_page == 0:
                    logging.warning(f"No valid items found on page {current_page}. Stopping pagination.")
                    break
                    
            except Exception as e:
                logging.error(f"Error scraping page {current_page}: {e}")
            
            sleep_time = random.uniform(1, 3)
            logging.info(f"Sleeping for {sleep_time:.2f} seconds...")
            time.sleep(sleep_time)

        browser.close()

    if results:
        try:
            with open(output_file, mode="w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=["Title", "Price", "Description", "Link"])
                writer.writeheader()
                writer.writerows(results)
            logging.info(f"Successfully saved {len(results)} items to '{output_file}'.")
        except Exception as e:
            logging.error(f"Failed to save data to CSV: {e}")
    else:
        logging.warning("No data was extracted to save.")

if __name__ == "__main__":
    target_url = "https://999.md/ro/list/computers-and-office-equipment/video"
    scrape_999_md(base_url=target_url, max_pages=999, output_file="video_cards.csv")
