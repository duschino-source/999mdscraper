# 999.md Scraper

An asynchronous Playwright scraper for 999.md category listings. It keeps listing and price history in SQLite and exports each run to CSV or JSON.

## Requirements

- Python 3.10 or newer
- Chromium, installed once through Playwright

## Install

From the repository directory, create and activate a virtual environment:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
python -m playwright install chromium
```

For the optional HTTP API, install its dependencies too:

```powershell
python -m pip install -e ".[api]"
```

To install the test and packaging tools as well, use `python -m pip install -e ".[api,dev]"`.

## Run the CLI

```powershell
.\.venv\Scripts\999scraper.exe --url "https://999.md/ro/list/computers-and-office-equipment/video" --output listings.csv
```

The scraper follows the category pagination, up to 999 pages by default, and stops after two consecutive empty pages. It writes listing history to `scraper.db` and exports listings from all fetched pages to `listings.csv`. Use `--output listings.json` for JSON, `--pages N` to set a different page cap, `--db PATH` for a different database, and `--help` to see all options. The default concurrency is 3 pages.

If you activated the virtual environment with `\.venv\Scripts\Activate.ps1`, you can run `999scraper` without the explicit path.

You can also run it from a source checkout without installing the console command:

```powershell
python -m scraper999.cli --pages 2 --output listings.csv
```

## Run the API

```powershell
python -m uvicorn scraper999.api:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs` for the interactive API docs. `POST /api/scrape` accepts a 999.md URL, page count, and concurrency. The API stores its database under `data/scraper.db` by default; set `SCRAPER_DATA_DIR` before startup to choose another storage directory. `GET /api/price-history?url=https://999.md/ro/12345678` returns observed price changes for a listing. The API is intended for local use; keep it bound to localhost unless you add authentication and deployment safeguards.

## Notes

- Browser installation is an explicit setup step. Scraper startup no longer downloads a browser or depends on Playwright's private APIs.
- URLs are restricted to `999.md` and `www.999.md`.
- The SQLite database tracks first-seen and last-seen times and whether a listing's price dropped.
- Price history records each observed price change; an existing database is upgraded with its latest known price as the initial history point.
- Pagination checks pages in order and tolerates an isolated empty page before stopping after two consecutive empty pages.
- The API no longer accepts a database path in requests, so callers cannot select an arbitrary file to write.
- The page layout and anti-bot behavior on 999.md can change; selectors may need adjustment if the site changes.
