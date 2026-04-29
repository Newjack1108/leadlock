import asyncio
from datetime import datetime

from app.login_quote_service import _hour_to_time_of_day, _month_to_season, generate_login_quote


def test_month_to_season_mapping():
    assert _month_to_season(1) == "winter"
    assert _month_to_season(4) == "spring"
    assert _month_to_season(7) == "summer"
    assert _month_to_season(10) == "autumn"


def test_hour_to_time_of_day_mapping():
    assert _hour_to_time_of_day(8) == "morning"
    assert _hour_to_time_of_day(14) == "afternoon"
    assert _hour_to_time_of_day(20) == "evening"


def test_generate_login_quote_falls_back_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    quote, source = asyncio.run(generate_login_quote(now=datetime(2026, 12, 5, 9, 30)))
    assert source == "fallback"
    assert isinstance(quote, str)
    assert quote.strip() != ""
