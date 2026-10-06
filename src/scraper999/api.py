"""Optional local FastAPI interface for scraping and price history."""

import os
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .core import Scraper999

app = FastAPI(title="999.md Scraper API", version="2.1.0")
DATA_DIR = Path(os.environ.get("SCRAPER_DATA_DIR", "data")).expanduser().resolve()
DATABASE_PATH = DATA_DIR / "scraper.db"


class ScrapeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    pages: int = Field(default=999, ge=1, le=999)
    concurrency: int = Field(default=3, ge=1, le=10)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/scrape")
async def scrape_endpoint(request: ScrapeRequest):
    try:
        Scraper999._validate_url(request.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    scraper = Scraper999(db_path=DATABASE_PATH)
    try:
        results = await scraper.run_scraper(
            base_url=request.url,
            max_pages=request.pages,
            concurrency=request.concurrency,
        )
        return {"status": "success", "items_scraped": len(results), "data": results}
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Scraping failed") from exc
    finally:
        scraper.close()


@app.get("/api/price-history")
async def price_history(url: str):
    try:
        Scraper999._validate_url(url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    parsed = urlparse(url)
    canonical_url = f"https://999.md{parsed.path}"
    scraper = Scraper999(db_path=DATABASE_PATH)
    try:
        return {"url": canonical_url, "history": scraper.get_price_history(canonical_url)}
    finally:
        scraper.close()


def main():
    import uvicorn

    uvicorn.run("scraper999.api:app", host="127.0.0.1", port=8000)
