"""
Seasonal login quote generation using OpenAI Responses API with safe fallback.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Literal, Optional, Tuple

import httpx

SeasonLabel = Literal["winter", "spring", "summer", "autumn"]
TimeOfDayLabel = Literal["morning", "afternoon", "evening"]
QuoteSource = Literal["ai", "fallback"]

FALLBACK_QUOTES = {
    "witty_fun": [
        "Success is 10% strategy and 90% remembering to hit save.",
        "Great things begin with coffee, courage, and one brave click.",
        "Today is a blank page. Sketch big, laugh often, ship something.",
        "Momentum loves motion. Tiny steps still count as dancing forward.",
    ],
    "deep": [
        "Discipline is remembering what you want most, not what is easiest now.",
        "Small consistent actions quietly become extraordinary outcomes.",
    ],
}
DEFAULT_QUOTE = "Show up with intention. The rest gets easier after the first step."


def _month_to_season(month: int) -> SeasonLabel:
    if month in (12, 1, 2):
        return "winter"
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    return "autumn"


def _hour_to_time_of_day(hour: int) -> TimeOfDayLabel:
    if hour < 12:
        return "morning"
    if hour < 17:
        return "afternoon"
    return "evening"


def _pick_fallback_quote() -> str:
    witty_fun = FALLBACK_QUOTES["witty_fun"]
    deep = FALLBACK_QUOTES["deep"]
    use_playful = bool(witty_fun) and (not deep or os.urandom(1)[0] / 255 < 0.7)
    pool = witty_fun if use_playful else deep
    if not pool:
        return DEFAULT_QUOTE
    idx = int.from_bytes(os.urandom(2), "big") % len(pool)
    return pool[idx]


def _clean_quote(text: str) -> str:
    cleaned = " ".join((text or "").strip().split())
    cleaned = cleaned.strip(" \"'")
    if len(cleaned) > 220:
        cleaned = cleaned[:220].rsplit(" ", 1)[0].strip()
    return cleaned


def _extract_text_from_responses_api(data: dict) -> str:
    direct = (data.get("output_text") or "").strip()
    if direct:
        return direct
    out = data.get("output")
    if not isinstance(out, list):
        return ""
    parts: list[str] = []
    for item in out:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "message" or item.get("role") != "assistant":
            continue
        for block in item.get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") not in ("output_text", "text", None):
                continue
            text = (block.get("text") or "").strip()
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


async def generate_login_quote(now: Optional[datetime] = None) -> Tuple[str, QuoteSource]:
    now_local = now or datetime.now()
    season = _month_to_season(now_local.month)
    time_of_day = _hour_to_time_of_day(now_local.hour)
    month_name = now_local.strftime("%B")

    fallback = _pick_fallback_quote()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return fallback, "fallback"

    model = os.getenv("OPENAI_LOGIN_QUOTE_MODEL", "").strip() or "gpt-4.1-mini"
    url = "https://api.openai.com/v1/responses"
    instructions = (
        "You write short motivational one-line quotes for a sales CRM login popup. "
        "Output exactly one sentence, 8-20 words, plain text only. "
        "No profanity, no politics, no religion, no controversy, no emojis, no hashtags. "
        "Tone distribution target across calls: 70% witty/fun, 30% deep."
    )
    user_prompt = (
        f"Context: UK business user logging in during {time_of_day} in {month_name} ({season}). "
        "Write one seasonal quote that feels relevant to time-of-year. "
        "Do not mention weather forecasts or specific real-world claims."
    )
    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": instructions}]},
            {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
        ],
        "metadata": {"feature": "login_quote", "season": season, "time_of_day": time_of_day},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict):
                return fallback, "fallback"
            quote = _clean_quote(_extract_text_from_responses_api(data))
            if not quote:
                return fallback, "fallback"
            return quote, "ai"
    except Exception:
        return fallback, "fallback"
