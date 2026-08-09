import sys
import asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from .core import Scraper999

app = FastAPI(title="999.md Scraper API")

class ScrapeRequest(BaseModel):
    url: str
    pages: int = 10
    concurrency: int = 5
    db_path: str = "scraper.db"

@app.post("/api/scrape")
async def scrape_endpoint(request: ScrapeRequest):
    scraper = Scraper999(db_path=request.db_path)
    try:
        results = await scraper.run_scraper(
            base_url=request.url,
            max_pages=request.pages,
            concurrency=request.concurrency
        )
        return {
            "status": "success",
            "items_scraped": len(results),
            "data": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        scraper.close()

# To run: uvicorn scraper999.api:app --reload
