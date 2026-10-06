import asyncio

import pytest
from pydantic import ValidationError

from scraper999 import api


def test_api_request_cannot_choose_database_path():
    assert "db_path" not in api.ScrapeRequest.model_fields
    with pytest.raises(ValidationError):
        api.ScrapeRequest.model_validate(
            {"url": "https://999.md/ro/list", "db_path": "C:/anything.db"}
        )


def test_api_defaults_to_full_category_pagination():
    assert api.ScrapeRequest(url="https://999.md/ro/list/example").pages == 999


def test_price_history_endpoint_canonicalizes_tracking_query(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "DATABASE_PATH", tmp_path / "api.db")
    result = asyncio.run(
        api.price_history("https://www.999.md/ro/12345678?clickToken=tracking")
    )
    assert result == {"url": "https://999.md/ro/12345678", "history": []}
