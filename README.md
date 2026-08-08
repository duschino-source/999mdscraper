# 999.md Scraper

A lightweight, portable, and robust web scraper for `999.md`. It extracts ad listings (Title, Price, Description, Link) into a CSV file while gracefully skipping irrelevant boosted ads (e.g. laptops, credit loans) that are injected into the page via the `clickToken` advertisement network. 

## Features
- **Auto-Installs Chromium**: The script (and compiled executable) uses Playwright's `compute_driver_executable()` to auto-download Chromium dynamically on the first run, allowing the `.exe` to remain under 50MB instead of bundling a massive 200MB+ browser binary!
- **Dynamic Pagination**: Scrapes all available pages up to a limit (default: 999), and halts automatically when it reaches an empty page.
- **Smart Filtering**: Skips `clickToken` boosted ads and ignores global site footer URLs (`/sitemap`, `/info/`).

## How to use
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Run the scraper:
   ```bash
   python scraper.py
   ```

## Compiling to an Executable
To package the script into a standalone executable (without bloating the file size), run:
```bash
python -m PyInstaller --onefile scraper.py
```
*Note: We purposely exclude `--add-data` for the Playwright browsers. The script handles the Chromium installation dynamically at runtime.*
