"""Browser-backed scraper and SQLite price history for 999.md."""

import asyncio
import logging
import random
import re
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)
LISTING_HREF_RE = re.compile(r"^/ro/(\d+)(?:\?|$)")
PRICE_NUMBER_RE = re.compile(r"(?<!\w)(\d[\d\s\u00a0\u202f.,'’]*\d|\d)")
EMPTY_PAGE_LIMIT = 2


class Scraper999:
    def __init__(self, db_path: str | Path = "scraper.db"):
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS items (
                url TEXT PRIMARY KEY,
                title TEXT,
                price REAL,
                currency TEXT,
                description TEXT,
                date_added TEXT,
                last_seen TEXT,
                price_dropped INTEGER DEFAULT 0
            )"""
        )
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY,
                url TEXT NOT NULL,
                price REAL NOT NULL,
                currency TEXT,
                observed_at TEXT NOT NULL
            )"""
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_price_history_url_time "
            "ON price_history(url, observed_at)"
        )
        # Existing databases only have the latest price. Preserve it as the
        # earliest history point available after upgrading.
        self.conn.execute(
            """INSERT INTO price_history (url, price, currency, observed_at)
               SELECT i.url, i.price, i.currency, COALESCE(i.last_seen, i.date_added)
               FROM items AS i
               WHERE i.price IS NOT NULL AND COALESCE(i.last_seen, i.date_added) IS NOT NULL
                 AND NOT EXISTS (SELECT 1 FROM price_history AS h WHERE h.url = i.url)"""
        )
        self.conn.commit()

    @staticmethod
    def _validate_url(base_url: str) -> str:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
            "999.md", "www.999.md"
        }:
            raise ValueError("URL must point to https://999.md or https://www.999.md")
        return base_url.rstrip("?")

    @staticmethod
    def _parse_price(price_text: str | None) -> tuple[int | float | None, str | None]:
        if not price_text or price_text.strip().upper() == "N/A":
            return None, None

        normalized = price_text.lower()
        if any(token in normalized for token in ("lei", "mdl", "лей")):
            currency = "MDL"
        elif "€" in normalized or "eur" in normalized:
            currency = "EUR"
        elif "$" in normalized or "usd" in normalized:
            currency = "USD"
        else:
            currency = None

        match = PRICE_NUMBER_RE.search(price_text)
        if not match:
            return None, currency

        number = match.group(1).replace("\u00a0", "").replace("\u202f", "")
        number = re.sub(r"[\s'’]", "", number)
        dot, comma = number.rfind("."), number.rfind(",")
        if dot >= 0 and comma >= 0:
            decimal_separator = "." if dot > comma else ","
            grouping_separator = "," if decimal_separator == "." else "."
            number = number.replace(grouping_separator, "")
            if decimal_separator == ",":
                number = number.replace(",", ".")
        elif dot >= 0 or comma >= 0:
            separator = "." if dot >= 0 else ","
            chunks = number.split(separator)
            if len(chunks) > 2 and all(len(chunk) == 3 for chunk in chunks[1:]):
                number = "".join(chunks)
            elif len(chunks) == 2 and len(chunks[1]) == 3:
                number = "".join(chunks)
            else:
                number = "".join(chunks[:-1]) + "." + chunks[-1]

        try:
            value = Decimal(number)
        except InvalidOperation:
            return None, currency
        return (int(value) if value == value.to_integral_value() else float(value)), currency

    @staticmethod
    def _parse_listing_card(href: str | None, text: str) -> dict | None:
        """Parse one listing anchor; ignore navigation and sponsored placements."""
        if not href:
            return None
        parsed = urlparse(href)
        if not LISTING_HREF_RE.fullmatch(parsed.path):
            return None
        query = parse_qs(parsed.query)
        # 999.md now adds clickToken to regular links too. Only exclude links
        # explicitly marked as boosted instead of dropping every clickToken.
        if "booster" in query.get("adType", []):
            return None

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return None
        price_line = next(
            (
                line
                for line in lines
                if re.search(r"(?:MDL|\blei\b|лей|€|\bEUR\b|\$|\bUSD\b)", line, re.I)
            ),
            None,
        )
        title_candidates = [line for line in lines if line != price_line]
        while title_candidates and title_candidates[0].casefold() in {
            "preț avantajos", "pret avantajos", "super preț", "super pret", "reducere"
        }:
            title_candidates.pop(0)
        if not title_candidates:
            return None
        title = title_candidates[0]
        description = next(
            (line for line in title_candidates[1:] if len(line) > 15), "N/A"
        )
        price, currency = Scraper999._parse_price(price_line)
        return {
            "title": title,
            "price": price,
            "currency": currency,
            "description": description,
            "url": urljoin("https://999.md", parsed.path),
        }

    def _save_listing(self, listing: dict, observed_at: str) -> dict:
        previous = self.conn.execute(
            "SELECT price, currency, price_dropped, date_added FROM items WHERE url = ?",
            (listing["url"],),
        ).fetchone()
        old_price, old_currency, old_drop, date_added = previous or (None, None, 0, observed_at)
        price = listing["price"]
        dropped = int(old_price is not None and price is not None and price < old_price)
        if price is not None and (old_price != price or old_currency != listing["currency"]):
            self.conn.execute(
                "INSERT INTO price_history (url, price, currency, observed_at) VALUES (?, ?, ?, ?)",
                (listing["url"], price, listing["currency"], observed_at),
            )
        self.conn.execute(
            """INSERT INTO items
               (url, title, price, currency, description, date_added, last_seen, price_dropped)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(url) DO UPDATE SET
                 title=excluded.title,
                 price=COALESCE(excluded.price, items.price),
                 currency=COALESCE(excluded.currency, items.currency),
                 description=excluded.description,
                 last_seen=excluded.last_seen,
                 price_dropped=CASE WHEN excluded.price IS NULL
                   THEN items.price_dropped ELSE excluded.price_dropped END""",
            (
                listing["url"], listing["title"], price, listing["currency"],
                listing["description"], date_added, observed_at, dropped,
            ),
        )
        result = dict(listing)
        result["price_dropped"] = dropped if price is not None else old_drop
        return result

    async def _scrape_page(self, context, base_url: str, page_num: int):
        page = await context.new_page()
        url = f"{base_url}{'&' if '?' in base_url else '?'}page={page_num}"
        extracted: dict[str, dict] = {}
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            try:
                await page.wait_for_function(
                    """() => [...document.querySelectorAll('a[href^="/ro/"]')]
                        .some(a => /^\\/ro\\/\\d+(?:\\?|$)/.test(a.getAttribute('href') || ''))""",
                    timeout=8_000,
                )
            except PlaywrightTimeoutError:
                # Empty result pages are valid; a blank page will be counted by
                # the ordered pagination logic below.
                pass

            links = page.locator('a[href^="/ro/"]')
            for index in range(await links.count()):
                anchor = links.nth(index)
                listing = self._parse_listing_card(
                    await anchor.get_attribute("href"), await anchor.inner_text()
                )
                if listing:
                    extracted[listing["url"]] = listing

            now = datetime.now(timezone.utc).isoformat()
            output = [self._save_listing(listing, now) for listing in extracted.values()]
            self.conn.commit()
            return len(output), output
        except Exception:
            self.conn.rollback()
            logger.exception("Could not scrape page %s (%s)", page_num, url)
            raise
        finally:
            await page.close()

    @staticmethod
    async def _collect_pages(fetch_page, max_pages: int, concurrency: int):
        """Fetch page batches in order, tolerating an isolated empty page."""
        all_results = []
        empty_streak = 0
        for start in range(1, max_pages + 1, concurrency):
            end = min(start + concurrency, max_pages + 1)
            results = await asyncio.gather(*(fetch_page(number) for number in range(start, end)))
            for count, listings in results:
                all_results.extend(listings)
                empty_streak = empty_streak + 1 if count == 0 else 0
            if empty_streak >= EMPTY_PAGE_LIMIT:
                logger.info("Reached %d consecutive empty pages; stopping pagination", empty_streak)
                break
        return all_results

    async def run_scraper(self, base_url: str, max_pages: int = 999, concurrency: int = 3):
        base_url = self._validate_url(base_url)
        if max_pages < 1:
            raise ValueError("max_pages must be at least 1")
        if concurrency < 1:
            raise ValueError("concurrency must be at least 1")

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                    )
                )
                try:
                    return await self._collect_pages(
                        lambda number: self._scrape_with_delay(context, base_url, number),
                        max_pages=max_pages,
                        concurrency=concurrency,
                    )
                finally:
                    await context.close()
            finally:
                await browser.close()

    async def _scrape_with_delay(self, context, base_url: str, page_num: int):
        await asyncio.sleep(random.uniform(0.25, 0.75))
        return await self._scrape_page(context, base_url, page_num)

    def get_price_history(self, url: str) -> list[dict]:
        self._validate_url(url)
        rows = self.conn.execute(
            "SELECT price, currency, observed_at FROM price_history WHERE url = ? ORDER BY observed_at, id",
            (url,),
        ).fetchall()
        return [
            {"price": price, "currency": currency, "observed_at": observed_at}
            for price, currency, observed_at in rows
        ]

    def close(self):
        self.conn.close()
