import asyncio
import inspect

import pytest

from scraper999.cli import _parser
from scraper999.core import Scraper999


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1 499 MDL", (1499, "MDL")),
        ("1\u00a0234,50 €", (1234.5, "EUR")),
        ("$1,234.56", (1234.56, "USD")),
        ("1,5 lei", (1.5, "MDL")),
        ("1.234 EUR", (1234, "EUR")),
        ("not listed", (None, None)),
        ("N/A", (None, None)),
    ],
)
def test_parse_price_handles_locale_formats(text, expected):
    assert Scraper999._parse_price(text) == expected


def test_validate_url_only_accepts_999_md():
    assert Scraper999._validate_url("https://www.999.md/ro/list?x=1") == "https://www.999.md/ro/list?x=1"
    for url in ("file:///tmp/data", "https://999.md.attacker.test/", "http://localhost/"):
        with pytest.raises(ValueError):
            Scraper999._validate_url(url)


def test_cli_and_library_default_to_full_category_pagination():
    assert _parser().parse_args([]).pages == 999
    assert inspect.signature(Scraper999.run_scraper).parameters["max_pages"].default == 999


def test_listing_parser_uses_listing_ids_and_ignores_boosted_ads():
    normal = Scraper999._parse_listing_card(
        "/ro/105567191",
        "Placă video Palit GeForce GTS 450\n300 MDL",
    )
    assert normal == {
        "title": "Placă video Palit GeForce GTS 450",
        "price": 300,
        "currency": "MDL",
        "description": "N/A",
        "url": "https://999.md/ro/105567191",
    }
    assert Scraper999._parse_listing_card(
        "/ro/12345678?clickToken=abc", "A regular tracked listing\n100 MDL"
    ) is not None
    assert Scraper999._parse_listing_card(
        "/ro/12345678?adType=booster&placement=ADS_LIST_INLINE_REDESIGN",
        "Sponsored listing\n100 MDL",
    ) is None
    assert Scraper999._parse_listing_card("/ro/category/computers", "Category") is None


def test_price_history_records_only_changes_and_tracks_drops(tmp_path):
    scraper = Scraper999(tmp_path / "history.db")
    url = "https://999.md/ro/12345678"
    try:
        for value, time in ((1000, "2026-01-01T00:00:00+00:00"),
                            (1000, "2026-01-02T00:00:00+00:00"),
                            (900, "2026-01-03T00:00:00+00:00"),
                            (1100, "2026-01-04T00:00:00+00:00")):
            saved = scraper._save_listing(
                {"url": url, "title": "Video card", "price": value,
                 "currency": "MDL", "description": "N/A"},
                time,
            )
            if value == 900:
                assert saved["price_dropped"] == 1
        assert [point["price"] for point in scraper.get_price_history(url)] == [1000, 900, 1100]
        assert [point["observed_at"] for point in scraper.get_price_history(url)] == [
            "2026-01-01T00:00:00+00:00",
            "2026-01-03T00:00:00+00:00",
            "2026-01-04T00:00:00+00:00",
        ]
    finally:
        scraper.close()


def test_price_history_migration_preserves_current_price(tmp_path):
    import sqlite3

    db = tmp_path / "old.db"
    with sqlite3.connect(db) as connection:
        connection.execute(
            """CREATE TABLE items (url TEXT PRIMARY KEY, title TEXT, price INTEGER,
               currency TEXT, description TEXT, date_added TEXT, last_seen TEXT,
               price_dropped INTEGER DEFAULT 0)"""
        )
        connection.execute(
            "INSERT INTO items(url, price, currency, date_added, last_seen) VALUES (?, ?, ?, ?, ?)",
            ("https://999.md/ro/1", 75, "EUR", "2026-01-01", "2026-01-02"),
        )
    scraper = Scraper999(db)
    try:
        assert scraper.get_price_history("https://999.md/ro/1") == [
            {"price": 75, "currency": "EUR", "observed_at": "2026-01-02"}
        ]
    finally:
        scraper.close()


def test_pagination_tolerates_an_empty_page_inside_a_concurrent_batch():
    calls = []
    responses = {
        1: (0, []),
        2: (0, []),
        3: (1, [{"url": "three"}]),
        4: (1, [{"url": "four"}]),
        5: (0, []),
        6: (1, [{"url": "six"}]),
    }

    async def fetch(page_number):
        calls.append(page_number)
        return responses[page_number]

    results = asyncio.run(Scraper999._collect_pages(fetch, max_pages=6, concurrency=3))
    assert [item["url"] for item in results] == ["three", "four", "six"]
    assert calls == [1, 2, 3, 4, 5, 6]


def test_pagination_stops_after_two_empty_pages_at_batch_end():
    calls = []

    async def fetch(page_number):
        calls.append(page_number)
        return (0, []) if page_number >= 3 else (1, [{"url": str(page_number)}])

    results = asyncio.run(Scraper999._collect_pages(fetch, max_pages=10, concurrency=2))
    assert [item["url"] for item in results] == ["1", "2"]
    assert calls == [1, 2, 3, 4]
