import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://999.md/ro/list/computers-and-office-equipment/video")
        await page.wait_for_timeout(2000)
        items = await page.locator('a[href*="/ro/"]:has(div), a[href*="/ro/"]:has(span), li a[href*="/ro/"]').all()
        
        with open("output.txt", "w", encoding="utf-8") as f:
            for item in items[:2]:
                html = await item.evaluate("el => el.outerHTML")
                f.write(html + "\n\n")
        await browser.close()

asyncio.run(run())
